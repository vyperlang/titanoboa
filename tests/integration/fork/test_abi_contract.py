import hypothesis.strategies as st
import pytest
from eth.constants import ZERO_ADDRESS
from hypothesis import given

import boa


@pytest.fixture(scope="module")
def crvusd(get_filepath):
    abi_path = get_filepath("crvusd_abi.json")

    abi = boa.load_abi(abi_path)

    return abi.at("0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E")


@pytest.fixture(scope="module")
def metaregistry(get_filepath):
    abi_path = get_filepath("metaregistry_abi.json")
    abi = boa.load_abi(abi_path)
    return abi.at("0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC")


@pytest.fixture(scope="module")
def tricrypto(get_filepath):
    abi_path = get_filepath("tricrypto_abi.json")

    abi = boa.load_abi(abi_path)

    return abi.at("0x7F86Bf177Dd4F3494b841a37e810A34dD56c829B")


def test_tricrypto(tricrypto):
    assert tricrypto.fee_receiver() == "0xeCb456EA5365865EbAb8a2661B0c503410e9B347"
    assert tricrypto.get_virtual_price() == 1002646248101745739
    assert tricrypto.gamma() == 11809167828997
    assert tricrypto.fee() == 3704162
    # TODO: test the overloaded functions


def test_invariants(crvusd):
    assert crvusd.decimals() == 18
    assert crvusd.version() == "v1.0.0"
    assert crvusd.name() == "Curve.Fi USD Stablecoin"
    assert crvusd.symbol() == "crvUSD"
    assert crvusd.totalSupply() == 260000000000000000000000000


def test_metaregistry_overloading(metaregistry):
    pool = metaregistry.pool_list(0)
    coin1, coin2 = metaregistry.get_coins(pool)[:2]
    pools_found = metaregistry.find_pools_for_coins(coin1, coin2)
    first_pools = [pool for pool in pools_found if not pool.startswith("0x0000")][:10]
    assert first_pools[0] == metaregistry.find_pool_for_coins(coin1, coin2)
    assert first_pools == [
        metaregistry.find_pool_for_coins(coin1, coin2, i)
        for i in range(len(first_pools))
    ]


# randomly grabbed from:
# https://etherscan.io/token/0xf939e0a03fb07f59a73314e73794be0e57ac1b4e#balances
balances = {
    "0x37417B2238AA52D0DD2D6252d989E728e8f706e4": 1190015011947636310265723,
    "0x3FAAd2238ab2C50a4BD8Fb496b24CddD2fE6CeB4": 30045280884767179302599,
}


def test_balances(crvusd):
    for addr, balance in balances.items():
        assert crvusd.balanceOf(addr) == balance


@given(n=st.integers(min_value=0, max_value=30045280884767179302599))
def test_fork_write(crvusd, n):
    # test we can mutate the fork state
    a = "0x37417B2238AA52D0DD2D6252d989E728e8f706e4"
    b = "0x3FAAd2238ab2C50a4BD8Fb496b24CddD2fE6CeB4"
    with boa.env.prank(a):
        crvusd.transfer(b, n)

    assert crvusd.balanceOf(a) == balances[a] - n
    assert crvusd.balanceOf(b) == balances[b] + n


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
