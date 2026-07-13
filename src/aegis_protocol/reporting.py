from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .constants import BPS_DENOMINATOR, risk_band_for_score
from .models import ClaimRequest, PolicySnapshot, RiskPoolState


@dataclass(frozen=True)
class PoolReportRow:
    pool_id: int
    total_capital: int
    locked_exposure: int
    pending_claims: int
    paid_claims: int
    utilization_bps: int
    solvency_bps: int
    free_capital: int

    @property
    def risk_band(self) -> str:
        return risk_band_for_score(self.utilization_bps).code

    def as_csv_row(self) -> str:
        return ",".join(
            [
                str(self.pool_id),
                str(self.total_capital),
                str(self.locked_exposure),
                str(self.pending_claims),
                str(self.paid_claims),
                str(self.utilization_bps),
                str(self.solvency_bps),
                str(self.free_capital),
                self.risk_band,
            ]
        )


@dataclass(frozen=True)
class PolicyReportRow:
    policy_id: int
    pool_id: int
    product_id: int
    subject: str
    holder: str
    beneficiary: str
    coverage: int
    retained_exposure: int
    ceded_exposure: int
    paid_amount: int
    status: str
    expiration_time: int

    @property
    def active_exposure(self) -> int:
        return self.retained_exposure + self.ceded_exposure

    @property
    def coverage_remaining(self) -> int:
        return max(0, self.coverage - self.paid_amount)

    def as_csv_row(self) -> str:
        return ",".join(
            [
                str(self.policy_id),
                str(self.pool_id),
                str(self.product_id),
                self.subject,
                self.holder,
                self.beneficiary,
                str(self.coverage),
                str(self.retained_exposure),
                str(self.ceded_exposure),
                str(self.paid_amount),
                self.status,
                str(self.expiration_time),
            ]
        )


@dataclass(frozen=True)
class ClaimReportRow:
    claim_id: int
    policy_id: int
    claimant: str
    beneficiary: str
    amount_requested: int
    amount_approved: int
    amount_paid: int
    status: str
    submitted_at: int

    @property
    def unpaid_approved(self) -> int:
        return max(0, self.amount_approved - self.amount_paid)

    def as_csv_row(self) -> str:
        return ",".join(
            [
                str(self.claim_id),
                str(self.policy_id),
                self.claimant,
                self.beneficiary,
                str(self.amount_requested),
                str(self.amount_approved),
                str(self.amount_paid),
                self.status,
                str(self.submitted_at),
            ]
        )


