from pathlib import Path
from tempfile import TemporaryDirectory

import hypothesis.strategies as st
import pytest
from hypothesis import given

import boa
from boa import BoaError

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


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
def stableswap_factory_ng(get_filepath):
    abi_path = get_filepath("CurveStableswapFactoryNG_abi.json")
    abi = boa.load_abi(abi_path)
    return abi.at("0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf")


@pytest.fixture(scope="module")
def tricrypto(get_filepath):
    abi_path = get_filepath("tricrypto_abi.json")

    abi = boa.load_abi(abi_path)

    return abi.at("0x7F86Bf177Dd4F3494b841a37e810A34dD56c829B")


def test_tricrypto(tricrypto):
    assert tricrypto.fee_receiver() == "0xeCb456EA5365865EbAb8a2661B0c503410e9B347"
    assert tricrypto.get_virtual_price() == 1003146380129683788
    assert tricrypto.gamma() == 11809167828997
    assert tricrypto.fee() == 7069800
    assert tricrypto.initial_A_gamma() == 581076037942835227425498917514114728328226821


def test_no_bytecode(get_filepath):
    abi_path = get_filepath("crvusd_abi.json")
    crvusd = boa.load_abi(abi_path).at(ZERO_ADDRESS)
    with pytest.raises(BoaError) as exc_info:
        crvusd.decimals()
    assert "no bytecode at this address" in str(exc_info.value)


def test_invariants(crvusd):
    assert crvusd.decimals() == 18
    assert crvusd.version() == "v1.0.0"
    assert crvusd.name() == "Curve.Fi USD Stablecoin"
    assert crvusd.symbol() == "crvUSD"
    assert crvusd.totalSupply() == 730461476239623125757516933


def test_metaregistry_overloading(metaregistry):
    pool = metaregistry.pool_list(0)
    coin1, coin2 = metaregistry.get_coins(pool)[:2]
    pools_found = metaregistry.find_pools_for_coins(coin1, coin2)
    first_pools = [pool for pool in pools_found if not pool.startswith("0x0000")][:2]
    assert first_pools[0] == metaregistry.find_pool_for_coins(coin1, coin2)
    assert first_pools == [
        metaregistry.find_pool_for_coins(coin1, coin2, i)
        for i in range(len(first_pools))
    ]


def test_stableswap_factory_ng(stableswap_factory_ng):
    pool = "0x76Ae7A7DC125E4163a2137e650b7726231FdB917"
    assert stableswap_factory_ng.pool_list(5) == pool
    base_pool = stableswap_factory_ng.get_base_pool(pool)
    assert stableswap_factory_ng.base_pool_data(base_pool) == (
        "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        [
            "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        ],
        394770,
        3,
        [0, 0, 0],
    )
    assert stableswap_factory_ng.base_pool_data(pool) == (ZERO_ADDRESS, [], 0, 0, [])


# randomly grabbed from:
# https://etherscan.io/token/0xf939e0a03fb07f59a73314e73794be0e57ac1b4e#balances
account_a = "0x37417B2238AA52D0DD2D6252d989E728e8f706e4"
account_b = "0x4e59541306910aD6dC1daC0AC9dFB29bD9F15c67"
balances = {
    account_a: 3797750812312960372676816,
    account_b: 167292367990896792104836343,
}


@pytest.mark.parametrize("addr,balance", balances.items())
def test_balances(addr, balance, crvusd):
    assert crvusd.balanceOf(addr) == balance


# test write 0 to fresh fork state
def test_fork_write0(crvusd):
    n = balances[account_a]
    with boa.env.prank(account_a):
        crvusd.transfer(account_b, n)

    assert crvusd.balanceOf(account_a) == 0
    assert crvusd.balanceOf(account_b) == balances[account_b] + n


@given(n=st.integers(min_value=0, max_value=balances[account_a]))
def test_fork_write(crvusd, n):
    # test we can mutate the fork state
    with boa.env.prank(account_a):
        crvusd.transfer(account_b, n)

    assert crvusd.balanceOf(account_a) == balances[account_a] - n
    assert crvusd.balanceOf(account_b) == balances[account_b] + n


# test net gas metering negative refund
def test_fork_write_flip(crvusd):
    e = boa.loads(
        f"""
from ethereum.ercs import IERC20
crvUSD: IERC20

@deploy
def __init__():
    self.crvUSD = IERC20({crvusd.address})
@external
def flip_from(_input: uint256) -> uint256:
    extcall self.crvUSD.transferFrom(msg.sender, self, _input)
    extcall self.crvUSD.transfer(msg.sender, _input // 2)
    return _input // 2
    """
    )
    pool = "0x4dece678ceceb27446b35c672dc7d61f30bad69e"
    initial_balance = crvusd.balanceOf(pool)
    with boa.env.prank(pool):
        crvusd.approve(e, 2**256 - 1)
        e.flip_from(initial_balance)
    assert crvusd.balanceOf(pool) == initial_balance // 2
    assert crvusd.balanceOf(e) == initial_balance - initial_balance // 2


def test_abi_stack_trace(crvusd):
    c = boa.loads(
        """
from ethereum.ercs import IERC20
@external
def foo(x: IERC20, from_: address):
    extcall x.transferFrom(from_, self, 100)
    """
    )

    t = boa.env.generate_address()

    with boa.reverts():
        c.foo(crvusd, t)

    bt = c.stack_trace()
    assert "crvusd_abi interface at 0x" in bt[0]
    assert "transferFrom(address,address,uint256)" in bt[0]


def test_call_trace_abi_and_vyper(crvusd):
    c = boa.loads(
        """
from ethereum.ercs import IERC20
@external
def foo(x: IERC20):
    extcall x.transfer(self, 100)
    """
    )
    boa.env.set_balance(boa.env.eoa, 1000)
    with boa.reverts():
        c.foo(crvusd)

    tree = c.call_trace()
    assert str(tree).splitlines() == [
        f'[E] [5290] VyperContract.foo:5(x = "{crvusd.address}") <0x>',
        f'    [E] [2502] crvusd_abi.transfer(_to = "{c.address}", _value = 100) <0x>',
    ]
    assert tree.to_dict() == {
        "address": "0xC6Acb7D16D51f72eAA659668F30A40d87E2E0551",
        "children": [
            {
                "address": "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E",
                "children": [],
                "depth": 1,
                "gas_used": 2502,
                "is_error": True,
                "input": "0x000000000000000000000000c6acb7d16d51f72eaa659668f30a40d87e2e0551000000"
                "0000000000000000000000000000000000000000000000000000000064",
                "output": "0x",
                "source": "crvusd_abi.transfer",
                "text": '[E] [2502] crvusd_abi.transfer(_to = "'
                '0xC6Acb7D16D51f72eAA659668F30A40d87E2E0551", _value = 100) <0x>',
            }
        ],
        "depth": 0,
        "gas_used": 5290,
        "is_error": True,
        "input": "0x000000000000000000000000f939e0a03fb07f59a73314e73794be0e57ac1b4e",
        "output": "0x",
        "source": "VyperContract.foo:5",
        "text": "[E] [5290] VyperContract.foo:5(x = "
        '"0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E") <0x>',
    }

    with TemporaryDirectory() as tmpdir:
        tmpfile = Path(tmpdir) / "trace.json"
        tree.export_html(tmpfile)
        with open(tmpfile) as f:
            html = f.read()
            assert html.startswith("<!DOCTYPE html>")
            assert "JSON.parse(`{" in html
