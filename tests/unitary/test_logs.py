import boa
from boa.util.abi import Address


def test_log_constructor():
    contract = boa.loads(
        """
event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

@deploy
def __init__(supply: uint256):
    log Transfer(empty(address), msg.sender, supply)
""",
        100,
    )
    logs = contract.get_logs()
    sender = Address("0x0000000000000000000000000000000000000000")
    receiver = boa.env.eoa
    expected = f"Transfer(address={repr(contract.address)},"
    expected += f" sender={repr(sender)},"
    expected += f" receiver={repr(receiver)},"
    expected += " value=100)"
    log_strs = [str(log) for log in logs]
    assert log_strs == [expected]
