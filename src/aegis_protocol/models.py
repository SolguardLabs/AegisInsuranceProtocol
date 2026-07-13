from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

from .constants import (
    BPS_DENOMINATOR,
    CLAIM_APPROVED,
    CLAIM_PAID,
    CLAIM_REJECTED,
    CLAIM_REVIEWED,
    CLAIM_SUBMITTED,
    DEFAULT_CLAIM_WINDOW_DAYS,
    DEFAULT_DEDUCTIBLE_BPS,
    DEFAULT_POOL_UTILIZATION_BPS,
    DEFAULT_RETENTION_BPS,
    MAX_CESSION_SLOTS,
    MAX_POLICY_DAYS,
    MIN_POLICY_DAYS,
    POLICY_ACTIVE,
    POLICY_CANCELLED,
    POLICY_CLAIMED,
    POLICY_EXPIRED,
    POOL_ACTIVE,
    POOL_CLOSED,
    POOL_PAUSED,
    clamp_bps,
)


class PolicyStatus(StrEnum):
    ACTIVE = POLICY_ACTIVE
    EXPIRED = POLICY_EXPIRED
    CLAIMED = POLICY_CLAIMED
    CANCELLED = POLICY_CANCELLED


class PoolStatus(StrEnum):
    ACTIVE = POOL_ACTIVE
    PAUSED = POOL_PAUSED
    CLOSED = POOL_CLOSED


class ClaimStatus(StrEnum):
    SUBMITTED = CLAIM_SUBMITTED
    REVIEWED = CLAIM_REVIEWED
    APPROVED = CLAIM_APPROVED
    PAID = CLAIM_PAID
    REJECTED = CLAIM_REJECTED


@dataclass(frozen=True)
class PoolConfig:
    pool_id: int
    label: str
    jurisdiction: str
    min_capital: int = 0
    max_utilization_bps: int = DEFAULT_POOL_UTILIZATION_BPS
    retention_bps: int = DEFAULT_RETENTION_BPS
    status: PoolStatus = PoolStatus.ACTIVE

    def validate(self) -> None:
        if self.pool_id <= 0:
            raise ValueError("pool_id must be positive")
        if not self.label:
            raise ValueError("pool label is required")
        if not self.jurisdiction:
            raise ValueError("jurisdiction is required")
        if self.min_capital < 0:
            raise ValueError("min_capital cannot be negative")
        if self.max_utilization_bps <= 0 or self.max_utilization_bps > BPS_DENOMINATOR:
            raise ValueError("max_utilization_bps out of range")
        if self.retention_bps < 0 or self.retention_bps > BPS_DENOMINATOR:
            raise ValueError("retention_bps out of range")

    @property
    def is_active(self) -> bool:
        return self.status == PoolStatus.ACTIVE

    def with_status(self, status: PoolStatus) -> "PoolConfig":
        return replace(self, status=status)

    def retained_amount(self, coverage: int) -> int:
        if coverage < 0:
            raise ValueError("coverage cannot be negative")
        return coverage * self.retention_bps // BPS_DENOMINATOR

    def ceded_amount(self, coverage: int) -> int:
        return coverage - self.retained_amount(coverage)


