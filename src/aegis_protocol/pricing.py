from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from .constants import BPS_DENOMINATOR, YEAR_DAYS, clamp_bps, risk_band_for_score
from .models import CoverageProduct, PoolConfig, RiskPoolState, validate_duration, weighted_average_bps


@dataclass(frozen=True)
class PremiumBreakdown:
    base_premium: int
    utilization_premium: int
    risk_premium: int
    jurisdiction_premium: int
    minimum_adjustment: int
    final_premium: int

    @property
    def variable_total(self) -> int:
        return self.base_premium + self.utilization_premium + self.risk_premium + self.jurisdiction_premium

    @property
    def was_minimum_applied(self) -> bool:
        return self.minimum_adjustment > 0

    def as_dict(self) -> dict[str, int]:
        return {
            "base_premium": self.base_premium,
            "utilization_premium": self.utilization_premium,
            "risk_premium": self.risk_premium,
            "jurisdiction_premium": self.jurisdiction_premium,
            "minimum_adjustment": self.minimum_adjustment,
            "final_premium": self.final_premium,
        }


@dataclass(frozen=True)
class PricingInput:
    product: CoverageProduct
    pool: RiskPoolState
    pool_config: PoolConfig
    coverage: int
    duration_days: int
    risk_score_bps: int = 0
    jurisdiction_haircut_bps: int = 0
    broker_discount_bps: int = 0

    def validate(self) -> None:
        self.product.validate()
        self.pool.validate()
        self.pool_config.validate()
        validate_duration(self.duration_days)
        if self.coverage <= 0:
            raise ValueError("coverage must be positive")
        if not self.product.allows_cover(self.coverage):
            raise ValueError("coverage exceeds product cap")
        if self.coverage > self.pool.available_capacity:
            raise ValueError("coverage exceeds pool capacity")
        for value in [self.risk_score_bps, self.jurisdiction_haircut_bps, self.broker_discount_bps]:
            if value < 0 or value > BPS_DENOMINATOR:
                raise ValueError("bps value out of range")


