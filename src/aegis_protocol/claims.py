from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from .constants import BPS_DENOMINATOR, risk_band_for_score
from .models import ClaimRequest, ClaimStatus, CoverageProduct, IncidentSignal, PolicySnapshot


class EvidenceKind(StrEnum):
    ORACLE = "oracle"
    VAULT_LOG = "vault_log"
    GOVERNANCE = "governance"
    KEEPER = "keeper"
    COUNTERPARTY = "counterparty"
    ACCOUNTING = "accounting"


@dataclass(frozen=True)
class EvidenceItem:
    kind: EvidenceKind
    reference: str
    submitted_by: str
    confidence_bps: int
    timestamp: int
    metadata: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.reference:
            raise ValueError("evidence reference is required")
        if not self.submitted_by:
            raise ValueError("submitted_by is required")
        if self.confidence_bps < 0 or self.confidence_bps > BPS_DENOMINATOR:
            raise ValueError("confidence_bps out of range")
        if self.timestamp < 0:
            raise ValueError("timestamp cannot be negative")


@dataclass(frozen=True)
class ClaimDecision:
    claim_id: int
    reviewer: str
    approved: bool
    approved_amount: int
    reason_code: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def validate(self, request: ClaimRequest) -> None:
        if self.claim_id != request.claim_id:
            raise ValueError("decision claim_id mismatch")
        if not self.reviewer:
            raise ValueError("reviewer is required")
        if self.approved:
            if self.approved_amount <= 0:
                raise ValueError("approved decision needs amount")
            if self.approved_amount > request.amount_requested:
                raise ValueError("approved amount exceeds request")
        else:
            if self.approved_amount != 0:
                raise ValueError("rejected decision cannot approve amount")
        if not self.reason_code:
            raise ValueError("reason_code is required")


@dataclass(frozen=True)
class ReviewScore:
    evidence_score_bps: int
    incident_score_bps: int
    policy_score_bps: int
    amount_score_bps: int

    @property
    def composite_bps(self) -> int:
        return (
            self.evidence_score_bps * 4
            + self.incident_score_bps * 3
            + self.policy_score_bps * 2
            + self.amount_score_bps
        ) // 10

    @property
    def risk_band(self) -> str:
        return risk_band_for_score(self.composite_bps).code

    def as_dict(self) -> dict[str, int | str]:
        return {
            "evidence_score_bps": self.evidence_score_bps,
            "incident_score_bps": self.incident_score_bps,
            "policy_score_bps": self.policy_score_bps,
            "amount_score_bps": self.amount_score_bps,
            "composite_bps": self.composite_bps,
            "risk_band": self.risk_band,
        }