@dataclass(frozen=True)
class CoverageProduct:
    product_id: int
    code: str
    label: str
    base_rate_bps: int
    min_premium: int
    deductible_bps: int = DEFAULT_DEDUCTIBLE_BPS
    claim_window_days: int = DEFAULT_CLAIM_WINDOW_DAYS
    max_cover: int = 0
    active: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if self.product_id <= 0:
            raise ValueError("product_id must be positive")
        if not self.code:
            raise ValueError("product code is required")
        if not self.label:
            raise ValueError("product label is required")
        if self.base_rate_bps <= 0 or self.base_rate_bps > BPS_DENOMINATOR:
            raise ValueError("base_rate_bps out of range")
        if self.min_premium < 0:
            raise ValueError("min_premium cannot be negative")
        if self.deductible_bps < 0 or self.deductible_bps > BPS_DENOMINATOR:
            raise ValueError("deductible_bps out of range")
        if self.claim_window_days < 0 or self.claim_window_days > MAX_POLICY_DAYS:
            raise ValueError("claim_window_days out of range")
        if self.max_cover < 0:
            raise ValueError("max_cover cannot be negative")

    def allows_cover(self, amount: int) -> bool:
        if amount <= 0:
            return False
        return self.max_cover == 0 or amount <= self.max_cover

    def net_payout(self, approved_amount: int) -> int:
        if approved_amount < 0:
            raise ValueError("approved_amount cannot be negative")
        deductible = approved_amount * self.deductible_bps // BPS_DENOMINATOR
        return approved_amount - deductible

    @property
    def code32(self) -> bytes:
        raw = self.code.encode("ascii")
        if len(raw) > 32:
            raise ValueError("product code does not fit bytes32")
        return raw.ljust(32, b"\0")


@dataclass(frozen=True)
class UnderwriterAccount:
    address: str
    display_name: str
    jurisdiction: str
    risk_limit: int
    preferred_products: tuple[str, ...] = field(default_factory=tuple)
    active: bool = True

    def validate(self) -> None:
        if not self.address:
            raise ValueError("address is required")
        if self.risk_limit < 0:
            raise ValueError("risk_limit cannot be negative")
        if not self.jurisdiction:
            raise ValueError("jurisdiction is required")

    def can_underwrite(self, product_code: str, amount: int) -> bool:
        if not self.active:
            return False
        if amount > self.risk_limit:
            return False
        if not self.preferred_products:
            return True
        return product_code in self.preferred_products


@dataclass(frozen=True)
class PoolPosition:
    pool_id: int
    provider: str
    shares: int
    deposited: int
    withdrawn: int = 0
    earned: int = 0

    def validate(self) -> None:
        if self.pool_id <= 0:
            raise ValueError("pool_id must be positive")
        if not self.provider:
            raise ValueError("provider is required")
        if self.shares < 0 or self.deposited < 0 or self.withdrawn < 0 or self.earned < 0:
            raise ValueError("position amounts cannot be negative")

    @property
    def net_deposited(self) -> int:
        return self.deposited - self.withdrawn

    @property
    def withdrawable_basis(self) -> int:
        return self.shares + self.earned

    def deposit(self, amount: int) -> "PoolPosition":
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        return replace(self, shares=self.shares + amount, deposited=self.deposited + amount)

    def withdraw(self, amount: int) -> "PoolPosition":
        if amount <= 0:
            raise ValueError("withdraw amount must be positive")
        if amount > self.shares:
            raise ValueError("withdraw amount exceeds shares")
        return replace(self, shares=self.shares - amount, withdrawn=self.withdrawn + amount)

    def credit_earnings(self, amount: int) -> "PoolPosition":
        if amount < 0:
            raise ValueError("earnings cannot be negative")
        return replace(self, earned=self.earned + amount)


