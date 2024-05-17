import boa


def test_log_constructor():
    contract = boa.loads(
        """
event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

@external
def __init__(supply: uint256):
    log Transfer(empty(address), msg.sender, supply)
""",
        100,
    )
    logs = contract.get_logs()
    log_strs = [str(log) for log in logs]
    assert log_strs == ["Transfer(sender=0x"]