@dataclass
class ClaimReviewBook:
    claims: dict[int, ClaimRequest] = field(default_factory=dict)
    evidence: dict[int, list[EvidenceItem]] = field(default_factory=dict)
    decisions: dict[int, ClaimDecision] = field(default_factory=dict)

    def submit(self, request: ClaimRequest) -> ClaimRequest:
        request.validate()
        if request.claim_id in self.claims:
            raise ValueError("claim already exists")
        self.claims[request.claim_id] = request
        self.evidence[request.claim_id] = []
        return request

    def attach_evidence(self, claim_id: int, item: EvidenceItem) -> None:
        self._claim(claim_id)
        item.validate()
        self.evidence.setdefault(claim_id, []).append(item)

    def mark_reviewed(self, claim_id: int, timestamp: int) -> ClaimRequest:
        request = self._claim(claim_id)
        updated = request.reviewed(timestamp)
        self.claims[claim_id] = updated
        return updated

    def decide(self, decision: ClaimDecision, timestamp: int) -> ClaimRequest:
        request = self._claim(decision.claim_id)
        decision.validate(request)
        if decision.approved:
            updated = request.approved(decision.approved_amount, timestamp)
        else:
            updated = request.rejected(timestamp)
        self.claims[decision.claim_id] = updated
        self.decisions[decision.claim_id] = decision
        return updated

    def mark_paid(self, claim_id: int, amount: int, timestamp: int) -> ClaimRequest:
        request = self._claim(claim_id)
        updated = request.paid(amount, timestamp)
        self.claims[claim_id] = updated
        return updated

    def score(
        self,
        claim_id: int,
        policy: PolicySnapshot,
        product: CoverageProduct,
        incident: IncidentSignal,
    ) -> ReviewScore:
        request = self._claim(claim_id)
        policy.validate()
        product.validate()
        incident.validate()
        items = self.evidence.get(claim_id, [])
        evidence_score = self._evidence_score(items)
        incident_score = incident.severity_bps
        policy_score = self._policy_score(request, policy)
        amount_score = self._amount_score(request, policy, product)
        return ReviewScore(
            evidence_score_bps=evidence_score,
            incident_score_bps=incident_score,
            policy_score_bps=policy_score,
            amount_score_bps=amount_score,
        )

    def recommendation(
        self,
        claim_id: int,
        policy: PolicySnapshot,
        product: CoverageProduct,
        incident: IncidentSignal,
        reviewer: str,
    ) -> ClaimDecision:
        request = self._claim(claim_id)
        score = self.score(claim_id, policy, product, incident)
        evidence_refs = tuple(item.reference for item in self.evidence.get(claim_id, []))
        if not incident.active:
            return ClaimDecision(
                claim_id=claim_id,
                reviewer=reviewer,
                approved=False,
                approved_amount=0,
                reason_code="incident-inactive",
                evidence_refs=evidence_refs,
            )
        if not policy.is_active:
            return ClaimDecision(
                claim_id=claim_id,
                reviewer=reviewer,
                approved=False,
                approved_amount=0,
                reason_code="policy-inactive",
                evidence_refs=evidence_refs,
            )
        if score.evidence_score_bps < 4_000:
            return ClaimDecision(
                claim_id=claim_id,
                reviewer=reviewer,
                approved=False,
                approved_amount=0,
                reason_code="evidence-insufficient",
                evidence_refs=evidence_refs,
            )
        requested = min(request.amount_requested, policy.remaining_cover)
        net = product.net_payout(requested)
        return ClaimDecision(
            claim_id=claim_id,
            reviewer=reviewer,
            approved=True,
            approved_amount=net,
            reason_code="covered-loss",
            evidence_refs=evidence_refs,
            notes=(f"review-score={score.composite_bps}", f"band={score.risk_band}"),
        )

    def open_claims(self) -> tuple[ClaimRequest, ...]:
        return tuple(claim for claim in self.claims.values() if claim.is_open)

    def claims_for_policy(self, policy_id: int) -> tuple[ClaimRequest, ...]:
        return tuple(claim for claim in self.claims.values() if claim.policy_id == policy_id)

    def total_requested(self) -> int:
        return sum(claim.amount_requested for claim in self.claims.values())

    def total_approved(self) -> int:
        return sum(claim.amount_approved for claim in self.claims.values())

    def total_paid(self) -> int:
        return sum(claim.amount_paid for claim in self.claims.values())

    def _claim(self, claim_id: int) -> ClaimRequest:
        if claim_id not in self.claims:
            raise KeyError(f"claim not found: {claim_id}")
        return self.claims[claim_id]

    def _evidence_score(self, items: list[EvidenceItem]) -> int:
        if not items:
            return 0
        weights = {
            EvidenceKind.ORACLE: 4,
            EvidenceKind.VAULT_LOG: 3,
            EvidenceKind.GOVERNANCE: 2,
            EvidenceKind.KEEPER: 2,
            EvidenceKind.COUNTERPARTY: 2,
            EvidenceKind.ACCOUNTING: 3,
        }
        weighted_sum = 0
        total_weight = 0
        unique_refs: set[str] = set()
        for item in items:
            item.validate()
            weight = weights[item.kind]
            weighted_sum += item.confidence_bps * weight
            total_weight += weight
            unique_refs.add(item.reference)
        base = weighted_sum // max(1, total_weight)
        diversity_bonus = min(1_500, len(unique_refs) * 250)
        return min(BPS_DENOMINATOR, base + diversity_bonus)

    def _policy_score(self, request: ClaimRequest, policy: PolicySnapshot) -> int:
        if request.policy_id != policy.policy_id:
            return BPS_DENOMINATOR
        if request.submitted_at > policy.claim_window_end:
            return 8_000
        if request.submitted_at > policy.expiration_time:
            return 3_000
        return 1_000

    def _amount_score(self, request: ClaimRequest, policy: PolicySnapshot, product: CoverageProduct) -> int:
        if request.amount_requested > policy.remaining_cover:
            return BPS_DENOMINATOR
        if policy.coverage == 0:
            return BPS_DENOMINATOR
        ratio = request.amount_requested * BPS_DENOMINATOR // policy.coverage
        deductible_offset = product.deductible_bps // 2
        return min(BPS_DENOMINATOR, ratio + deductible_offset)


def allocation_for_claim(policy: PolicySnapshot, requested_amount: int) -> tuple[tuple[int, int], ...]:
    if requested_amount <= 0:
        raise ValueError("requested amount must be positive")
    if requested_amount > policy.remaining_cover:
        raise ValueError("requested amount exceeds remaining cover")
    total_exposure = policy.active_exposure
    if total_exposure <= 0:
        raise ValueError("policy has no active exposure")
    rows = policy.allocation_table()
    result: list[tuple[int, int]] = []
    remaining = requested_amount
    for index, (pool_id, exposure) in enumerate(rows):
        part = requested_amount * exposure // total_exposure
        if index == len(rows) - 1:
            part = remaining
        part = min(part, exposure)
        if part > 0:
            result.append((pool_id, part))
            remaining = max(0, remaining - part)
    return tuple(result)


def payout_parts(approved_payout: int, requested_amount: int, allocations: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    if approved_payout <= 0 or requested_amount <= 0:
        raise ValueError("payout and request must be positive")
    if approved_payout > requested_amount:
        raise ValueError("payout cannot exceed requested amount")
    result: list[tuple[int, int]] = []
    paid = 0
    for index, (pool_id, exposure) in enumerate(allocations):
        part = approved_payout * exposure // requested_amount
        if index == len(allocations) - 1:
            part = approved_payout - paid
        result.append((pool_id, part))
        paid += part
    return tuple(result)


def clone_request_with_status(request: ClaimRequest, status: ClaimStatus) -> ClaimRequest:
    if status == ClaimStatus.SUBMITTED:
        return replace(request, status=status, amount_approved=0, amount_paid=0, reviewed_at=0, paid_at=0)
    return replace(request, status=status)
