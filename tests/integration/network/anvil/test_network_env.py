import pytest
from hypothesis import given, settings

import boa
import boa.test.strategies as vy
from boa.network import NetworkEnv

code = """
totalSupply: public(uint256)
balances: HashMap[address, uint256]

@deploy
def __init__(t: uint256):
    self.totalSupply = t
    self.balances[self] = t

@external
def update_total_supply(t: uint16):
    self.totalSupply += convert(t, uint256)

@external
def raise_exception(t: uint256):
    raise "oh no!"
"""

STARTING_SUPPLY = 100


@pytest.fixture(scope="module")
def simple_contract():
    return boa.loads(code, STARTING_SUPPLY)


def test_env_type():
    # sanity check
    assert isinstance(boa.env, NetworkEnv)


def test_network_env_nickname(free_port):
    assert boa.env.nickname == f"http://localhost:{free_port}"


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY


@settings(max_examples=100, deadline=None)
@given(vy.strategy("uint16"))
def test_update_total_supply(simple_contract, t):
    orig_supply = simple_contract.totalSupply()
    assert orig_supply == STARTING_SUPPLY  # test isolation in fork
    simple_contract.update_total_supply(t)
    assert simple_contract.totalSupply() == orig_supply + t


@settings(max_examples=1, deadline=None)
@given(vy.strategy("uint256"))
def test_raise_exception(simple_contract, t):
    with boa.reverts("oh no!"):
        simple_contract.raise_exception(t)


def test_failed_transaction():
    with pytest.raises(Exception) as ctx:
        boa.loads(code, STARTING_SUPPLY, gas=149377)
    error = str(ctx.value)
    assert error.startswith("txn failed:")


# XXX: probably want to test deployment revert behavior
