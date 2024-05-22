import os
from unittest.mock import patch

import pytest
from eth.vm.message import Message
from vyper.utils import method_id

import boa
from boa import Env

crvusd = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
voting_agent = "0xE478de485ad2fe566d49342Cbd03E49ed7DB3356"


@pytest.fixture(scope="module")
def api_key():
    return os.environ.get("ETHERSCAN_API_KEY")


@pytest.fixture(scope="module")
def crvusd_contract(api_key):
    return boa.from_etherscan(crvusd, name="crvUSD", api_key=api_key)


@pytest.fixture(scope="module")
def proxy_contract(api_key):
    return boa.from_etherscan(voting_agent, name="VotingAgent", api_key=api_key)


def test_crvusd_contract(crvusd_contract):
    assert crvusd_contract.totalSupply() > 0
    assert crvusd_contract.symbol() == "crvUSD"


def test_proxy_contract(proxy_contract):
    assert isinstance(proxy_contract._abi, list)
    assert proxy_contract.minTime() == 43200
    assert proxy_contract.voteTime() == 604800
    assert proxy_contract.minBalance() == 2500000000000000000000


@pytest.mark.parametrize("fresh_env", [True, False])
def test_prefetch_state(proxy_contract, rpc_url, fresh_env):
    env = boa.env
    if fresh_env:
        env = Env()
        env.fork(rpc_url)

    msg = Message(
        to=proxy_contract.address.canonical_address,
        sender=env.eoa.canonical_address,
        gas=0,
        value=0,
        code=proxy_contract._bytecode,
        data=method_id("minTime()"),
    )
    db = env.evm.vm.state._account_db
    db.try_prefetch_state(msg)
    account = db._account_cache[proxy_contract.address.canonical_address]
    assert db._journaldb[account.code_hash] == proxy_contract._bytecode


@pytest.mark.parametrize("prefetch", [True, False])
def test_prefetch_state_called_on_message(proxy_contract, prefetch):
    boa.env.evm._fork_try_prefetch_state = prefetch
    with patch("boa.vm.fork.AccountDBFork.try_prefetch_state") as mock:
        proxy_contract.minTime()
        assert mock.called == prefetch


@pytest.mark.parametrize("prefetch", [True, False])
def test_prefetch_state_called_on_deploy(proxy_contract, prefetch):
    boa.env.evm._fork_try_prefetch_state = prefetch
    with patch("boa.vm.fork.AccountDBFork.try_prefetch_state") as mock:
        boa.loads("")
        assert mock.called == prefetch
