from __future__ import annotations

from dataclasses import dataclass

from .claims import EvidenceItem, EvidenceKind
from .constants import PRODUCT_TEMPLATES, jurisdiction_profile, product_template
from .ledger import CapitalLedger
from .models import (
    ClaimRequest,
    CoverageProduct,
    IncidentSignal,
    PoolConfig,
    RiskPoolState,
    UnderwriterAccount,
)
from .pricing import RiskObservation


@dataclass(frozen=True)
class ScenarioAccount:
    label: str
    address: str
    balance: int


@dataclass(frozen=True)
class ScenarioPool:
    config: PoolConfig
    sponsor: ScenarioAccount
    deposits: tuple[tuple[ScenarioAccount, int], ...]


@dataclass(frozen=True)
class ScenarioPolicyOrder:
    holder: ScenarioAccount
    beneficiary: ScenarioAccount
    pool_id: int
    product_code: str
    subject: str
    coverage: int
    duration_days: int
    risk_score_bps: int
    jurisdiction_haircut_bps: int


@dataclass(frozen=True)
class ScenarioCessionOrder:
    policy_index: int
    to_pool_id: int
    amount: int


@dataclass(frozen=True)
class ScenarioClaimOrder:
    policy_index: int
    claimant: ScenarioAccount
    amount: int
    incident_hash: str
    evidence_hash: str
    evidence: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class MarketScenario:
    name: str
    timestamp: int
    accounts: tuple[ScenarioAccount, ...]
    pools: tuple[ScenarioPool, ...]
    products: tuple[CoverageProduct, ...]
    policies: tuple[ScenarioPolicyOrder, ...]
    cessions: tuple[ScenarioCessionOrder, ...]
    incidents: tuple[IncidentSignal, ...]
    claims: tuple[ScenarioClaimOrder, ...]
    observations: tuple[RiskObservation, ...]

    def account(self, label: str) -> ScenarioAccount:
        for account in self.accounts:
            if account.label == label:
                return account
        raise KeyError(f"scenario account not found: {label}")

    def product(self, code: str) -> CoverageProduct:
        for product in self.products:
            if product.code == code:
                return product
        raise KeyError(f"scenario product not found: {code}")

    def incident(self, incident_hash: str) -> IncidentSignal:
        for incident in self.incidents:
            if incident.incident_hash == incident_hash:
                return incident
        raise KeyError(f"scenario incident not found: {incident_hash}")


def account(label: str, balance: int = 1_000 * 10**18) -> ScenarioAccount:
    suffix = abs(hash(label)) % 10**16
    return ScenarioAccount(label=label, address=f"0x{suffix:040x}", balance=balance)


def product_from_template(product_id: int, code: str) -> CoverageProduct:
    template = product_template(code)
    return CoverageProduct(
        product_id=product_id,
        code=template.code,
        label=template.label,
        base_rate_bps=template.base_rate_bps,
        min_premium=10**15,
        deductible_bps=template.deductible_bps,
        claim_window_days=template.claim_window_days,
        max_cover=template.max_cover_wei,
        active=True,
        tags=("scenario", template.code.lower()),
    )


def baseline_market() -> MarketScenario:
    sponsor = account("sponsor")
    senior = account("senior-underwriter", 2_000 * 10**18)
    specialty = account("specialty-underwriter", 1_500 * 10**18)
    holder = account("vault-operator")
    beneficiary = account("beneficiary")
    reviewer = account("reviewer")

    product = product_from_template(1, "ETH-STABLE-VAULT")
    profile = jurisdiction_profile("EU")
    pool_a = ScenarioPool(
        config=PoolConfig(
            pool_id=1,
            label="Senior A",
            jurisdiction=profile.code,
            min_capital=0,
            max_utilization_bps=9_000,
            retention_bps=7_000,
        ),
        sponsor=sponsor,
        deposits=((senior, 1_000 * 10**18),),
    )
    pool_b = ScenarioPool(
        config=PoolConfig(
            pool_id=2,
            label="Specialty B",
            jurisdiction=profile.code,
            min_capital=0,
            max_utilization_bps=8_500,
            retention_bps=6_500,
        ),
        sponsor=sponsor,
        deposits=((specialty, 700 * 10**18),),
    )
    policy = ScenarioPolicyOrder(
        holder=holder,
        beneficiary=beneficiary,
        pool_id=1,
        product_code=product.code,
        subject="vault-alpha",
        coverage=300 * 10**18,
        duration_days=90,
        risk_score_bps=2_700,
        jurisdiction_haircut_bps=profile.capital_haircut_bps,
    )
    cession = ScenarioCessionOrder(policy_index=0, to_pool_id=2, amount=100 * 10**18)
    incident = IncidentSignal(
        incident_hash="oracle-confirmed-loss",
        product_code=product.code,
        subject="vault-alpha",
        opened_at=1_700_010_000,
        active=True,
        severity_bps=4_500,
        sources=("oracle", "keeper", "vault-log"),
    )
    evidence = (
        EvidenceItem(
            kind=EvidenceKind.ORACLE,
            reference="oracle-round-884200",
            submitted_by=reviewer.address,
            confidence_bps=9_200,
            timestamp=1_700_010_100,
        ),
        EvidenceItem(
            kind=EvidenceKind.VAULT_LOG,
            reference="vault-alpha-loss-42",
            submitted_by=holder.address,
            confidence_bps=8_500,
            timestamp=1_700_010_120,
        ),
    )
    claim = ScenarioClaimOrder(
        policy_index=0,
        claimant=beneficiary,
        amount=120 * 10**18,
        incident_hash=incident.incident_hash,
        evidence_hash="bundle-120",
        evidence=evidence,
    )
    observation = RiskObservation(
        timestamp=1_700_000_000,
        subject="vault-alpha",
        oracle_latency_ms=4_000,
        peg_deviation_bps=35,
        admin_action_count=2,
        liquidity_depth=20_000 * 10**18,
        failed_heartbeat_count=0,
    )
    return MarketScenario(
        name="baseline-market",
        timestamp=1_700_000_000,
        accounts=(sponsor, senior, specialty, holder, beneficiary, reviewer),
        pools=(pool_a, pool_b),
        products=(product,),
        policies=(policy,),
        cessions=(cession,),
        incidents=(incident,),
        claims=(claim,),
        observations=(observation,),
    )


