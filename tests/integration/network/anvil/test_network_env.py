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


# Prefetch is disabled currently since anvil doesn't support `prestateTracer`.
# This test will fail when anvil is fixed, so we can re-enable prefetching.
# Then, this test may be deleted. See fixture `anvil_env`
def test_debug_traceCall_tracer_ignored(simple_contract):
    assert boa.env._fork_try_prefetch_state is False
    assert simple_contract.totalSupply() == STARTING_SUPPLY

    boa.env._fork_try_prefetch_state = True
    try:
        with pytest.raises(ValueError) as excinfo:
            boa.loads(code, STARTING_SUPPLY)
        expected = "when sending a str, it must be a hex string. Got: 'failed'"
        assert expected == str(excinfo.value)
    finally:
        boa.env._fork_try_prefetch_state = False


# XXX: probably want to test deployment revert behavior
