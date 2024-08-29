import re

import pytest

import boa


def test_simple_mapping_zero_balance():
    source = """
    balanceOf: public(HashMap[address, uint256])
    totalSupply: public(uint256)
    """

    contract = boa.loads(source)

    boa.deal(contract, 100, receiver := boa.env.generate_address())

    assert contract.balanceOf(receiver) == 100
    assert contract.totalSupply() == 100


def test_simple_mapping_no_supply_adjustment():
    source = """
    balanceOf: public(HashMap[address, uint256])
    totalSupply: public(uint256)
    """

    contract = boa.loads(source)

    boa.deal(contract, 100, receiver := boa.env.generate_address(), adjust_supply=False)

    assert contract.balanceOf(receiver) == 100
    assert contract.totalSupply() == 0


def test_simple_mapping_non_zero_balance():
    source = """
    balanceOf: public(HashMap[address, uint256])
    totalSupply: public(uint256)
    """
    contract = boa.loads(source)

    receiver = boa.env.generate_address()

    contract.eval(f"self.balanceOf[{receiver}] = 120")
    contract.eval("self.totalSupply = 120")

    assert contract.balanceOf(receiver) == 120
    assert contract.totalSupply() == 120

    boa.deal(contract, 100, receiver)

    assert contract.balanceOf(receiver) == 100
    assert contract.totalSupply() == 100


def test_multiple_sloads_same_value():
    source = """
    foo: public(uint256)
    bar: public(uint256)

    @view
    @external
    def balanceOf(receiver: address) -> uint256:
        foobar: uint256 = self.bar + self.foo
        return self.foo
    totalSupply: public(uint256)
    """

    contract = boa.loads(source)

    boa.deal(contract, 100, receiver := boa.env.generate_address())

    assert contract.balanceOf(receiver) == 100
    assert contract.totalSupply() == 100


def test_vvm_contract():
    source = """
    # pragma version 0.3.10
    balanceOf: public(HashMap[address, uint256])
    totalSupply: public(uint256)
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

    with pytest.raises(
        ValueError, match=re.escape(f"Function balanceOf not found in {contract}")
    ):
        boa.deal(contract, 100, boa.env.generate_address())


def test_deal_failure_non_erc20_totalSupply():
    source = """
    foo: public(uint256)
    balanceOf: public(HashMap[address, uint256])
    """

    contract = boa.loads(source)

    with pytest.raises(
        ValueError, match=re.escape(f"Function totalSupply not found in {contract}")
    ):
        boa.deal(contract, 100, boa.env.generate_address())


def test_deal_failure_exotic_token_balanceOf():
    code = """
    @external
    @view
    def balanceOf(receiver: address) -> uint256:
        return 100

    totalSupply: public(uint256)
    """

    contract = boa.loads(code)

    with pytest.raises(
        ValueError,
        match="Could not find the target slot for balanceOf, this is expected if"
        " the token packs storage slots or computes the value on the fly",
    ):
        boa.deal(contract, 100, boa.env.generate_address())


def test_deal_failure_exotic_token_totalSupply():
    code = """
    balanceOf: public(HashMap[address, uint256])
    @external
    @view
    def totalSupply() -> uint256:
        return 100
    """

    contract = boa.loads(code)

    with pytest.raises(
        ValueError,
        match="Could not find the target slot for totalSupply, this is expected if"
        " the token packs storage slots or computes the value on the fly",
    ):
        boa.deal(contract, 100, boa.env.generate_address())
