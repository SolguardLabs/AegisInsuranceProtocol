import boa

from conftest import ETHER, b32, buy_policy


def test_policy_purchase_locks_capacity_and_records_exposure(protocol, accounts, funded_market):
    pool_a, _ = funded_market
    coverage = 250 * ETHER

    policy_id, premium = buy_policy(protocol, accounts, pool_a, coverage)

    summary = protocol.pool_risk_summary(pool_a)
    assert policy_id == 1
    assert premium > 0
    assert summary[0] == 1_000 * ETHER + premium - premium // 10
    assert summary[1] == coverage
    assert protocol.policy_total_exposure(policy_id) == coverage
    assert protocol.policy_pool_allocation(policy_id, pool_a) == coverage
    assert protocol.policy_is_claimable(policy_id) is True


def test_policy_expiration_releases_capacity_after_term(protocol, accounts, funded_market):
    pool_a, _ = funded_market
    coverage = 180 * ETHER
    policy_id, _ = buy_policy(protocol, accounts, pool_a, coverage, duration_days=14)

    assert protocol.pool_risk_summary(pool_a)[1] == coverage

    boa.env.time_travel(seconds=15 * 24 * 60 * 60)
    protocol.expire_policy(policy_id)

    assert protocol.pool_risk_summary(pool_a)[1] == 0
    assert protocol.policy_total_exposure(policy_id) == 0
    assert protocol.free_capital(pool_a) == protocol.pool_risk_summary(pool_a)[0]


def test_exposure_can_be_transferred_to_specialty_pool(protocol, accounts, funded_market):
    pool_a, pool_b = funded_market
    coverage = 300 * ETHER
    policy_id, _ = buy_policy(protocol, accounts, pool_a, coverage, duration_days=60)

    with boa.env.prank(accounts["router"]):
        protocol.transfer_policy_exposure(policy_id, pool_b, 120 * ETHER)

    assert protocol.policy_total_exposure(policy_id) == coverage
    assert protocol.policy_pool_allocation(policy_id, pool_a) == 180 * ETHER
    assert protocol.policy_pool_allocation(policy_id, pool_b) == 120 * ETHER
    assert protocol.pool_risk_summary(pool_a)[1] == 180 * ETHER
    assert protocol.pool_risk_summary(pool_b)[1] == 120 * ETHER
    assert protocol.cession_allocation(policy_id, 0) == (pool_b, 120 * ETHER)


def test_expired_syndicated_policy_releases_each_visible_allocation(protocol, accounts, funded_market):
    pool_a, pool_b = funded_market
    coverage = 300 * ETHER
    policy_id, _ = buy_policy(protocol, accounts, pool_a, coverage, duration_days=21)

    with boa.env.prank(accounts["router"]):
        protocol.transfer_policy_exposure(policy_id, pool_b, 120 * ETHER)

    boa.env.time_travel(seconds=22 * 24 * 60 * 60)
    protocol.expire_policy(policy_id)

    assert protocol.policy_total_exposure(policy_id) == 0
    assert protocol.pool_risk_summary(pool_a)[1] == 0
    assert protocol.pool_risk_summary(pool_b)[1] == 0


def test_underwriter_can_withdraw_unlocked_capital(protocol, accounts, funded_market):
    pool_a, _ = funded_market
    coverage = 200 * ETHER
    policy_id, _ = buy_policy(protocol, accounts, pool_a, coverage, duration_days=10)

    assert protocol.pool_can_withdraw(pool_a, accounts["underwriter"], 500 * ETHER) is True

    before = boa.env.get_balance(accounts["underwriter"])
    with boa.env.prank(accounts["underwriter"]):
        protocol.withdraw_capital(pool_a, 300 * ETHER, accounts["underwriter"])
    after = boa.env.get_balance(accounts["underwriter"])

    assert after - before == 300 * ETHER
    assert protocol.pool_risk_summary(pool_a)[0] >= coverage

    boa.env.time_travel(seconds=11 * 24 * 60 * 60)
    protocol.expire_policy(policy_id)
    assert protocol.free_capital(pool_a) == protocol.pool_risk_summary(pool_a)[0]


def test_claim_submission_approval_and_settlement(protocol, accounts, funded_market):
    pool_a, _ = funded_market
    coverage = 260 * ETHER
    policy_id, _ = buy_policy(protocol, accounts, pool_a, coverage, duration_days=45)
    incident = b32("oracle-confirmed-loss")

    with boa.env.prank(accounts["keeper"]):
        protocol.set_incident_signal(incident, True)

    with boa.env.prank(accounts["beneficiary"]):
        claim_id = protocol.submit_claim(policy_id, 120 * ETHER, incident, b32("evidence-bundle"))

    assert claim_id == 1
    assert protocol.claim_allocation(claim_id, 0) == (pool_a, 120 * ETHER)
    assert protocol.pool_risk_summary(pool_a)[2] == 120 * ETHER

    with boa.env.prank(accounts["reviewer"]):
        protocol.mark_claim_reviewed(claim_id)
        protocol.approve_claim(claim_id, 120 * ETHER)

    before = boa.env.get_balance(accounts["beneficiary"])
    with boa.env.prank(accounts["keeper"]):
        protocol.settle_claim(claim_id)
    after = boa.env.get_balance(accounts["beneficiary"])

    assert after - before == 114 * ETHER
    assert protocol.pool_risk_summary(pool_a)[2] == 0
    assert protocol.pool_risk_summary(pool_a)[3] < 3000


def test_claim_allocation_follows_transferred_exposure(protocol, accounts, funded_market):
    pool_a, pool_b = funded_market
    policy_id, _ = buy_policy(protocol, accounts, pool_a, 400 * ETHER, duration_days=90)

    with boa.env.prank(accounts["router"]):
        protocol.transfer_policy_exposure(policy_id, pool_b, 100 * ETHER)

    incident = b32("multi-pool-loss")
    with boa.env.prank(accounts["keeper"]):
        protocol.set_incident_signal(incident, True)

    with boa.env.prank(accounts["holder"]):
        claim_id = protocol.submit_claim(policy_id, 200 * ETHER, incident, b32("loss-memo"))

    assert protocol.claim_allocation(claim_id, 0) == (pool_a, 150 * ETHER)
    assert protocol.claim_allocation(claim_id, 1) == (pool_b, 50 * ETHER)
    assert protocol.pool_risk_summary(pool_a)[2] == 150 * ETHER
    assert protocol.pool_risk_summary(pool_b)[2] == 50 * ETHER

    with boa.env.prank(accounts["reviewer"]):
        protocol.approve_claim(claim_id, 200 * ETHER)
    with boa.env.prank(accounts["keeper"]):
        protocol.settle_claim(claim_id)

    assert protocol.pool_risk_summary(pool_a)[2] == 0
    assert protocol.pool_risk_summary(pool_b)[2] == 0
    assert protocol.policy_total_exposure(policy_id) == 400 * ETHER
