from os import urandom
from unittest.mock import patch

import pytest
from hypothesis import given, settings

import boa
import boa.test.strategies as vy
from boa.network import NetworkEnv

code = """
totalSupply: public(uint256)
balances: HashMap[address, uint256]

@external
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


def test_deploy_cached():
    deploy_id = urandom(16).hex()
    c1 = boa.loads(code, STARTING_SUPPLY, deploy_id=deploy_id)
    with patch("boa.network.NetworkEnv._send_txn", side_effect=ValueError):
        c2 = boa.loads(code, STARTING_SUPPLY, deploy_id=deploy_id)

    # different supply
    c3 = boa.loads(code, STARTING_SUPPLY * 2, deploy_id=deploy_id)

    assert c1.address == c2.address
    assert c1.address != c3.address


def test_deploy_cache_set():
    deploy_id = urandom(16).hex()
    deployer = boa.loads_partial(code)
    c1 = deployer.deploy(STARTING_SUPPLY, deploy_id=deploy_id)
    bytecode = deployer.compiler_data.bytecode + c1._ctor.prepare_calldata(
        STARTING_SUPPLY
    )
    receipt, trace = boa.env._deploys.get(code, bytecode, deploy_id, chain_id=31337)
    assert receipt is not None and trace is not None


# XXX: probably want to test deployment revert behavior
