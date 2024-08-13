import os
from unittest.mock import patch

import pytest
from eth.vm.message import Message

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
def test_prefetch_state(rpc_url, fresh_env, crvusd_contract):
    if fresh_env:
        # the contract was loaded from abi, test it against a fresh env too
        env = Env()
        env.fork(rpc_url)
    else:
        env = boa.env

    msg = Message(
        to=crvusd_contract.address.canonical_address,
        sender=env.eoa.canonical_address,
        gas=30000,
        value=0,
        code=crvusd_contract._bytecode,
        data=crvusd_contract.burn.prepare_calldata(0),
    )

    db = env.state._account_db
    db.try_prefetch_state(msg)

    # patch the RPC, so we make sure to use the cache
    with patch("boa.rpc.EthereumRPC.fetch", side_effect=AssertionError):
        code = db.get_code(crvusd_contract.address.canonical_address)
        storage = db.get_storage(crvusd_contract.address.canonical_address, slot=2)

        crvusd_contract.env = env
        assert code == crvusd_contract._bytecode
        assert storage == crvusd_contract.totalSupply()


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
