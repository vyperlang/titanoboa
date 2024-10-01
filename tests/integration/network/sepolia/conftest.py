# tests network mode against sepolia

import os

import pytest
from eth_account import Account

import boa
from boa.deployments import DeploymentsDB, set_deployments_db

PKEY = os.environ["SEPOLIA_PKEY"]
SEPOLIA_URI = os.environ["SEPOLIA_ENDPOINT"]


# run all tests with testnet
@pytest.fixture(scope="module", autouse=True)
def sepolia_env():
    with boa.set_network_env(SEPOLIA_URI), set_deployments_db(
        DeploymentsDB(":memory:")
    ):
        boa.env.add_account(Account.from_key(PKEY))
        yield
