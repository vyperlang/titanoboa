import pytest
from hypothesis import given

import boa
from boa.test.strategies import strategy

contract_code = """
totalSupply: public(uint256)
"""

inject_code = """
@external
def test_mint(amt: uint256):
    self.totalSupply += amt

def test_mint_default(amt: uint256 = 1):
    self.totalSupply += amt
"""


@pytest.fixture(scope="module")
def contract():
    s = boa.loads(contract_code)
    s.inject_function(inject_code)
    return s


def test_inject_force(contract):
    with pytest.raises(ValueError):
        # name collision
        contract.inject_function(inject_code)

    contract.inject_function(inject_code, force=True)


@given(x=strategy("uint256"))
def test_inject(contract, x):
    contract.inject.test_mint(x)
    assert contract.totalSupply() == x

@given(x=strategy("uint256"))
def test_inject_default(contract, x):
    contract.inject.test_mint_default(x)
    assert contract.totalSupply() == x
    contract.inject.test_mint_default()
    assert contract.totalSupply() == x + 1
