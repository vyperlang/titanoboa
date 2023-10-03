from boa.interpret import load

me = "0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF"
token = load("examples/ERC20.vy", "Test", "TEST", 18, 0)
token.mint(me, 100)
event = token.get_logs()[0]


def test_topics_saved_to_event():
    assert len(event.topics) == 2
    assert event.topics[0] == "0x0000000000000000000000000000000000000000"
    assert event.topics[1] == me


def test_args_saved_to_event():
    assert len(event.args) == 1
    assert event.args[0] == 100


def test_args_ordered_to_event_param_sequence():
    args = event.ordered_args()
    assert args[0][0] == "sender"
    assert args[1][0] == "receiver"
    assert args[2][0] == "value"


def test_args_map_match_event_params():
    args = event.args_map
    assert args["sender"] == "0x0000000000000000000000000000000000000000"
    assert args["receiver"] == me
    assert args["value"] == 100


def test_args_map_values_match_ordered_args():
    assert event.args_map == {
        "sender": "0x0000000000000000000000000000000000000000",
        "receiver": me,
        "value": 100,
    }
    assert event.ordered_args() == [
        ("sender", "0x0000000000000000000000000000000000000000"),
        ("receiver", me),
        ("value", 100),
    ]
