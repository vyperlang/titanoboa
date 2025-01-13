import time

import boa


def test_timestamp_shortcut():
    assert (
        boa.env.timestamp() == boa.env.evm.patch.timestamp
    ), "result should equal its shortcut"


def test_timestamp_correctness():
    assert abs(boa.env.timestamp() - time.time()) < 1, "time should be present time"
