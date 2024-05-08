import pytest

import boa

code = """

interface IWETH:
    def deposit(): payable

weth9: constant(address) = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2

@external
@payable
def deposit():
    IWETH(weth9).deposit(value=msg.value)

"""


@pytest.fixture(scope="module")
def simple_contract():
    return boa.loads(code)


def test_logs(simple_contract):
    eoa = boa.env.generate_address()
    boa.env.set_balance(eoa, 10**21)
    simple_contract.deposit(value=10**18, sender=eoa)

    logs = simple_contract.get_logs()
    assert len(logs) > 0

    for log in logs:
        assert hasattr(log, "event_data")
