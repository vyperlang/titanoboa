import pytest
from vyper.utils import keccak256

import boa
from boa.contracts.vyper.event import RawEvent

WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

code = f"""

interface IWETH:
    def deposit(): payable

weth9: constant(address) = {WETH_ADDRESS}

@external
@payable
def deposit():
    extcall IWETH(weth9).deposit(value=msg.value)

"""


@pytest.fixture(scope="module")
def simple_contract():
    return boa.loads(code)


def test_logs(simple_contract):
    eoa = boa.env.generate_address()
    amount = 10**18
    boa.env.set_balance(eoa, amount)
    simple_contract.deposit(value=amount, sender=eoa)

    topic0 = keccak256("Deposit(address,uint256)".encode())
    expected_log = (
        0,
        int(WETH_ADDRESS, 16).to_bytes(20, "big"),
        (int.from_bytes(topic0, "big"), int(simple_contract.address, 16)),
        amount.to_bytes(32, "big"),
    )

    logs = simple_contract.get_logs()
    assert logs == [RawEvent(expected_log)]
