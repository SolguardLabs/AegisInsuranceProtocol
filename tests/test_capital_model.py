from dataclasses import replace

from aegis_protocol import (
    DEFAULT_CAPITAL_STRESS,
    CapitalModel,
    CapitalStressScenario,
    ExposureCell,
    ExposureMonitor,
    MonitoringLimits,
    RiskFlag,
)
from aegis_protocol.scenarios import baseline_market, build_ledger_from_scenario


ETHER = 10**18


def exposure_cells():
    return (
        ExposureCell(1, "ETH-STABLE", "vault-alpha", 300 * ETHER, 900, 6_000),
        ExposureCell(1, "ETH-STABLE", "bridge-beta", 180 * ETHER, 650, 4_500),
        ExposureCell(2, "RESTAKING", "operator-gamma", 220 * ETHER, 1_200, 7_500),
    )


def test_capital_model_reconciles_correlated_stress_components():
    assessment = CapitalModel().assess(1_500 * ETHER, exposure_cells())

    assert assessment.gross_exposure == 700 * ETHER
    assert assessment.expected_loss > 0
    assert assessment.correlated_loss >= max(cell.standalone_loss for cell in exposure_cells())
    assert assessment.stressed_loss > assessment.correlated_loss
    assert assessment.required_capital > assessment.concentration_charge
    assert assessment.coverage_ratio_bps > 10_000
    assert assessment.solvent is True


def test_common_correlation_increases_the_modeled_tail():
    model = CapitalModel()
    uncorrelated = model.assess(
        1_500 * ETHER,
        exposure_cells(),
        replace(DEFAULT_CAPITAL_STRESS, common_correlation_bps=0),
    )
    correlated = model.assess(
        1_500 * ETHER,
        exposure_cells(),
        replace(DEFAULT_CAPITAL_STRESS, common_correlation_bps=7_500),
    )

    assert correlated.correlated_loss > uncorrelated.correlated_loss
    assert correlated.stressed_loss > uncorrelated.stressed_loss


def test_severe_liquidity_and_incident_shocks_surface_a_shortfall():
    scenario = CapitalStressScenario(
        incident_shock_bps=3_000,
        claim_inflation_bps=2_000,
        liquidity_haircut_bps=3_000,
        common_correlation_bps=7_500,
        expense_buffer_bps=1_500,
        concentration_charge_bps=1_000,
    )
    assessment = CapitalModel().assess(250 * ETHER, exposure_cells(), scenario)

    assert assessment.shortfall > 0
    assert assessment.capital_after_stress < assessment.required_capital
    assert assessment.solvent is False


def test_monitor_reconciles_policy_allocations_against_pool_ledgers():
    scenario = baseline_market()
    ledger = build_ledger_from_scenario(scenario)
    snapshot = ExposureMonitor().evaluate(
        generated_at=scenario.timestamp,
        pools=ledger.pools.values(),
        policies=ledger.policies.values(),
        limits=MonitoringLimits(
            minimum_solvency_bps=10_000,
            maximum_subject_concentration_bps=10_000,
        ),
    )

    assert snapshot.healthy is True
    assert all(row.exposure_gap == 0 for row in snapshot.pools)


def test_monitor_flags_accounting_drift_and_concentration():
    scenario = baseline_market()
    ledger = build_ledger_from_scenario(scenario)
    pool = ledger.pools[1]
    ledger.pools[1] = replace(pool, locked_exposure=pool.locked_exposure - ETHER)

    snapshot = ExposureMonitor().evaluate(
        generated_at=scenario.timestamp,
        pools=ledger.pools.values(),
        policies=ledger.policies.values(),
    )

    assert snapshot.healthy is False
    assert RiskFlag.EXPOSURE_MISMATCH in snapshot.flags
    assert RiskFlag.SUBJECT_CONCENTRATION_HIGH in snapshot.flags