@dataclass(frozen=True)
class ExposureReport:
    generated_at: int
    pools: tuple[PoolReportRow, ...]
    policies: tuple[PolicyReportRow, ...]
    claims: tuple[ClaimReportRow, ...]

    @property
    def total_capital(self) -> int:
        return sum(row.total_capital for row in self.pools)

    @property
    def total_locked(self) -> int:
        return sum(row.locked_exposure for row in self.pools)

    @property
    def total_pending_claims(self) -> int:
        return sum(row.pending_claims for row in self.pools)

    @property
    def aggregate_utilization_bps(self) -> int:
        if self.total_capital == 0:
            return 0
        return self.total_locked * BPS_DENOMINATOR // self.total_capital

    @property
    def aggregate_solvency_bps(self) -> int:
        obligations = self.total_locked + self.total_pending_claims
        if obligations == 0:
            return BPS_DENOMINATOR
        return self.total_capital * BPS_DENOMINATOR // obligations

    def to_markdown(self) -> str:
        generated = datetime.fromtimestamp(self.generated_at, tz=UTC).isoformat()
        lines = [
            f"# Aegis Exposure Report",
            "",
            f"Generated: {generated}",
            "",
            "## Aggregate",
            "",
            f"- Total capital: {self.total_capital}",
            f"- Locked exposure: {self.total_locked}",
            f"- Pending claims: {self.total_pending_claims}",
            f"- Utilization bps: {self.aggregate_utilization_bps}",
            f"- Solvency bps: {self.aggregate_solvency_bps}",
            "",
            "## Pools",
            "",
            "| Pool | Capital | Locked | Pending | Paid | Utilization | Solvency | Free | Band |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for row in self.pools:
            lines.append(
                f"| {row.pool_id} | {row.total_capital} | {row.locked_exposure} | "
                f"{row.pending_claims} | {row.paid_claims} | {row.utilization_bps} | "
                f"{row.solvency_bps} | {row.free_capital} | {row.risk_band} |"
            )
        lines.extend(
            [
                "",
                "## Policies",
                "",
                "| Policy | Pool | Product | Subject | Coverage | Active Exposure | Paid | Status |",
                "| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for row in self.policies:
            lines.append(
                f"| {row.policy_id} | {row.pool_id} | {row.product_id} | {row.subject} | "
                f"{row.coverage} | {row.active_exposure} | {row.paid_amount} | {row.status} |"
            )
        lines.extend(
            [
                "",
                "## Claims",
                "",
                "| Claim | Policy | Requested | Approved | Paid | Status |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in self.claims:
            lines.append(
                f"| {row.claim_id} | {row.policy_id} | {row.amount_requested} | "
                f"{row.amount_approved} | {row.amount_paid} | {row.status} |"
            )
        return "\n".join(lines)

    def pools_csv(self) -> str:
        header = "pool_id,total_capital,locked_exposure,pending_claims,paid_claims,utilization_bps,solvency_bps,free_capital,risk_band"
        return "\n".join([header, *(row.as_csv_row() for row in self.pools)])

    def policies_csv(self) -> str:
        header = "policy_id,pool_id,product_id,subject,holder,beneficiary,coverage,retained_exposure,ceded_exposure,paid_amount,status,expiration_time"
        return "\n".join([header, *(row.as_csv_row() for row in self.policies)])

    def claims_csv(self) -> str:
        header = "claim_id,policy_id,claimant,beneficiary,amount_requested,amount_approved,amount_paid,status,submitted_at"
        return "\n".join([header, *(row.as_csv_row() for row in self.claims)])


@dataclass
class ReportBuilder:
    generated_at: int
    pool_rows: list[PoolReportRow] = field(default_factory=list)
    policy_rows: list[PolicyReportRow] = field(default_factory=list)
    claim_rows: list[ClaimReportRow] = field(default_factory=list)

    def add_pool(self, state: RiskPoolState) -> None:
        state.validate()
        self.pool_rows.append(
            PoolReportRow(
                pool_id=state.pool_id,
                total_capital=state.total_capital,
                locked_exposure=state.locked_exposure,
                pending_claims=state.pending_claims,
                paid_claims=state.paid_claims,
                utilization_bps=state.utilization_bps,
                solvency_bps=state.solvency_bps,
                free_capital=state.free_capital,
            )
        )

    def add_policy(self, policy: PolicySnapshot) -> None:
        policy.validate()
        self.policy_rows.append(
            PolicyReportRow(
                policy_id=policy.policy_id,
                pool_id=policy.pool_id,
                product_id=policy.product_id,
                subject=policy.subject,
                holder=policy.holder,
                beneficiary=policy.beneficiary,
                coverage=policy.coverage,
                retained_exposure=policy.retained_exposure,
                ceded_exposure=policy.ceded_exposure,
                paid_amount=policy.paid_amount,
                status=policy.status.value,
                expiration_time=policy.expiration_time,
            )
        )

    def add_claim(self, claim: ClaimRequest) -> None:
        claim.validate()
        self.claim_rows.append(
            ClaimReportRow(
                claim_id=claim.claim_id,
                policy_id=claim.policy_id,
                claimant=claim.claimant,
                beneficiary=claim.beneficiary,
                amount_requested=claim.amount_requested,
                amount_approved=claim.amount_approved,
                amount_paid=claim.amount_paid,
                status=claim.status.value,
                submitted_at=claim.submitted_at,
            )
        )

    def build(self) -> ExposureReport:
        return ExposureReport(
            generated_at=self.generated_at,
            pools=tuple(sorted(self.pool_rows, key=lambda row: row.pool_id)),
            policies=tuple(sorted(self.policy_rows, key=lambda row: row.policy_id)),
            claims=tuple(sorted(self.claim_rows, key=lambda row: row.claim_id)),
        )

    @classmethod
    def from_state(
        cls,
        generated_at: int,
        pools: list[RiskPoolState],
        policies: list[PolicySnapshot],
        claims: list[ClaimRequest],
    ) -> "ReportBuilder":
        builder = cls(generated_at=generated_at)
        for pool in pools:
            builder.add_pool(pool)
        for policy in policies:
            builder.add_policy(policy)
        for claim in claims:
            builder.add_claim(claim)
        return builder
