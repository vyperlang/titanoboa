import pytest

from hypothesis import given
import boa
from boa.test import strategy

A_INIT = 10
B_INIT = boa.env.generate_address()
addr_constn = boa.env.generate_address()


@pytest.fixture(scope="module")
def boa_contract():
    source_code = """
a: public(uint256)
b: public(address)

@external
def __init__(a_input: uint256, b_input: address):

    self.a = a_input
    self.b = b_input


@external
def set_vars(a_input: uint256, b_input: address):

    self.a = a_input
    self.b = b_input
"""

    with boa.env.prank(boa.env.generate_address()):
        return boa.loads(source_code, A_INIT, B_INIT)


@given(a=strategy("uint"), b=strategy("address"))
def test_state_isolation(boa_contract, a, b):
    assert boa_contract.a() == A_INIT
    assert boa_contract.b() == B_INIT
    boa_contract.set_vars(a, b)
    assert boa_contract.a() == a
    assert boa_contract.b() == b


@pytest.mark.ignore_isolation
def test_ignore_isolation_init(boa_contract):
    assert boa_contract.a() == A_INIT
    assert boa_contract.b() == B_INIT
    boa_contract.set_vars(42069, addr_constn)


@pytest.mark.ignore_isolation
def test_check_ignore_isolation(boa_contract):
    assert boa_contract.a() == 42069
    assert boa_contract.b() == addr_constn
