import pytest

import boa


@pytest.fixture()
def base_code():
    return boa.loads("""
# pragma version 0.3.10

totalSupply: public(uint256)
""")


@pytest.fixture()
def inject_code():
    return """
@external
def test_mint(amt: uint256):
    self.totalSupply += amt
"""


def test_vvm_inject_function_mutates_state(base_code, inject_code):
    base_code.inject_function(inject_code)

    amt = 7
    base_code.inject.test_mint(amt)
    assert base_code.totalSupply() == amt


def test_vvm_inject_double_vs_force(base_code, inject_code):
    base_code.inject_function(inject_code)

    with pytest.raises(ValueError):
        base_code.inject_function(inject_code)

    # Allow overriding with force
    base_code.inject_function(inject_code, force=True)
