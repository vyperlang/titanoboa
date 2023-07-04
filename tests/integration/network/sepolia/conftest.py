# tests network mode against sepolia

import os

import pytest
from eth_account import Account

import boa
from boa.network import NetworkEnv


# run all tests with testnet
@pytest.fixture(scope="module", autouse=True)
def sepolia_env():
    PKEY = os.environ["SEPOLIA_PKEY"]
    SEPOLIA_URI = os.environ["SEPOLIA_ENDPOINT"]
    with boa.swap_env(NetworkEnv(SEPOLIA_URI)):
        boa.env.add_account(Account.from_key(PKEY))
        yield
