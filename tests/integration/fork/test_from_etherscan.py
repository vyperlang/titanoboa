import os

import pytest

import boa
from boa.contracts.abi.abi_contract import RawLogEntry
from boa.rpc import to_bytes, to_hex

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


@pytest.mark.ignore_isolation
def test_crvusd_logs(api_key):
    c = boa.from_etherscan(
        "0x00e6Fd108C4640d21B40d02f18Dd6fE7c7F725CA", name="crvUSD", api_key=api_key
    )
    rpc = boa.env.evm.vm.state._account_db._rpc
    raw_logs = rpc.fetch(
        "eth_getLogs",
        [
            {
                "address": str(c.address),
                "fromBlock": to_hex(19699678 - 1),
                "toBlock": to_hex(19699678 + 1),
            }
        ],
    )
    log_entries = [
        RawLogEntry(
            address=log["address"],
            topics=[to_bytes(topic) for topic in log["topics"]],
            data=to_bytes(log["data"]),
        )
        for log in raw_logs
    ]
    parsed_logs = [c.parse_log(log) for log in log_entries]
    assert len(parsed_logs) == 2
    assert [str(log.args) for log in parsed_logs] == [
        "Transfer(sender=Address('0x0000000000000000000000000000000000000000'), "
        "receiver=Address('0x860b7Abd16672B33Bab84679526227adb283ed8f'), "
        "value=10311475843661588)",
        "AddLiquidity(provider=Address('0x860b7Abd16672B33Bab84679526227adb283ed8f'), "
        "token_amounts=[0, 10000000000000000], fees=[0, 310124289528], "
        "invariant=3904289717238430384026544, token_supply=3899779865542232381549763)",
    ]
