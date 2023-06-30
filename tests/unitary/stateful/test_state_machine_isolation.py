import pytest
import hypothesis.strategies as st
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
def add_to_a(d: uint256):
    self.a += d
"""
    return boa.loads(source_code)


NUM_STEPS = 100


class StateMachine(RuleBasedStateMachine):
    contract = None

    @initialize()
    def setup(self):
        self.a = 0

    @rule(d=st.integers(min_value=0, max_value=(2**256) // NUM_STEPS))
    def change_a(self, d):
        self.contract.add_to_a(d)
        self.a += d

    @invariant()
    def foo(self):
        assert self.contract.a() == self.a

    # ensure overriding teardown doesn't break things
    def teardown(self):
        pass


def test_state_machine_isolation(boa_contract):
    StateMachine.contract = boa_contract
    StateMachine.settings = {
        "stateful_step_count": NUM_STEPS,
        "suppress_health_check": HealthCheck.all(),
    }
    run_state_machine_as_test(StateMachine)
