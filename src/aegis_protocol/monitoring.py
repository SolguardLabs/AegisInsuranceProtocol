from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

from .constants import BPS_DENOMINATOR
from .models import ClaimRequest, PolicySnapshot, RiskPoolState


class RiskFlag(StrEnum):
    EXPOSURE_MISMATCH = "EXPOSURE_MISMATCH"
    CLAIM_ALLOCATION_MISMATCH = "CLAIM_ALLOCATION_MISMATCH"
    UTILIZATION_HIGH = "UTILIZATION_HIGH"
    SOLVENCY_LOW = "SOLVENCY_LOW"
    CLAIM_BACKLOG_HIGH = "CLAIM_BACKLOG_HIGH"
    SUBJECT_CONCENTRATION_HIGH = "SUBJECT_CONCENTRATION_HIGH"


@dataclass(frozen=True)
class MonitoringLimits:
    utilization_alert_bps: int = 8_000
    minimum_solvency_bps: int = 12_500
    maximum_claim_backlog_bps: int = 2_500
    maximum_subject_concentration_bps: int = 4_000
    accounting_tolerance: int = 0

    def validate(self) -> None:
        for name, value in (
            ("utilization_alert_bps", self.utilization_alert_bps),
            ("maximum_claim_backlog_bps", self.maximum_claim_backlog_bps),
            ("maximum_subject_concentration_bps", self.maximum_subject_concentration_bps),
        ):
            if not 0 <= value <= BPS_DENOMINATOR:
                raise ValueError(f"{name} out of range")
        if self.minimum_solvency_bps < BPS_DENOMINATOR:
            raise ValueError("minimum_solvency_bps cannot be below 100%")
        if self.accounting_tolerance < 0:
            raise ValueError("accounting_tolerance cannot be negative")


@dataclass(frozen=True)
class PoolMonitoringRow:
    pool_id: int
    recorded_exposure: int
    derived_exposure: int
    exposure_gap: int
    recorded_pending_claims: int
    derived_pending_claims: int
    pending_claim_gap: int
    utilization_bps: int
    solvency_bps: int
    claim_backlog_bps: int
    largest_subject_bps: int
    flags: tuple[RiskFlag, ...]

    @property
    def healthy(self) -> bool:
        return not self.flags


@dataclass(frozen=True)
class MonitoringSnapshot:
    generated_at: int
    pools: tuple[PoolMonitoringRow, ...]

    @property
    def healthy(self) -> bool:
        return all(row.healthy for row in self.pools)

    @property
    def flags(self) -> tuple[RiskFlag, ...]:
        return tuple(sorted({flag for row in self.pools for flag in row.flags}, key=str))


class ExposureMonitor:
    def evaluate(
        self,
        generated_at: int,
        pools: Iterable[RiskPoolState],
        policies: Iterable[PolicySnapshot],
        claims: Iterable[ClaimRequest] = (),
        claim_allocations: Mapping[int, tuple[tuple[int, int], ...]] | None = None,
        limits: MonitoringLimits = MonitoringLimits(),
    ) -> MonitoringSnapshot:
        if generated_at < 0:
            raise ValueError("generated_at cannot be negative")
        limits.validate()
        pool_rows = tuple(pools)
        policy_rows = tuple(policies)
        claim_rows = tuple(claims)
        allocations = claim_allocations or {}
        for pool in pool_rows:
            pool.validate()
        for policy in policy_rows:
            policy.validate()
        for claim in claim_rows:
            claim.validate()

        derived_exposure, by_subject = self._derive_policy_exposure(policy_rows)
        derived_claims = self._derive_pending_claims(claim_rows, allocations)
        rows = tuple(
            self._pool_row(
                pool,
                derived_exposure.get(pool.pool_id, 0),
                derived_claims.get(pool.pool_id, 0),
                by_subject.get(pool.pool_id, {}),
                limits,
            )
            for pool in sorted(pool_rows, key=lambda item: item.pool_id)
        )
        return MonitoringSnapshot(generated_at=generated_at, pools=rows)

    def _derive_policy_exposure(
        self,
        policies: tuple[PolicySnapshot, ...],
    ) -> tuple[dict[int, int], dict[int, dict[str, int]]]:
        totals: dict[int, int] = {}
        subjects: dict[int, dict[str, int]] = {}
        for policy in policies:
            if not policy.is_active:
                continue
            for pool_id, amount in policy.allocation_table():
                totals[pool_id] = totals.get(pool_id, 0) + amount
                pool_subjects = subjects.setdefault(pool_id, {})
                pool_subjects[policy.subject] = pool_subjects.get(policy.subject, 0) + amount
        return totals, subjects

    def _derive_pending_claims(
        self,
        claims: tuple[ClaimRequest, ...],
        allocations: Mapping[int, tuple[tuple[int, int], ...]],
    ) -> dict[int, int]:
        totals: dict[int, int] = {}
        for claim in claims:
            if not claim.is_open:
                continue
            for pool_id, amount in allocations.get(claim.claim_id, ()):
                if pool_id <= 0 or amount < 0:
                    raise ValueError("claim allocation is invalid")
                totals[pool_id] = totals.get(pool_id, 0) + amount
        return totals

    def _pool_row(
        self,
        pool: RiskPoolState,
        derived_exposure: int,
        derived_pending: int,
        subject_exposures: Mapping[str, int],
        limits: MonitoringLimits,
    ) -> PoolMonitoringRow:
        exposure_gap = abs(pool.locked_exposure - derived_exposure)
        pending_gap = abs(pool.pending_claims - derived_pending)
        claim_backlog_bps = (
            0
            if pool.total_capital == 0
            else pool.pending_claims * BPS_DENOMINATOR // pool.total_capital
        )
        largest_subject_bps = (
            0
            if pool.locked_exposure == 0 or not subject_exposures
            else max(subject_exposures.values()) * BPS_DENOMINATOR // pool.locked_exposure
        )

        flags: list[RiskFlag] = []
        if exposure_gap > limits.accounting_tolerance:
            flags.append(RiskFlag.EXPOSURE_MISMATCH)
        if pending_gap > limits.accounting_tolerance:
            flags.append(RiskFlag.CLAIM_ALLOCATION_MISMATCH)
        if pool.utilization_bps >= limits.utilization_alert_bps:
            flags.append(RiskFlag.UTILIZATION_HIGH)
        if pool.solvency_bps < limits.minimum_solvency_bps:
            flags.append(RiskFlag.SOLVENCY_LOW)
        if claim_backlog_bps > limits.maximum_claim_backlog_bps:
            flags.append(RiskFlag.CLAIM_BACKLOG_HIGH)
        if largest_subject_bps > limits.maximum_subject_concentration_bps:
            flags.append(RiskFlag.SUBJECT_CONCENTRATION_HIGH)

        return PoolMonitoringRow(
            pool_id=pool.pool_id,
            recorded_exposure=pool.locked_exposure,
            derived_exposure=derived_exposure,
            exposure_gap=exposure_gap,
            recorded_pending_claims=pool.pending_claims,
            derived_pending_claims=derived_pending,
            pending_claim_gap=pending_gap,
            utilization_bps=pool.utilization_bps,
            solvency_bps=pool.solvency_bps,
            claim_backlog_bps=claim_backlog_bps,
            largest_subject_bps=largest_subject_bps,
            flags=tuple(flags),
        )
