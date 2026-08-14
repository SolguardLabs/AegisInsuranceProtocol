from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
from typing import Iterable

from .constants import BPS_DENOMINATOR, clamp_bps


@dataclass(frozen=True)
class ExposureCell:
    pool_id: int
    product_code: str
    subject: str
    amount: int
    probability_bps: int
    severity_bps: int

    def validate(self) -> None:
        if self.pool_id <= 0:
            raise ValueError("pool_id must be positive")
        if not self.product_code or not self.subject:
            raise ValueError("product_code and subject are required")
        if self.amount <= 0:
            raise ValueError("exposure amount must be positive")
        if not 0 <= self.probability_bps <= BPS_DENOMINATOR:
            raise ValueError("probability_bps out of range")
        if not 0 <= self.severity_bps <= BPS_DENOMINATOR:
            raise ValueError("severity_bps out of range")

    @property
    def expected_loss(self) -> int:
        return (
            self.amount
            * self.probability_bps
            * self.severity_bps
            // BPS_DENOMINATOR
            // BPS_DENOMINATOR
        )

    @property
    def standalone_loss(self) -> int:
        return self.amount * self.severity_bps // BPS_DENOMINATOR


@dataclass(frozen=True)
class CapitalStressScenario:
    incident_shock_bps: int
    claim_inflation_bps: int
    liquidity_haircut_bps: int
    common_correlation_bps: int
    expense_buffer_bps: int
    concentration_charge_bps: int

    def validate(self) -> None:
        for name, value in (
            ("incident_shock_bps", self.incident_shock_bps),
            ("claim_inflation_bps", self.claim_inflation_bps),
            ("liquidity_haircut_bps", self.liquidity_haircut_bps),
            ("common_correlation_bps", self.common_correlation_bps),
            ("expense_buffer_bps", self.expense_buffer_bps),
            ("concentration_charge_bps", self.concentration_charge_bps),
        ):
            if not 0 <= value <= BPS_DENOMINATOR:
                raise ValueError(f"{name} out of range")


DEFAULT_CAPITAL_STRESS = CapitalStressScenario(
    incident_shock_bps=2_000,
    claim_inflation_bps=1_250,
    liquidity_haircut_bps=750,
    common_correlation_bps=3_500,
    expense_buffer_bps=1_000,
    concentration_charge_bps=500,
)


@dataclass(frozen=True)
class CapitalAssessment:
    available_capital: int
    liquid_capital: int
    gross_exposure: int
    expected_loss: int
    correlated_loss: int
    stressed_loss: int
    concentration_charge: int
    required_capital: int
    capital_after_stress: int
    shortfall: int
    coverage_ratio_bps: int
    largest_subject_bps: int
    exposure_count: int

    @property
    def solvent(self) -> bool:
        return self.shortfall == 0


class CapitalModel:
    def assess(
        self,
        available_capital: int,
        exposures: Iterable[ExposureCell],
        scenario: CapitalStressScenario = DEFAULT_CAPITAL_STRESS,
    ) -> CapitalAssessment:
        if available_capital < 0:
            raise ValueError("available_capital cannot be negative")
        scenario.validate()
        cells = tuple(exposures)
        for cell in cells:
            cell.validate()

        gross_exposure = sum(cell.amount for cell in cells)
        expected_loss = sum(cell.expected_loss for cell in cells)
        standalone_losses = tuple(cell.standalone_loss for cell in cells)
        correlated_loss = self._correlated_loss(
            standalone_losses,
            scenario.common_correlation_bps,
        )

        stressed_losses = tuple(self._stress_cell(cell, scenario) for cell in cells)
        stressed_loss = self._correlated_loss(
            stressed_losses,
            scenario.common_correlation_bps,
        )
        concentration_charge = (
            max(stressed_losses, default=0)
            * scenario.concentration_charge_bps
            // BPS_DENOMINATOR
        )
        expense_buffer = stressed_loss * scenario.expense_buffer_bps // BPS_DENOMINATOR
        required_capital = max(expected_loss, correlated_loss) + concentration_charge + expense_buffer

        liquid_capital = (
            available_capital
            * (BPS_DENOMINATOR - scenario.liquidity_haircut_bps)
            // BPS_DENOMINATOR
        )
        capital_after_stress = max(0, liquid_capital - stressed_loss)
        shortfall = max(0, required_capital - capital_after_stress)
        coverage_ratio_bps = (
            BPS_DENOMINATOR
            if required_capital == 0
            else liquid_capital * BPS_DENOMINATOR // required_capital
        )
        largest_subject_bps = self._largest_subject_bps(cells, gross_exposure)

        return CapitalAssessment(
            available_capital=available_capital,
            liquid_capital=liquid_capital,
            gross_exposure=gross_exposure,
            expected_loss=expected_loss,
            correlated_loss=correlated_loss,
            stressed_loss=stressed_loss,
            concentration_charge=concentration_charge,
            required_capital=required_capital,
            capital_after_stress=capital_after_stress,
            shortfall=shortfall,
            coverage_ratio_bps=coverage_ratio_bps,
            largest_subject_bps=largest_subject_bps,
            exposure_count=len(cells),
        )

    def _stress_cell(self, cell: ExposureCell, scenario: CapitalStressScenario) -> int:
        stressed_severity = clamp_bps(cell.severity_bps + scenario.incident_shock_bps)
        base_loss = cell.amount * stressed_severity // BPS_DENOMINATOR
        return (
            base_loss
            * (BPS_DENOMINATOR + scenario.claim_inflation_bps)
            // BPS_DENOMINATOR
        )

    def _correlated_loss(self, losses: Iterable[int], correlation_bps: int) -> int:
        values = tuple(losses)
        if not values:
            return 0
        square_sum = sum(value * value for value in values)
        aggregate = sum(values)
        cross_terms = max(0, aggregate * aggregate - square_sum)
        variance = square_sum + cross_terms * correlation_bps // BPS_DENOMINATOR
        return isqrt(variance)

    def _largest_subject_bps(
        self,
        cells: tuple[ExposureCell, ...],
        gross_exposure: int,
    ) -> int:
        if gross_exposure == 0:
            return 0
        by_subject: dict[str, int] = {}
        for cell in cells:
            by_subject[cell.subject] = by_subject.get(cell.subject, 0) + cell.amount
        return max(by_subject.values()) * BPS_DENOMINATOR // gross_exposure
