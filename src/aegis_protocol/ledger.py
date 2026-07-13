from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from .constants import DEFAULT_PROTOCOL_FEE_BPS, SECONDS_PER_DAY
from .models import (
    CessionAllocation,
    CoverageProduct,
    PolicySnapshot,
    PolicyStatus,
    PoolConfig,
    PoolPosition,
    PoolStatus,
    RiskPoolState,
    validate_duration,
)
from .pricing import PremiumBreakdown, PremiumEngine, PricingInput


@dataclass(frozen=True)
class LedgerEvent:
    sequence: int
    kind: str
    pool_id: int
    amount: int
    policy_id: int = 0
    actor: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyIssueResult:
    policy: PolicySnapshot
    premium: PremiumBreakdown
    pool_state: RiskPoolState
    event: LedgerEvent


@dataclass(frozen=True)
class TransferResult:
    policy: PolicySnapshot
    from_pool: RiskPoolState
    to_pool: RiskPoolState
    event: LedgerEvent


@dataclass(frozen=True)
class ExpirationResult:
    policy: PolicySnapshot
    pool_states: tuple[RiskPoolState, ...]
    events: tuple[LedgerEvent, ...]


@dataclass
class CapitalLedger:
    pricing: PremiumEngine = field(default_factory=PremiumEngine)
    pool_configs: dict[int, PoolConfig] = field(default_factory=dict)
    pools: dict[int, RiskPoolState] = field(default_factory=dict)
    positions: dict[tuple[int, str], PoolPosition] = field(default_factory=dict)
    policies: dict[int, PolicySnapshot] = field(default_factory=dict)
    events: list[LedgerEvent] = field(default_factory=list)
    _policy_ids: count = field(default_factory=lambda: count(1), init=False)
    _event_ids: count = field(default_factory=lambda: count(1), init=False)

    def add_pool(self, config: PoolConfig, initial_state: RiskPoolState | None = None) -> None:
        config.validate()
        if config.pool_id in self.pool_configs:
            raise ValueError("pool already exists")
        state = initial_state or RiskPoolState(
            pool_id=config.pool_id,
            total_capital=0,
            locked_exposure=0,
            max_utilization_bps=config.max_utilization_bps,
            status=config.status,
        )
        state.validate()
        self.pool_configs[config.pool_id] = config
        self.pools[config.pool_id] = state
        self._append_event("pool.created", config.pool_id, 0, actor=config.label)

    def set_pool_status(self, pool_id: int, status: PoolStatus) -> None:
        config = self._pool_config(pool_id)
        self.pool_configs[pool_id] = config.with_status(status)
        state = self._pool(pool_id)
        self.pools[pool_id] = RiskPoolState(
            pool_id=state.pool_id,
            total_capital=state.total_capital,
            locked_exposure=state.locked_exposure,
            pending_claims=state.pending_claims,
            paid_claims=state.paid_claims,
            earned_premiums=state.earned_premiums,
            protocol_fees=state.protocol_fees,
            max_utilization_bps=state.max_utilization_bps,
            status=status,
        )
        self._append_event("pool.status", pool_id, 0, metadata={"status": status.value})

    def deposit(self, pool_id: int, provider: str, amount: int) -> PoolPosition:
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        self._require_active_pool(pool_id)
        state = self._pool(pool_id).deposit(amount)
        self.pools[pool_id] = state
        key = (pool_id, provider)
        current = self.positions.get(
            key,
            PoolPosition(pool_id=pool_id, provider=provider, shares=0, deposited=0),
        )
        updated = current.deposit(amount)
        self.positions[key] = updated
        self._append_event("capital.deposit", pool_id, amount, actor=provider)
        return updated

    def withdraw(self, pool_id: int, provider: str, amount: int) -> PoolPosition:
        if amount <= 0:
            raise ValueError("withdraw amount must be positive")
        key = (pool_id, provider)
        if key not in self.positions:
            raise ValueError("provider has no position")
        current = self.positions[key]
        updated_position = current.withdraw(amount)
        updated_pool = self._pool(pool_id).withdraw(amount)
        self.positions[key] = updated_position
        self.pools[pool_id] = updated_pool
        self._append_event("capital.withdraw", pool_id, amount, actor=provider)
        return updated_position

    def issue_policy(
        self,
        holder: str,
        beneficiary: str,
        pool_id: int,
        product: CoverageProduct,
        subject: str,
        coverage: int,
        duration_days: int,
        start_time: int,
        risk_score_bps: int = 0,
        jurisdiction_haircut_bps: int = 0,
        broker_discount_bps: int = 0,
    ) -> PolicyIssueResult:
        self._require_active_pool(pool_id)
        product.validate()
        validate_duration(duration_days)
        pool = self._pool(pool_id)
        config = self._pool_config(pool_id)
        pricing_input = PricingInput(
            product=product,
            pool=pool,
            pool_config=config,
            coverage=coverage,
            duration_days=duration_days,
            risk_score_bps=risk_score_bps,
            jurisdiction_haircut_bps=jurisdiction_haircut_bps,
            broker_discount_bps=broker_discount_bps,
        )
        premium = self.pricing.quote(pricing_input)
        updated_pool = pool.earn_premium(
            premium.final_premium,
            protocol_fee_bps=self.pricing.protocol_fee_bps or DEFAULT_PROTOCOL_FEE_BPS,
        ).lock(coverage)
        self.pools[pool_id] = updated_pool

        policy_id = next(self._policy_ids)
        expiration = start_time + duration_days * SECONDS_PER_DAY
        policy = PolicySnapshot(
            policy_id=policy_id,
            holder=holder,
            beneficiary=beneficiary,
            pool_id=pool_id,
            product_id=product.product_id,
            subject=subject,
            coverage=coverage,
            premium=premium.final_premium,
            start_time=start_time,
            expiration_time=expiration,
            claim_window_end=expiration + product.claim_window_days * SECONDS_PER_DAY,
            retained_exposure=coverage,
        )
        policy.validate()
        self.policies[policy_id] = policy
        event = self._append_event("policy.issue", pool_id, coverage, policy_id=policy_id, actor=holder)
        return PolicyIssueResult(policy=policy, premium=premium, pool_state=updated_pool, event=event)

    def transfer_exposure(self, policy_id: int, to_pool_id: int, amount: int) -> TransferResult:
        if amount <= 0:
            raise ValueError("transfer amount must be positive")
        policy = self._policy(policy_id)
        if policy.status != PolicyStatus.ACTIVE:
            raise ValueError("policy is not active")
        if to_pool_id == policy.pool_id:
            raise ValueError("cannot transfer to origin pool")
        self._require_active_pool(to_pool_id)
        from_pool = self._pool(policy.pool_id)
        to_pool = self._pool(to_pool_id)
        if amount > policy.retained_exposure:
            raise ValueError("transfer exceeds retained exposure")
        updated_to = to_pool.lock(amount)
        updated_from = from_pool.release(amount)
        updated_policy = policy.with_cession(to_pool_id, amount)
        self.pools[policy.pool_id] = updated_from
        self.pools[to_pool_id] = updated_to
        self.policies[policy_id] = updated_policy
        event = self._append_event(
            "policy.transfer",
            policy.pool_id,
            amount,
            policy_id=policy_id,
            metadata={"to_pool": str(to_pool_id)},
        )
        return TransferResult(policy=updated_policy, from_pool=updated_from, to_pool=updated_to, event=event)

    def expire_policy(self, policy_id: int) -> ExpirationResult:
        policy = self._policy(policy_id)
        if policy.status != PolicyStatus.ACTIVE:
            raise ValueError("policy is not active")
        states: list[RiskPoolState] = []
        events: list[LedgerEvent] = []

        origin_state = self._pool(policy.pool_id).release(policy.retained_exposure)
        self.pools[policy.pool_id] = origin_state
        states.append(origin_state)
        events.append(self._append_event("policy.expire.origin", policy.pool_id, policy.retained_exposure, policy_id))

        for cession in policy.cessions:
            cession_state = self._pool(cession.pool_id).release(cession.amount)
            self.pools[cession.pool_id] = cession_state
            states.append(cession_state)
            events.append(
                self._append_event("policy.expire.cession", cession.pool_id, cession.amount, policy_id)
            )

        expired = policy.expire()
        self.policies[policy_id] = expired
        return ExpirationResult(policy=expired, pool_states=tuple(states), events=tuple(events))

    def register_pending_claim(self, policy_id: int, claim_amount: int) -> tuple[tuple[int, int], ...]:
        policy = self._policy(policy_id)
        if claim_amount <= 0:
            raise ValueError("claim amount must be positive")
        if claim_amount > policy.remaining_cover:
            raise ValueError("claim exceeds remaining cover")
        total_exposure = policy.active_exposure
        if total_exposure <= 0:
            raise ValueError("policy has no active exposure")
        allocations: list[tuple[int, int]] = []
        remaining = claim_amount
        table = policy.allocation_table()
        for index, (pool_id, exposure) in enumerate(table):
            amount = claim_amount * exposure // total_exposure
            if index == len(table) - 1:
                amount = remaining
            amount = min(amount, exposure)
            if amount > 0:
                self.pools[pool_id] = self._pool(pool_id).register_claim(amount)
                allocations.append((pool_id, amount))
                remaining = max(0, remaining - amount)
        self._append_event("claim.reserve", policy.pool_id, claim_amount, policy_id=policy_id)
        return tuple(allocations)

    def settle_claim_allocations(
        self,
        policy_id: int,
        requested_amount: int,
        approved_payout: int,
        allocations: tuple[tuple[int, int], ...],
    ) -> PolicySnapshot:
        if requested_amount <= 0:
            raise ValueError("requested amount must be positive")
        if approved_payout <= 0:
            raise ValueError("approved payout must be positive")
        if approved_payout > requested_amount:
            raise ValueError("payout cannot exceed request")
        paid = 0
        for index, (pool_id, exposure_amount) in enumerate(allocations):
            payout_part = approved_payout * exposure_amount // requested_amount
            if index == len(allocations) - 1:
                payout_part = approved_payout - paid
            self.pools[pool_id] = self._pool(pool_id).clear_claim(exposure_amount, payout_part)
            paid += payout_part
            self._append_event("claim.settle.pool", pool_id, payout_part, policy_id=policy_id)
        policy = self._policy(policy_id).mark_claimed(approved_payout)
        self.policies[policy_id] = policy
        self._append_event("claim.settle", policy.pool_id, approved_payout, policy_id=policy_id)
        return policy

    def pool_exposure(self, pool_id: int) -> int:
        return self._pool(pool_id).locked_exposure

    def pool_free_capital(self, pool_id: int) -> int:
        return self._pool(pool_id).free_capital

    def pool_available_capacity(self, pool_id: int) -> int:
        return self._pool(pool_id).available_capacity

    def policy_allocation(self, policy_id: int, pool_id: int) -> int:
        return self._policy(policy_id).allocation_for_pool(pool_id)

    def provider_position(self, pool_id: int, provider: str) -> PoolPosition | None:
        return self.positions.get((pool_id, provider))

    def events_for_policy(self, policy_id: int) -> tuple[LedgerEvent, ...]:
        return tuple(event for event in self.events if event.policy_id == policy_id)

    def events_for_pool(self, pool_id: int) -> tuple[LedgerEvent, ...]:
        return tuple(event for event in self.events if event.pool_id == pool_id)

    def _pool_config(self, pool_id: int) -> PoolConfig:
        if pool_id not in self.pool_configs:
            raise KeyError(f"pool config not found: {pool_id}")
        return self.pool_configs[pool_id]

    def _pool(self, pool_id: int) -> RiskPoolState:
        if pool_id not in self.pools:
            raise KeyError(f"pool not found: {pool_id}")
        return self.pools[pool_id]

    def _policy(self, policy_id: int) -> PolicySnapshot:
        if policy_id not in self.policies:
            raise KeyError(f"policy not found: {policy_id}")
        return self.policies[policy_id]

    def _require_active_pool(self, pool_id: int) -> None:
        config = self._pool_config(pool_id)
        if config.status != PoolStatus.ACTIVE:
            raise ValueError("pool is not active")
        state = self._pool(pool_id)
        if state.status != PoolStatus.ACTIVE:
            raise ValueError("pool state is not active")

    def _append_event(
        self,
        kind: str,
        pool_id: int,
        amount: int,
        policy_id: int = 0,
        actor: str = "",
        metadata: dict[str, str] | None = None,
    ) -> LedgerEvent:
        event = LedgerEvent(
            sequence=next(self._event_ids),
            kind=kind,
            pool_id=pool_id,
            amount=amount,
            policy_id=policy_id,
            actor=actor,
            metadata=metadata or {},
        )
        self.events.append(event)
        return event


