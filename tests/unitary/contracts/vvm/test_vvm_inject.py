import pytest

import boa


def _base_code():
    return """
# pragma version 0.3.10

totalSupply: public(uint256)
"""


def _inject_code():
    return """
@external
def test_mint(amt: uint256):
    self.totalSupply += amt
"""


def test_vvm_inject_function_mutates_state():
    c = boa.loads(_base_code())

    # Ensure VVM contracts expose injection
    assert hasattr(c, "inject_function")

    c.inject_function(_inject_code())

    amt = 7
    c.test_mint(amt)
    assert c.totalSupply() == amt


def test_vvm_inject_double_vs_force():
    c = boa.loads(_base_code())
    c.inject_function(_inject_code())

    with pytest.raises(ValueError):
        c.inject_function(_inject_code())

    # Allow overriding with force
    c.inject_function(_inject_code(), force=True)
