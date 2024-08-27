import os

import pytest

import boa
from boa.environment import Env


@pytest.fixture(scope="module")
def rpc_url():
    return os.environ.get("MAINNET_ENDPOINT") or "http://localhost:8545"


# run all tests with this forked environment
# called as fixture for its side effects
@pytest.fixture(scope="module", autouse=True)
def forked_env(rpc_url):
    with boa.swap_env(Env()):
        block_id = 18801970  # some block we know the state of
        boa.fork(rpc_url, block_identifier=block_id)
        yield
