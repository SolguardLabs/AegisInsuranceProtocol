from pathlib import Path
import sys

import boa
import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "src" / "AegisInsuranceProtocol.vy"
ETHER = 10**18

sys.path.insert(0, str(ROOT / "src"))


def b32(value: str) -> bytes:
    raw = value.encode("ascii")
    if len(raw) > 32:
        raise ValueError("bytes32 helper received a long value")
    return raw.ljust(32, b"\0")


@pytest.fixture(autouse=True)
def isolated_chain():
    with boa.env.anchor():
        yield


@pytest.fixture
def accounts():
    owner = boa.env.eoa
    treasury = boa.env.generate_address("treasury")
    underwriter = boa.env.generate_address("underwriter")
    underwriter_alt = boa.env.generate_address("underwriter-alt")
    holder = boa.env.generate_address("holder")
    beneficiary = boa.env.generate_address("beneficiary")
    keeper = boa.env.generate_address("keeper")
    reviewer = boa.env.generate_address("reviewer")
    router = boa.env.generate_address("router")

    for account in [owner, treasury, underwriter, underwriter_alt, holder, beneficiary, keeper, reviewer, router]:
        boa.env.set_balance(account, 2_000 * ETHER)

    return {
        "owner": owner,
        "treasury": treasury,
        "underwriter": underwriter,
        "underwriter_alt": underwriter_alt,
        "holder": holder,
        "beneficiary": beneficiary,
        "keeper": keeper,
        "reviewer": reviewer,
        "router": router,
    }


@pytest.fixture
def protocol(accounts):
    aegis = boa.load(str(CONTRACT), accounts["treasury"])
    aegis.set_role(accounts["keeper"], 3, True)
    aegis.set_role(accounts["reviewer"], 1, True)
    aegis.set_role(accounts["router"], 2, True)
    aegis.configure_product(1, b32("ETH-STABLE-VAULT"), 720, 10**15, 500, 30, 700 * ETHER, True)
    return aegis


@pytest.fixture
def funded_market(protocol, accounts):
    pool_a = protocol.create_pool(b32("Senior A"), b32("EU"), 0, 9000, 7000)
    pool_b = protocol.create_pool(b32("Specialty B"), b32("EU"), 0, 9000, 7000)

    with boa.env.prank(accounts["underwriter"]):
        protocol.deposit_capital(pool_a, accounts["underwriter"], value=1_000 * ETHER)

    with boa.env.prank(accounts["underwriter_alt"]):
        protocol.deposit_capital(pool_b, accounts["underwriter_alt"], value=700 * ETHER)

    return pool_a, pool_b


def buy_policy(protocol, accounts, pool_id, coverage, duration_days=90, subject="vault-alpha"):
    premium = protocol.quote_premium(pool_id, 1, coverage, duration_days)
    with boa.env.prank(accounts["holder"]):
        policy_id = protocol.buy_policy(
            pool_id,
            1,
            b32(subject),
            coverage,
            duration_days,
            accounts["beneficiary"],
            value=premium,
        )
    return policy_id, premium
