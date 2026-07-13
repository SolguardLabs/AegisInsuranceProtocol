from __future__ import annotations

from dataclasses import dataclass


BPS_DENOMINATOR = 10_000
SECONDS_PER_DAY = 86_400
YEAR_DAYS = 365
MAX_POLICY_DAYS = 730
MIN_POLICY_DAYS = 1
MAX_CESSION_SLOTS = 4

POOL_ACTIVE = "active"
POOL_PAUSED = "paused"
POOL_CLOSED = "closed"

POLICY_ACTIVE = "active"
POLICY_EXPIRED = "expired"
POLICY_CLAIMED = "claimed"
POLICY_CANCELLED = "cancelled"

CLAIM_SUBMITTED = "submitted"
CLAIM_REVIEWED = "reviewed"
CLAIM_APPROVED = "approved"
CLAIM_PAID = "paid"
CLAIM_REJECTED = "rejected"

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"

DEFAULT_POOL_UTILIZATION_BPS = 9_000
DEFAULT_RETENTION_BPS = 7_000
DEFAULT_PROTOCOL_FEE_BPS = 1_000
DEFAULT_DEDUCTIBLE_BPS = 500
DEFAULT_CLAIM_WINDOW_DAYS = 30
DEFAULT_MIN_PREMIUM_WEI = 10**15


@dataclass(frozen=True)
class RiskBand:
    code: str
    lower_bps: int
    upper_bps: int
    capital_buffer_bps: int
    reviewer_quorum: int
    description: str


@dataclass(frozen=True)
class ProductTemplate:
    code: str
    label: str
    base_rate_bps: int
    deductible_bps: int
    claim_window_days: int
    max_cover_wei: int
    target_retention_bps: int
    min_observations: int


@dataclass(frozen=True)
class JurisdictionProfile:
    code: str
    display_name: str
    capital_haircut_bps: int
    dispute_window_days: int
    evidence_floor: int
    notes: tuple[str, ...]


RISK_BANDS: tuple[RiskBand, ...] = (
    RiskBand(
        code=RISK_LOW,
        lower_bps=0,
        upper_bps=2_500,
        capital_buffer_bps=1_100,
        reviewer_quorum=1,
        description="Mature integrations with observable operations and low variance.",
    ),
    RiskBand(
        code=RISK_MEDIUM,
        lower_bps=2_501,
        upper_bps=5_500,
        capital_buffer_bps=1_350,
        reviewer_quorum=2,
        description="Standard DeFi systems with recurring governance or oracle dependencies.",
    ),
    RiskBand(
        code=RISK_HIGH,
        lower_bps=5_501,
        upper_bps=8_000,
        capital_buffer_bps=1_800,
        reviewer_quorum=3,
        description="Complex systems with upgrade, bridge, restaking or correlated vault risk.",
    ),
    RiskBand(
        code=RISK_CRITICAL,
        lower_bps=8_001,
        upper_bps=10_000,
        capital_buffer_bps=2_500,
        reviewer_quorum=4,
        description="Concentrated or distressed systems requiring manual underwriting.",
    ),
)


PRODUCT_TEMPLATES: tuple[ProductTemplate, ...] = (
    ProductTemplate(
        code="ETH-STABLE-VAULT",
        label="Ethereum stablecoin vault cover",
        base_rate_bps=720,
        deductible_bps=500,
        claim_window_days=30,
        max_cover_wei=700 * 10**18,
        target_retention_bps=7_000,
        min_observations=12,
    ),
    ProductTemplate(
        code="LST-OPERATOR",
        label="Liquid staking operator interruption cover",
        base_rate_bps=840,
        deductible_bps=650,
        claim_window_days=45,
        max_cover_wei=500 * 10**18,
        target_retention_bps=6_500,
        min_observations=18,
    ),
    ProductTemplate(
        code="BRIDGE-MESSAGE",
        label="Cross-chain message failure cover",
        base_rate_bps=1_150,
        deductible_bps=750,
        claim_window_days=60,
        max_cover_wei=300 * 10**18,
        target_retention_bps=5_500,
        min_observations=30,
    ),
    ProductTemplate(
        code="ORACLE-DEPEG",
        label="Oracle-driven peg deviation cover",
        base_rate_bps=930,
        deductible_bps=550,
        claim_window_days=21,
        max_cover_wei=600 * 10**18,
        target_retention_bps=6_800,
        min_observations=24,
    ),
    ProductTemplate(
        code="PERPS-CLEARING",
        label="Perpetual market clearing disruption cover",
        base_rate_bps=1_040,
        deductible_bps=800,
        claim_window_days=14,
        max_cover_wei=450 * 10**18,
        target_retention_bps=6_000,
        min_observations=36,
    ),
)


JURISDICTION_PROFILES: tuple[JurisdictionProfile, ...] = (
    JurisdictionProfile(
        code="EU",
        display_name="European operations desk",
        capital_haircut_bps=250,
        dispute_window_days=14,
        evidence_floor=2,
        notes=("entity-reviewed policy wording", "oracle attestation accepted"),
    ),
    JurisdictionProfile(
        code="US",
        display_name="US operations desk",
        capital_haircut_bps=325,
        dispute_window_days=21,
        evidence_floor=3,
        notes=("legal review required for payout memo", "keeper attestation accepted"),
    ),
    JurisdictionProfile(
        code="SG",
        display_name="Singapore operations desk",
        capital_haircut_bps=200,
        dispute_window_days=10,
        evidence_floor=2,
        notes=("fast-track review for oracle-only claims", "board memo required above cap"),
    ),
    JurisdictionProfile(
        code="CH",
        display_name="Swiss operations desk",
        capital_haircut_bps=180,
        dispute_window_days=12,
        evidence_floor=2,
        notes=("private vault logs accepted", "counterparty notification required"),
    ),
)


def clamp_bps(value: int) -> int:
    if value < 0:
        return 0
    if value > BPS_DENOMINATOR:
        return BPS_DENOMINATOR
    return value


def ceil_div(value: int, divisor: int) -> int:
    if divisor <= 0:
        raise ValueError("divisor must be positive")
    return (value + divisor - 1) // divisor


def product_template(code: str) -> ProductTemplate:
    normalized = code.upper()
    for template in PRODUCT_TEMPLATES:
        if template.code == normalized:
            return template
    raise KeyError(f"unknown product template: {code}")


def risk_band_for_score(score_bps: int) -> RiskBand:
    score = clamp_bps(score_bps)
    for band in RISK_BANDS:
        if band.lower_bps <= score <= band.upper_bps:
            return band
    return RISK_BANDS[-1]


def jurisdiction_profile(code: str) -> JurisdictionProfile:
    normalized = code.upper()
    for profile in JURISDICTION_PROFILES:
        if profile.code == normalized:
            return profile
    raise KeyError(f"unknown jurisdiction profile: {code}")
