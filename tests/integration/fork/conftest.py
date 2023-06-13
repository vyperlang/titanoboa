import os

import pytest

import boa
from boa.environment import Env


# run all tests with this forked environment
@pytest.fixture(scope="package", autouse=True)
def boa_env():
    with boa.swap_env(Env()):
        alchemy_api_key = os.environ["ALCHEMY_MAINNET_API_KEY"]
        ALCHEMY_URI = f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_api_key}"
        blkid = 17467922  # some block we know the state of
        boa.env.fork(ALCHEMY_URI, block_identifier=blkid)
        yield
