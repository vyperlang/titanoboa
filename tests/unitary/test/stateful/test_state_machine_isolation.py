import boa
from boa.test import given, strategy, state_machine
import pytest


@pytest.fixture(scope="module")
def boa_contract():
    source_code = """
a: public(uint256)

@external
def add_to_a(_a: uint256):
    self.a += _a
"""
    return boa.loads(source_code)


class TestStateMachine:

    def __init__(self, contract, val):
        self.contract = contract
        self.add_val = val

    def setup(self):
        self.contract.add_to_a(self.add_val)

    # empty rule just so hypothesis does not complain
    def rule_void(self):
        pass

    def invariant_a(self):
        assert self.contract.a() == self.add_val


@given(val=strategy("uint256"))
def test_state_machine_isolation(boa_contract, val):
    from hypothesis._settings import HealthCheck

    state_machine(
        TestStateMachine,
        boa_contract,
        val,
        settings={
            "max_examples": 5,
            "suppress_health_check": HealthCheck.all(),
        }
    )
