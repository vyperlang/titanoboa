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
    assert abs(boa.env.timestamp - time.time()) < 1, "time should be present time"
