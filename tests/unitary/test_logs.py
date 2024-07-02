import boa


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
    log_strs = [str(log) for log in logs]
    sender = "0x0000000000000000000000000000000000000000"
    receiver = str(boa.env.eoa)
    assert log_strs == [f"Transfer(sender={sender}, receiver={receiver}, value=100)"]
