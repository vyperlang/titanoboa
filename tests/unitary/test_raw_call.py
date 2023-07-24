import eth.exceptions
import pytest

import boa

fund_me_source = """
userBal: HashMap[address, uint256]

@external
@payable
def fund_contract():
    assert msg.value > 0, "msg.value cannot be zero"
    self.userBal[msg.sender] += msg.value
"""


@pytest.fixture(scope="module")
def fund_me():
    return boa.loads(fund_me_source)


# Try to send funds directly to the contract. Must revert
def test_deposit_via_default_function(fund_me):
    assert boa.env.get_balance(fund_me.address) == 0
    user = boa.env.generate_address("user0")
    boa.env.set_balance(user, 100000)
    with boa.env.prank(user):
        with pytest.raises(eth.exceptions.Revert):
            boa.env.raw_call(fund_me.address, value=100000)

        # demonstrate using execute_code
        computation = boa.env.execute_code(fund_me.address, value=100000)
        assert computation.is_error

    assert boa.env.get_balance(fund_me.address) == 0