@dataclass(frozen=True)
class RiskPoolState:
    pool_id: int
    total_capital: int
    locked_exposure: int
    pending_claims: int = 0
    paid_claims: int = 0
    earned_premiums: int = 0
    protocol_fees: int = 0
    max_utilization_bps: int = DEFAULT_POOL_UTILIZATION_BPS
    status: PoolStatus = PoolStatus.ACTIVE

    def validate(self) -> None:
        if self.pool_id <= 0:
            raise ValueError("pool_id must be positive")
        if min(
            self.total_capital,
            self.locked_exposure,
            self.pending_claims,
            self.paid_claims,
            self.earned_premiums,
            self.protocol_fees,
        ) < 0:
            raise ValueError("pool accounting cannot be negative")
        if self.max_utilization_bps <= 0 or self.max_utilization_bps > BPS_DENOMINATOR:
            raise ValueError("max_utilization_bps out of range")

    @property
    def capacity_ceiling(self) -> int:
        return self.total_capital * self.max_utilization_bps // BPS_DENOMINATOR

    @property
    def available_capacity(self) -> int:
        return max(0, self.capacity_ceiling - self.locked_exposure)

    @property
    def free_capital(self) -> int:
        return max(0, self.total_capital - self.locked_exposure)

    @property
    def utilization_bps(self) -> int:
        if self.total_capital == 0:
            return 0
        return self.locked_exposure * BPS_DENOMINATOR // self.total_capital

    @property
    def solvency_bps(self) -> int:
        obligations = self.locked_exposure + self.pending_claims
        if obligations == 0:
            return BPS_DENOMINATOR
        return self.total_capital * BPS_DENOMINATOR // obligations

    def deposit(self, amount: int) -> "RiskPoolState":
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        return replace(self, total_capital=self.total_capital + amount)

    def earn_premium(self, premium: int, protocol_fee_bps: int) -> "RiskPoolState":
        if premium < 0:
            raise ValueError("premium cannot be negative")
        fee_bps = clamp_bps(protocol_fee_bps)
        protocol_fee = premium * fee_bps // BPS_DENOMINATOR
        pool_premium = premium - protocol_fee
        return replace(
            self,
            total_capital=self.total_capital + pool_premium,
            earned_premiums=self.earned_premiums + pool_premium,
            protocol_fees=self.protocol_fees + protocol_fee,
        )

    def lock(self, amount: int) -> "RiskPoolState":
        if amount <= 0:
            raise ValueError("lock amount must be positive")
        if amount > self.available_capacity:
            raise ValueError("lock amount exceeds available capacity")
        return replace(self, locked_exposure=self.locked_exposure + amount)

    def release(self, amount: int) -> "RiskPoolState":
        if amount < 0:
            raise ValueError("release amount cannot be negative")
        released = min(amount, self.locked_exposure)
        return replace(self, locked_exposure=self.locked_exposure - released)

    def register_claim(self, amount: int) -> "RiskPoolState":
        if amount <= 0:
            raise ValueError("claim amount must be positive")
        return replace(self, pending_claims=self.pending_claims + amount)

    def clear_claim(self, exposure_amount: int, payout_amount: int) -> "RiskPoolState":
        if exposure_amount < 0 or payout_amount < 0:
            raise ValueError("claim amounts cannot be negative")
        if payout_amount > self.total_capital:
            raise ValueError("payout exceeds pool capital")
        pending = max(0, self.pending_claims - exposure_amount)
        locked = max(0, self.locked_exposure - exposure_amount)
        return replace(
            self,
            pending_claims=pending,
            locked_exposure=locked,
            total_capital=self.total_capital - payout_amount,
            paid_claims=self.paid_claims + payout_amount,
        )

    def withdraw(self, amount: int) -> "RiskPoolState":
        if amount <= 0:
            raise ValueError("withdraw amount must be positive")
        if amount > self.free_capital:
            raise ValueError("withdraw amount exceeds free capital")
        return replace(self, total_capital=self.total_capital - amount)


@dataclass(frozen=True)
class CessionAllocation:
    pool_id: int
    amount: int

    def validate(self) -> None:
        if self.pool_id <= 0:
            raise ValueError("pool_id must be positive")
        if self.amount <= 0:
            raise ValueError("cession amount must be positive")


