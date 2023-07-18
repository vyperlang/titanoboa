import os

import pytest

import boa
from boa.environment import Env


# run all tests with this forked environment
# called as fixture for its side effects
@pytest.fixture(scope="module", autouse=True)
def forked_env():
    with boa.swap_env(Env()):
        fork_uri = os.environ.get("MAINNET_ENDPOINT", "http://localhost:8545")
        blkid = 17467922  # some block we know the state of
        boa.env.fork(fork_uri, block_identifier=blkid)
        yield
