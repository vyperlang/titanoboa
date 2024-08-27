# tests network mode against sepolia

import os

import pytest
from eth_account import Account

import boa

PKEY = os.environ["SEPOLIA_PKEY"]
SEPOLIA_URI = os.environ["SEPOLIA_ENDPOINT"]


# run all tests with testnet
@pytest.fixture(scope="module", autouse=True)
def sepolia_env():
    with boa.swap_env(boa.NetworkEnv(SEPOLIA_URI)):
        boa.env.add_account(Account.from_key(PKEY))
        yield
