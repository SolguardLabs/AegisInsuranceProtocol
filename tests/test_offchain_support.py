from aegis_protocol import ClaimReviewBook, PremiumEngine, ReportBuilder
from aegis_protocol.claims import allocation_for_claim
from aegis_protocol.scenarios import (
    baseline_market,
    build_claim_requests,
    build_ledger_from_scenario,
    scenario_summary,
)


def test_scenario_builds_ledger_and_quotes_premium():
    scenario = baseline_market()
    ledger = build_ledger_from_scenario(scenario)
    summary = scenario_summary(scenario)

    assert summary["pool_count"] == 2
    assert summary["policy_count"] == 1
    assert ledger.pool_exposure(1) == 200 * 10**18
    assert ledger.pool_exposure(2) == 100 * 10**18
    assert ledger.policy_allocation(1, 1) == 200 * 10**18
    assert ledger.policy_allocation(1, 2) == 100 * 10**18

    premium_engine = PremiumEngine()
    policy = ledger.policies[1]
    assert premium_engine.protocol_fee(policy.premium) == policy.premium // 10


def test_claim_review_recommendation_uses_evidence_and_product_terms():
    scenario = baseline_market()
    ledger = build_ledger_from_scenario(scenario)
    request = build_claim_requests(scenario)[0]
    product = scenario.product("ETH-STABLE-VAULT")
    incident = scenario.incident("oracle-confirmed-loss")

    book = ClaimReviewBook()
    book.submit(request)
    for evidence in scenario.claims[0].evidence:
        book.attach_evidence(request.claim_id, evidence)

    decision = book.recommendation(
        request.claim_id,
        ledger.policies[1],
        product,
        incident,
        reviewer=scenario.account("reviewer").address,
    )

    assert decision.approved is True
    assert decision.approved_amount == product.net_payout(request.amount_requested)
    assert allocation_for_claim(ledger.policies[1], request.amount_requested) == (
        (1, 80 * 10**18),
        (2, 40 * 10**18),
    )


def test_report_builder_exports_aggregate_state():
    scenario = baseline_market()
    ledger = build_ledger_from_scenario(scenario)
    requests = build_claim_requests(scenario)
    builder = ReportBuilder.from_state(
        generated_at=scenario.timestamp,
        pools=list(ledger.pools.values()),
        policies=list(ledger.policies.values()),
        claims=list(requests),
    )
    report = builder.build()

    assert report.total_capital > 1_700 * 10**18
    assert report.total_locked == 300 * 10**18
    assert report.aggregate_utilization_bps > 0
    assert "Aegis Exposure Report" in report.to_markdown()
    assert report.pools_csv().splitlines()[0].startswith("pool_id,total_capital")
