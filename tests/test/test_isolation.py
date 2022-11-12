import boa

from boa.test import given, strategy

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
    boa_contract = boa.loads(source_code, 10, boa.env.generate_address())

A_INIT = boa_contract.a()
B_INIT = boa_contract.b()


@given(a=strategy("uint"), b=strategy("address"))
def test_state_isolation(a, b):
    assert boa_contract.a() == A_INIT
    assert boa_contract.b() == B_INIT
    boa_contract.set_vars(a, b)
