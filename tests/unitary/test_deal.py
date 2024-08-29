import pytest

import boa


def test_simple_mapping_zero_balance():
    source = "balanceOf: public(HashMap[address, uint256])"

    contract = boa.loads(source)

    boa.deal(contract, 100, receiver := boa.env.generate_address())

    assert contract.balanceOf(receiver) == 100


def test_simple_mapping_non_zero_balance():
    source = "balanceOf: public(HashMap[address, uint256])"

    contract = boa.loads(source)

    receiver = boa.env.generate_address()

    contract.eval(f"self.balanceOf[{receiver}] = 120")
    assert contract.balanceOf(receiver) == 120

    boa.deal(contract, 100, receiver)

    assert contract.balanceOf(receiver) == 100


def test_multiple_sloads_same_value():
    source = """
    foo: public(uint256)
    bar: public(uint256)
    
    @view
    @external
    def balanceOf(receiver: address) -> uint256:
        foobar: uint256 = self.bar + self.foo
        return self.foo
    """

    contract = boa.loads(source)

    boa.deal(contract, 100, receiver := boa.env.generate_address())

    assert contract.balanceOf(receiver) == 100

def test_vvm_contract():
    source = """
    # pragma version 0.3.10
    balanceOf: public(HashMap[address, uint256])
    """

    contract = boa.loads(source)

    print(type(contract))

    boa.deal(contract, 100, receiver := boa.env.generate_address())

    assert contract.balanceOf(receiver) == 100


def test_deal_failure_non_erc20():
    source = """
    foo: public(uint256)
    """

    contract = boa.loads(source)

    with pytest.raises(ValueError, match="Invalid token contract, are you sure it's an ERC20?"):
        boa.deal(contract, 100, receiver := boa.env.generate_address())

def test_deal_failure_exotic_token():
    code = """
    @external
    @view
    def balanceOf(receiver: address) -> uint256:
        return 100
    """

    contract = boa.loads(code)

    with pytest.raises(ValueError, match="Could not find the target slot, this is expected if the token packs storage slots or computes the balance on the fly"):
        boa.deal(contract, 100, receiver := boa.env.generate_address())