def high_utilization_market() -> MarketScenario:
    base = baseline_market()
    extra_product = product_from_template(2, "ORACLE-DEPEG")
    extra_policy = ScenarioPolicyOrder(
        holder=base.account("vault-operator"),
        beneficiary=base.account("beneficiary"),
        pool_id=1,
        product_code=extra_product.code,
        subject="vault-beta",
        coverage=420 * 10**18,
        duration_days=120,
        risk_score_bps=5_400,
        jurisdiction_haircut_bps=300,
    )
    return MarketScenario(
        name="high-utilization-market",
        timestamp=base.timestamp,
        accounts=base.accounts,
        pools=base.pools,
        products=(base.products[0], extra_product),
        policies=base.policies + (extra_policy,),
        cessions=base.cessions,
        incidents=base.incidents,
        claims=base.claims,
        observations=base.observations
        + (
            RiskObservation(
                timestamp=1_700_000_600,
                subject="vault-beta",
                oracle_latency_ms=12_000,
                peg_deviation_bps=120,
                admin_action_count=4,
                liquidity_depth=7_500 * 10**18,
                failed_heartbeat_count=1,
            ),
        ),
    )


def scenario_products() -> tuple[CoverageProduct, ...]:
    return tuple(product_from_template(index + 1, template.code) for index, template in enumerate(PRODUCT_TEMPLATES))


def build_ledger_from_scenario(scenario: MarketScenario) -> CapitalLedger:
    ledger = CapitalLedger()
    for pool in scenario.pools:
        ledger.add_pool(
            pool.config,
            RiskPoolState(
                pool_id=pool.config.pool_id,
                total_capital=0,
                locked_exposure=0,
                max_utilization_bps=pool.config.max_utilization_bps,
            ),
        )
        for provider, amount in pool.deposits:
            ledger.deposit(pool.config.pool_id, provider.address, amount)
    for order in scenario.policies:
        product = scenario.product(order.product_code)
        ledger.issue_policy(
            holder=order.holder.address,
            beneficiary=order.beneficiary.address,
            pool_id=order.pool_id,
            product=product,
            subject=order.subject,
            coverage=order.coverage,
            duration_days=order.duration_days,
            start_time=scenario.timestamp,
            risk_score_bps=order.risk_score_bps,
            jurisdiction_haircut_bps=order.jurisdiction_haircut_bps,
        )
    for order in scenario.cessions:
        policy_id = order.policy_index + 1
        ledger.transfer_exposure(policy_id, order.to_pool_id, order.amount)
    return ledger


def build_claim_requests(scenario: MarketScenario) -> tuple[ClaimRequest, ...]:
    requests: list[ClaimRequest] = []
    for index, order in enumerate(scenario.claims, start=1):
        policy_order = scenario.policies[order.policy_index]
        requests.append(
            ClaimRequest(
                claim_id=index,
                policy_id=order.policy_index + 1,
                claimant=order.claimant.address,
                beneficiary=policy_order.beneficiary.address,
                amount_requested=order.amount,
                incident_hash=order.incident_hash,
                evidence_hash=order.evidence_hash,
                submitted_at=scenario.timestamp + 10_000,
            )
        )
    return tuple(requests)


def scenario_matrix() -> tuple[MarketScenario, ...]:
    return (baseline_market(), high_utilization_market())


def scenario_capital_by_pool(scenario: MarketScenario) -> dict[int, int]:
    totals: dict[int, int] = {}
    for pool in scenario.pools:
        pool_total = 0
        for _, amount in pool.deposits:
            pool_total += amount
        totals[pool.config.pool_id] = pool_total
    return totals


def scenario_requested_cover_by_pool(scenario: MarketScenario) -> dict[int, int]:
    totals: dict[int, int] = {}
    for policy in scenario.policies:
        totals[policy.pool_id] = totals.get(policy.pool_id, 0) + policy.coverage
    return totals


def scenario_claims_by_policy(scenario: MarketScenario) -> dict[int, int]:
    totals: dict[int, int] = {}
    for claim in scenario.claims:
        policy_id = claim.policy_index + 1
        totals[policy_id] = totals.get(policy_id, 0) + claim.amount
    return totals


def scenario_subjects(scenario: MarketScenario) -> tuple[str, ...]:
    subjects = {policy.subject for policy in scenario.policies}
    subjects.update(incident.subject for incident in scenario.incidents)
    subjects.update(observation.subject for observation in scenario.observations)
    return tuple(sorted(subjects))


def scenario_summary(scenario: MarketScenario) -> dict[str, int | str]:
    capital = scenario_capital_by_pool(scenario)
    cover = scenario_requested_cover_by_pool(scenario)
    claims = scenario_claims_by_policy(scenario)
    return {
        "name": scenario.name,
        "pool_count": len(scenario.pools),
        "product_count": len(scenario.products),
        "policy_count": len(scenario.policies),
        "claim_count": len(scenario.claims),
        "total_capital": sum(capital.values()),
        "total_requested_cover": sum(cover.values()),
        "total_claim_amount": sum(claims.values()),
        "subject_count": len(scenario_subjects(scenario)),
    }
