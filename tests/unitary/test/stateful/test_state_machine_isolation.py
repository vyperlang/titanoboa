import boa
from boa.test import state_machine
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

    def __init__(self, contract):
        self.contract = contract

    def setup(self):
        self.contract.add_to_a(10)

    # empty rule just so hypothesis does not complain
    def rule_void(self):
        pass

    def invariant_foo(self):
        assert self.contract.a() == 10


def test_state_machine_isolation(boa_contract):
    from hypothesis._settings import HealthCheck

    state_machine(
        TestStateMachine,
        boa_contract,
        settings={
            "max_examples": 5,
            "suppress_health_check": HealthCheck.all(),
        }
    )
