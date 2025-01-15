import time

import boa


def test_env_timestamp():
    assert boa.env.timestamp == boa.env.evm.patch.timestamp

    tmp = boa.env.timestamp
    with boa.env.anchor():
        boa.env.timestamp += 1
        # check patch is updated
        assert boa.env.timestamp == boa.env.evm.patch.timestamp
        assert tmp + 1 == boa.env.timestamp

    # check reset to prior value after anchor
    assert tmp == boa.env.timestamp
    # sanity check
    assert boa.env.timestamp == boa.env.evm.patch.timestamp


def test_timestamp_correctness():
    # amount of "timer slack" to allow in the CI since it may take some
    # time between when boa.env is initialized and when this test is run.
    timer_slack = 60
    assert abs(boa.env.timestamp - time.time()) < timer_slack, "bad time"
