# tests network mode against local anvil fork

import subprocess
import sys
import time

import pytest
import requests
from eth_account import Account

import boa
from boa.deployments import DeploymentsDB, set_deployments_db
from boa.network import NetworkEnv

ANVIL_FORK_PKEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
]


@pytest.fixture(scope="session")
def accounts():
    return [Account.from_key(pkey) for pkey in ANVIL_FORK_PKEYS]


@pytest.fixture(scope="module")
def free_port():
    # https://gist.github.com/bertjwregeer/0be94ced48383a42e70c3d9fff1f4ad0

    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 0))
    portnum = s.getsockname()[1]
    s.close()

    return portnum


@pytest.fixture(scope="module")
def anvil_env(free_port):
    # anvil_cmd = f"anvil --fork-url {MAINNET_ENDPOINT} --steps-tracing".split(" ")
    anvil_cmd = f"anvil --port {free_port} --steps-tracing".split(" ")
    anvil = subprocess.Popen(anvil_cmd, stdout=sys.stdout, stderr=sys.stderr)
    anvil_uri = f"http://localhost:{free_port}"

    try:
        # wait for anvil to come up
        while True:
            try:
                requests.head(anvil_uri)
                break
            except requests.exceptions.ConnectionError:
                time.sleep(0.1)

        yield NetworkEnv(anvil_uri)
    finally:
        anvil.terminate()
        try:
            anvil.wait(timeout=10)
        except subprocess.TimeoutExpired:
            anvil.kill()
            anvil.wait(timeout=1)


# run all tests with this forked environment
# XXX: maybe parametrize across anvil, hardhat and geth --dev for
# max coverage across VM implementations?
@pytest.fixture(scope="module", autouse=True)
def networked_env(accounts, anvil_env):
    with boa.swap_env(anvil_env), set_deployments_db(DeploymentsDB(":memory:")):
        for account in accounts:
            boa.env.add_account(account)
        yield