@dataclass
class PremiumEngine:
    protocol_fee_bps: int = 1_000
    utilization_divisor: int = 25
    risk_loading_floor_bps: int = 0
    product_overrides: dict[str, int] = field(default_factory=dict)

    def quote(self, pricing_input: PricingInput) -> PremiumBreakdown:
        pricing_input.validate()
        product = pricing_input.product
        coverage = pricing_input.coverage
        duration_days = pricing_input.duration_days

        base_rate_bps = self.product_overrides.get(product.code, product.base_rate_bps)
        base_premium = coverage * base_rate_bps * duration_days // YEAR_DAYS // BPS_DENOMINATOR
        utilization_premium = (
            coverage * pricing_input.pool.utilization_bps // BPS_DENOMINATOR // self.utilization_divisor
        )
        risk_premium = self.risk_loading(coverage, pricing_input.risk_score_bps)
        jurisdiction_premium = coverage * pricing_input.jurisdiction_haircut_bps // BPS_DENOMINATOR
        discount = (
            (base_premium + utilization_premium + risk_premium + jurisdiction_premium)
            * pricing_input.broker_discount_bps
            // BPS_DENOMINATOR
        )
        variable_total = base_premium + utilization_premium + risk_premium + jurisdiction_premium - discount
        if variable_total < product.min_premium:
            minimum_adjustment = product.min_premium - variable_total
            final_premium = product.min_premium
        else:
            minimum_adjustment = 0
            final_premium = variable_total
        return PremiumBreakdown(
            base_premium=base_premium,
            utilization_premium=utilization_premium,
            risk_premium=risk_premium,
            jurisdiction_premium=jurisdiction_premium,
            minimum_adjustment=minimum_adjustment,
            final_premium=final_premium,
        )

    def risk_loading(self, coverage: int, risk_score_bps: int) -> int:
        if coverage < 0:
            raise ValueError("coverage cannot be negative")
        score = clamp_bps(risk_score_bps)
        band = risk_band_for_score(score)
        loading_bps = max(self.risk_loading_floor_bps, band.capital_buffer_bps - BPS_DENOMINATOR // 10)
        return coverage * score * loading_bps // BPS_DENOMINATOR // BPS_DENOMINATOR

    def protocol_fee(self, premium: int) -> int:
        if premium < 0:
            raise ValueError("premium cannot be negative")
        return premium * clamp_bps(self.protocol_fee_bps) // BPS_DENOMINATOR

    def pool_premium(self, premium: int) -> int:
        return premium - self.protocol_fee(premium)

    def quote_many(self, inputs: list[PricingInput]) -> list[PremiumBreakdown]:
        return [self.quote(item) for item in inputs]

    def blended_rate_bps(self, quotes: list[PremiumBreakdown], coverages: list[int]) -> int:
        if len(quotes) != len(coverages):
            raise ValueError("quotes and coverages length mismatch")
        weighted: list[tuple[int, int]] = []
        for quote, coverage in zip(quotes, coverages, strict=True):
            if coverage <= 0:
                raise ValueError("coverage must be positive")
            rate = quote.final_premium * BPS_DENOMINATOR // coverage
            weighted.append((rate, coverage))
        return weighted_average_bps(weighted)

    def minimum_capital_for_target_utilization(self, coverage: int, target_utilization_bps: int) -> int:
        if coverage <= 0:
            raise ValueError("coverage must be positive")
        target = clamp_bps(target_utilization_bps)
        if target == 0:
            raise ValueError("target utilization cannot be zero")
        return coverage * BPS_DENOMINATOR // target


@dataclass(frozen=True)
class RiskObservation:
    timestamp: int
    subject: str
    oracle_latency_ms: int
    peg_deviation_bps: int
    admin_action_count: int
    liquidity_depth: int
    failed_heartbeat_count: int

    def validate(self) -> None:
        if self.timestamp < 0:
            raise ValueError("timestamp cannot be negative")
        if not self.subject:
            raise ValueError("subject is required")
        if self.oracle_latency_ms < 0:
            raise ValueError("oracle latency cannot be negative")
        if self.peg_deviation_bps < 0:
            raise ValueError("peg deviation cannot be negative")
        if self.admin_action_count < 0 or self.failed_heartbeat_count < 0:
            raise ValueError("counts cannot be negative")
        if self.liquidity_depth < 0:
            raise ValueError("liquidity depth cannot be negative")

    @property
    def latency_score_bps(self) -> int:
        if self.oracle_latency_ms <= 2_000:
            return 250
        if self.oracle_latency_ms <= 10_000:
            return 1_000
        if self.oracle_latency_ms <= 60_000:
            return 2_500
        return 5_000

    @property
    def peg_score_bps(self) -> int:
        return min(7_000, self.peg_deviation_bps * 4)

    @property
    def governance_score_bps(self) -> int:
        return min(5_000, self.admin_action_count * 350)

    @property
    def heartbeat_score_bps(self) -> int:
        return min(6_000, self.failed_heartbeat_count * 800)

    @property
    def liquidity_score_bps(self) -> int:
        if self.liquidity_depth >= 50_000 * 10**18:
            return 200
        if self.liquidity_depth >= 10_000 * 10**18:
            return 800
        if self.liquidity_depth >= 2_000 * 10**18:
            return 1_800
        return 3_500

    def composite_score_bps(self) -> int:
        weighted = [
            (self.latency_score_bps, 2),
            (self.peg_score_bps, 4),
            (self.governance_score_bps, 2),
            (self.heartbeat_score_bps, 3),
            (self.liquidity_score_bps, 3),
        ]
        return weighted_average_bps(weighted)


@dataclass
class RiskOracleBook:
    observations: list[RiskObservation] = field(default_factory=list)

    def add(self, observation: RiskObservation) -> None:
        observation.validate()
        self.observations.append(observation)
        self.observations.sort(key=lambda item: item.timestamp)

    def latest_for_subject(self, subject: str) -> RiskObservation | None:
        for observation in reversed(self.observations):
            if observation.subject == subject:
                return observation
        return None

    def score_for_subject(self, subject: str, fallback_bps: int = 0) -> int:
        observation = self.latest_for_subject(subject)
        if observation is None:
            return clamp_bps(fallback_bps)
        return observation.composite_score_bps()

    def rolling_score(self, subject: str, window: int) -> int:
        if window <= 0:
            raise ValueError("window must be positive")
        matches = [item.composite_score_bps() for item in self.observations if item.subject == subject]
        if not matches:
            return 0
        tail = matches[-window:]
        return int(mean(tail))

    def stressed_subjects(self, threshold_bps: int) -> tuple[str, ...]:
        threshold = clamp_bps(threshold_bps)
        result: list[str] = []
        seen: set[str] = set()
        for observation in reversed(self.observations):
            if observation.subject in seen:
                continue
            seen.add(observation.subject)
            if observation.composite_score_bps() >= threshold:
                result.append(observation.subject)
        return tuple(sorted(result))


def make_pricing_input(
    product: CoverageProduct,
    pool: RiskPoolState,
    pool_config: PoolConfig,
    coverage: int,
    duration_days: int,
    risk_score_bps: int = 0,
    jurisdiction_haircut_bps: int = 0,
    broker_discount_bps: int = 0,
) -> PricingInput:
    return PricingInput(
        product=product,
        pool=pool,
        pool_config=pool_config,
        coverage=coverage,
        duration_days=duration_days,
        risk_score_bps=risk_score_bps,
        jurisdiction_haircut_bps=jurisdiction_haircut_bps,
        broker_discount_bps=broker_discount_bps,
    )