@dataclass(frozen=True)
class PolicySnapshot:
    policy_id: int
    holder: str
    beneficiary: str
    pool_id: int
    product_id: int
    subject: str
    coverage: int
    premium: int
    start_time: int
    expiration_time: int
    claim_window_end: int
    retained_exposure: int
    ceded_exposure: int = 0
    paid_amount: int = 0
    status: PolicyStatus = PolicyStatus.ACTIVE
    cessions: tuple[CessionAllocation, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if self.policy_id <= 0:
            raise ValueError("policy_id must be positive")
        if not self.holder or not self.beneficiary:
            raise ValueError("holder and beneficiary are required")
        if self.pool_id <= 0 or self.product_id <= 0:
            raise ValueError("pool_id and product_id must be positive")
        if self.coverage <= 0:
            raise ValueError("coverage must be positive")
        if self.premium < 0 or self.paid_amount < 0:
            raise ValueError("premium and paid amount cannot be negative")
        if self.expiration_time <= self.start_time:
            raise ValueError("expiration_time must be after start_time")
        if self.claim_window_end < self.expiration_time:
            raise ValueError("claim_window_end must be after expiration")
        if self.retained_exposure < 0 or self.ceded_exposure < 0:
            raise ValueError("exposure cannot be negative")
        if len(self.cessions) > MAX_CESSION_SLOTS:
            raise ValueError("too many cession allocations")
        for cession in self.cessions:
            cession.validate()
        if self.retained_exposure + self.ceded_exposure > self.coverage:
            raise ValueError("exposure exceeds coverage")

    @property
    def active_exposure(self) -> int:
        return self.retained_exposure + self.ceded_exposure

    @property
    def remaining_cover(self) -> int:
        return max(0, self.coverage - self.paid_amount)

    @property
    def is_active(self) -> bool:
        return self.status == PolicyStatus.ACTIVE

    def allocation_for_pool(self, pool_id: int) -> int:
        if pool_id == self.pool_id:
            return self.retained_exposure
        total = 0
        for cession in self.cessions:
            if cession.pool_id == pool_id:
                total += cession.amount
        return total

    def allocation_table(self) -> tuple[tuple[int, int], ...]:
        rows = [(self.pool_id, self.retained_exposure)]
        rows.extend((cession.pool_id, cession.amount) for cession in self.cessions)
        return tuple((pool_id, amount) for pool_id, amount in rows if amount > 0)

    def with_cession(self, to_pool_id: int, amount: int) -> "PolicySnapshot":
        if self.status != PolicyStatus.ACTIVE:
            raise ValueError("policy is not active")
        if amount <= 0:
            raise ValueError("cession amount must be positive")
        if amount > self.retained_exposure:
            raise ValueError("cession amount exceeds retained exposure")
        updated: list[CessionAllocation] = []
        merged = False
        for cession in self.cessions:
            if cession.pool_id == to_pool_id:
                updated.append(CessionAllocation(to_pool_id, cession.amount + amount))
                merged = True
            else:
                updated.append(cession)
        if not merged:
            if len(updated) >= MAX_CESSION_SLOTS:
                raise ValueError("cession slot limit reached")
            updated.append(CessionAllocation(to_pool_id, amount))
        return replace(
            self,
            retained_exposure=self.retained_exposure - amount,
            ceded_exposure=self.ceded_exposure + amount,
            cessions=tuple(updated),
        )

    def expire(self) -> "PolicySnapshot":
        return replace(
            self,
            retained_exposure=0,
            ceded_exposure=0,
            status=PolicyStatus.EXPIRED,
            cessions=tuple(),
        )

    def mark_claimed(self, payout: int) -> "PolicySnapshot":
        if payout < 0:
            raise ValueError("payout cannot be negative")
        if payout > self.remaining_cover:
            raise ValueError("payout exceeds remaining cover")
        return replace(
            self,
            paid_amount=self.paid_amount + payout,
            status=PolicyStatus.CLAIMED,
        )


@dataclass(frozen=True)
class IncidentSignal:
    incident_hash: str
    product_code: str
    subject: str
    opened_at: int
    active: bool
    severity_bps: int
    sources: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.incident_hash:
            raise ValueError("incident_hash is required")
        if not self.product_code:
            raise ValueError("product_code is required")
        if not self.subject:
            raise ValueError("subject is required")
        if self.opened_at < 0:
            raise ValueError("opened_at cannot be negative")
        if self.severity_bps < 0 or self.severity_bps > BPS_DENOMINATOR:
            raise ValueError("severity_bps out of range")

    @property
    def requires_board_review(self) -> bool:
        return self.severity_bps >= 5_000 or len(self.sources) < 2


@dataclass(frozen=True)
class ClaimRequest:
    claim_id: int
    policy_id: int
    claimant: str
    beneficiary: str
    amount_requested: int
    incident_hash: str
    evidence_hash: str
    submitted_at: int
    status: ClaimStatus = ClaimStatus.SUBMITTED
    amount_approved: int = 0
    amount_paid: int = 0
    reviewed_at: int = 0
    paid_at: int = 0

    def validate(self) -> None:
        if self.claim_id <= 0 or self.policy_id <= 0:
            raise ValueError("claim_id and policy_id must be positive")
        if not self.claimant or not self.beneficiary:
            raise ValueError("claimant and beneficiary are required")
        if self.amount_requested <= 0:
            raise ValueError("amount_requested must be positive")
        if self.amount_approved < 0 or self.amount_paid < 0:
            raise ValueError("approval and paid amounts cannot be negative")
        if self.amount_approved > self.amount_requested:
            raise ValueError("approved amount exceeds request")
        if self.amount_paid > self.amount_approved:
            raise ValueError("paid amount exceeds approval")
        if not self.incident_hash or not self.evidence_hash:
            raise ValueError("incident_hash and evidence_hash are required")

    @property
    def is_open(self) -> bool:
        return self.status in {ClaimStatus.SUBMITTED, ClaimStatus.REVIEWED, ClaimStatus.APPROVED}

    def reviewed(self, timestamp: int) -> "ClaimRequest":
        if self.status != ClaimStatus.SUBMITTED:
            raise ValueError("claim cannot be marked reviewed")
        return replace(self, status=ClaimStatus.REVIEWED, reviewed_at=timestamp)

    def approved(self, amount: int, timestamp: int) -> "ClaimRequest":
        if amount <= 0 or amount > self.amount_requested:
            raise ValueError("approval amount invalid")
        if self.status not in {ClaimStatus.SUBMITTED, ClaimStatus.REVIEWED}:
            raise ValueError("claim cannot be approved")
        return replace(
            self,
            status=ClaimStatus.APPROVED,
            amount_approved=amount,
            reviewed_at=timestamp,
        )

    def rejected(self, timestamp: int) -> "ClaimRequest":
        if self.status not in {ClaimStatus.SUBMITTED, ClaimStatus.REVIEWED}:
            raise ValueError("claim cannot be rejected")
        return replace(self, status=ClaimStatus.REJECTED, reviewed_at=timestamp)

    def paid(self, amount: int, timestamp: int) -> "ClaimRequest":
        if self.status != ClaimStatus.APPROVED:
            raise ValueError("claim must be approved")
        if amount != self.amount_approved:
            raise ValueError("paid amount must match approval")
        return replace(
            self,
            status=ClaimStatus.PAID,
            amount_paid=amount,
            paid_at=timestamp,
        )


def validate_duration(days: int) -> None:
    if days < MIN_POLICY_DAYS or days > MAX_POLICY_DAYS:
        raise ValueError("policy duration out of range")


def weighted_average_bps(values: Iterable[tuple[int, int]]) -> int:
    weighted_sum = 0
    total_weight = 0
    for value, weight in values:
        if value < 0 or weight < 0:
            raise ValueError("weighted average inputs cannot be negative")
        weighted_sum += value * weight
        total_weight += weight
    if total_weight == 0:
        return 0
    return weighted_sum // total_weight


def decimal_bps(value: Decimal) -> int:
    if value < 0:
        raise ValueError("decimal value cannot be negative")
    return int(value * Decimal(BPS_DENOMINATOR))
