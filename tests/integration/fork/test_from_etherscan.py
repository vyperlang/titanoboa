import os

import pytest

import boa

crvusd = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
voting_agent = "0xE478de485ad2fe566d49342Cbd03E49ed7DB3356"


@pytest.fixture(scope="module")
def api_key():
    return os.environ.get("ETHERSCAN_API_KEY")


@pytest.fixture(scope="module")
def crvusd_contract(api_key):
    contract = boa.from_etherscan(crvusd, name="crvUSD", api_key=api_key)

    return contract


@pytest.fixture(scope="module")
def proxy_contract(api_key):
    contract = boa.from_etherscan(voting_agent, name="VotingAgent", api_key=api_key)

    return contract


def test_crvusd_contract(crvusd_contract):
    assert crvusd_contract.totalSupply() > 0
    assert crvusd_contract.symbol() == "crvUSD"


def test_proxy_contract(proxy_contract):
    assert isinstance(proxy_contract._abi, dict)
    assert proxy_contract.minTime() == 43200
    assert proxy_contract.voteTime() == 604800
    assert proxy_contract.minBalance() == 2500000000000000000000
