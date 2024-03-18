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


# test isolation of hypothesis fuzz cases
@given(a=strategy("uint"), b=strategy("address"))
def test_hypothesis_isolation(boa_contract, a, b):
    assert boa_contract.a() == A_INIT
    assert boa_contract.b() == B_INIT
    boa_contract.set_vars(a, b)
    assert boa_contract.a() == a
    assert boa_contract.b() == b


# test isolation of pytest items
@pytest.mark.parametrize("a", [1, 2, 3])
@pytest.mark.parametrize("b", [boa.env.eoa, boa.env.generate_address()])
def test_pytest_isolation(boa_contract, a, b):
    assert boa_contract.a() == A_INIT
    assert boa_contract.b() == B_INIT
    boa_contract.set_vars(a, b)
    assert boa_contract.a() == a
    assert boa_contract.b() == b


@pytest.fixture(scope="module")
@pytest.mark.ignore_isolation
def setup_ignore_isolation(boa_contract):
    assert boa_contract.a() == A_INIT
    assert boa_contract.b() == B_INIT
    boa_contract.set_vars(42069, addr_constn)


@pytest.mark.ignore_isolation
def test_check_ignore_isolation(boa_contract, setup_ignore_isolation):
    assert boa_contract.a() == 42069
    assert boa_contract.b() == addr_constn


@pytest.fixture(scope="module")
def fixture_isolation_contract():
    code = """
x: uint256

@external
def set_x(val: uint256):
    self.x = val

@external
def get_x() -> uint256:
    return self.x
    """
    c = boa.loads(code)
    c.set_x(1)
    return c


@pytest.fixture(scope="function")
# test fixture isolation. this is a fixture which modifies its input fixture
def modify_contract(fixture_isolation_contract):
    assert fixture_isolation_contract.get_x() == 1
    fixture_isolation_contract.set_x(2)


@pytest.mark.parametrize("a", range(10))
def test_fixture_isolation(modify_contract, fixture_isolation_contract, a):
    assert fixture_isolation_contract.get_x() == 2
