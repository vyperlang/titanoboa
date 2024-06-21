import pytest

import boa


@pytest.fixture(scope="module")
def vyper_contract():
    source_code = """
a: public(uint256)
b: public(uint256)

@external
def __init__(a_input: uint256, b_input: uint256):

    self.a = a_input
    self.b = b_input


@external
def set_vars(a_input: uint256, b_input: uint256):

    self.a = a_input
    self.b = b_input
"""

    return source_code


def test_contract_unregistered_after_rollback(vyper_contract):
    with boa.env.anchor():
        contract_a = boa.loads(vyper_contract, 1, 2)
        with boa.env.anchor():
            contract_b = boa.loads(vyper_contract, 2, 2)
        assert boa.env.lookup_contract(contract_a.address) != None
        assert boa.env.lookup_contract(contract_b.address) == None
    assert len(boa.env._contracts) == 0


def test_contract_unregistered_nested_anchor(vyper_contract):
    with boa.env.anchor():
        contract_a = boa.loads(vyper_contract, 1, 2)
        with boa.env.anchor():
            contract_b = boa.loads(vyper_contract, 2, 2)
            with boa.env.anchor():
                contract_c = boa.loads(vyper_contract, 2, 2)
            assert boa.env.lookup_contract(contract_c.address) == None
        assert boa.env.lookup_contract(contract_a.address) != None
        assert boa.env.lookup_contract(contract_b.address) == None
    assert len(boa.env._contracts) == 0
