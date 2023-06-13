import pytest

import boa


@pytest.fixture
def crvusd(get_filepath):
    abi_path = get_filepath("crvusd_abi.json")

    abi = boa.load_abi(abi_path)

    return abi.at("0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E")


def test_invariants(crvusd):
    assert crvusd.decimals() == 18
    assert crvusd.version() == "v1.0.0"
    assert crvusd.name() == "Curve.Fi USD Stablecoin"
    assert crvusd.symbol() == "crvUSD"
    assert crvusd.totalSupply() == 260000000000000000000000000


def test_balances(crvusd):
    # randomly grabbed from:
    # https://etherscan.io/token/0xf939e0a03fb07f59a73314e73794be0e57ac1b4e#balances
    balances = {
        "0x37417B2238AA52D0DD2D6252d989E728e8f706e4": 1190015011947636310265723,
        "0x3FAAd2238ab2C50a4BD8Fb496b24CddD2fE6CeB4": 30045280884767179302599,
    }

    for addr, balance in balances.items():
        assert crvusd.balanceOf(addr) == balance


def test_abi_stack_trace(crvusd):
    c = boa.loads(
        """
from vyper.interfaces import ERC20
@external
def foo(x: ERC20, from_: address):
    x.transferFrom(from_, self, 100)
    """
    )

    t = boa.env.generate_address()

    with boa.reverts():
        c.foo(crvusd, t)

    bt = c.stack_trace()
    # something like
    # (unknown location in <...>.transferFrom(address,address,uint256))
    assert "unknown location in" in bt[0]
    assert "transferFrom(address,address,uint256)" in bt[0]
