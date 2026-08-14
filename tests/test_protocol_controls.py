import boa

from conftest import ETHER, b32, buy_policy


def test_guardian_can_pause_but_only_owner_can_resume(protocol, accounts):
    guardian = accounts["underwriter_alt"]
    protocol.set_role(guardian, 4, True)

    with boa.env.prank(guardian):
        protocol.set_paused(True)
    assert protocol.paused() is True

    with boa.env.prank(guardian):
        with boa.reverts("owner only"):
            protocol.set_paused(False)

    protocol.set_paused(False)
    assert protocol.paused() is False


def test_pool_retention_policy_bounds_cessions(protocol, accounts, funded_market):
    pool_a, pool_b = funded_market
    policy_id, _ = buy_policy(protocol, accounts, pool_a, 300 * ETHER)

    with boa.env.prank(accounts["router"]):
        with boa.reverts("retention policy"):
            protocol.transfer_policy_exposure(policy_id, pool_b, 151 * ETHER)
        protocol.transfer_policy_exposure(policy_id, pool_b, 150 * ETHER)

    assert protocol.policy_pool_allocation(policy_id, pool_a) == 150 * ETHER
    assert protocol.policy_pool_allocation(policy_id, pool_b) == 150 * ETHER


def test_minimum_capital_is_enforced_on_withdrawal(protocol, accounts):
    pool_id = protocol.create_pool(b32("Capital Floor"), b32("EU"), 500 * ETHER, 9_000, 5_000)
    with boa.env.prank(accounts["underwriter"]):
        protocol.deposit_capital(pool_id, accounts["underwriter"], value=1_000 * ETHER)

    assert protocol.pool_can_withdraw(pool_id, accounts["underwriter"], 600 * ETHER) is False
    with boa.env.prank(accounts["underwriter"]):
        with boa.reverts("capital floor"):
            protocol.withdraw_capital(pool_id, 600 * ETHER, accounts["underwriter"])
        protocol.withdraw_capital(pool_id, 500 * ETHER, accounts["underwriter"])

    assert protocol.pool_risk_summary(pool_id)[0] == 500 * ETHER
