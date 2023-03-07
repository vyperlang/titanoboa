import pytest
from hypothesis._settings import HealthCheck
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    rule,
    run_state_machine_as_test,
)

import boa


@pytest.fixture(scope="module")
def boa_contract():
    source_code = """
a: public(uint256)

@external
def add_to_a(_a: uint256):
    self.a += _a
"""
    return boa.loads(source_code)


class StateMachine(RuleBasedStateMachine):
    contract = None

    @initialize()
    def setup(self):
        self.contract.add_to_a(10)

    # empty rule just so hypothesis does not complain
    @rule()
    def void(self):
        pass

    @invariant()
    def foo(self):
        assert self.contract.a() == 10

    # ensure overriding teardown doesn't break things
    def teardown(self):
        pass


def test_state_machine_isolation(boa_contract):
    StateMachine.contract = boa_contract
    StateMachine.settings = {
        "max_examples": 5,
        "suppress_health_check": HealthCheck.all(),
    }
    run_state_machine_as_test(StateMachine)