def build_default_ledger(pool_configs: list[PoolConfig]) -> CapitalLedger:
    ledger = CapitalLedger()
    for config in pool_configs:
        ledger.add_pool(config)
    return ledger


def aggregate_policy_exposure(policies: list[PolicySnapshot]) -> dict[int, int]:
    totals: dict[int, int] = {}
    for policy in policies:
        for pool_id, amount in policy.allocation_table():
            totals[pool_id] = totals.get(pool_id, 0) + amount
    return totals


def aggregate_position_shares(positions: list[PoolPosition]) -> dict[int, int]:
    totals: dict[int, int] = {}
    for position in positions:
        totals[position.pool_id] = totals.get(position.pool_id, 0) + position.shares
    return totals


def allocation_delta(before: PolicySnapshot, after: PolicySnapshot) -> dict[int, int]:
    pools = {pool_id for pool_id, _ in before.allocation_table()}
    pools.update(pool_id for pool_id, _ in after.allocation_table())
    delta: dict[int, int] = {}
    for pool_id in pools:
        delta[pool_id] = after.allocation_for_pool(pool_id) - before.allocation_for_pool(pool_id)
    return delta


def normalize_allocations(allocations: tuple[CessionAllocation, ...]) -> tuple[CessionAllocation, ...]:
    totals: dict[int, int] = {}
    for allocation in allocations:
        allocation.validate()
        totals[allocation.pool_id] = totals.get(allocation.pool_id, 0) + allocation.amount
    return tuple(CessionAllocation(pool_id, amount) for pool_id, amount in sorted(totals.items()))
