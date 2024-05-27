import os

import pytest

import boa
from boa.contracts.abi.abi_contract import LogEntry
from boa.rpc import to_bytes

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
def test_crvusd_logs(crvusd_contract):
    # boa.env.fork(os.environ.get("MAINNET_ENDPOINT"))
    rpc = boa.env.evm.vm.state._account_db._rpc
    raw_logs = rpc.fetch(
        "eth_getLogs",
        [
            {
                "address": str(crvusd_contract.address),
                "fromBlock": "0x" + (19961143).to_bytes(4, "big").hex(),
                "toBlock": "0x" + (19961143).to_bytes(4, "big").hex(),
            }
        ],
    )
    log_entries = [
        LogEntry(
            address=log["address"],
            topics=[to_bytes(topic) for topic in log["topics"]],
            data=to_bytes(log["data"]),
        )
        for log in raw_logs
    ]
    parsed_logs = [crvusd_contract.parse_log(log) for log in log_entries]
    assert len(parsed_logs) == 2
    assert [str(log.args) for log in parsed_logs] == [
        "Transfer(sender=Address('0x4eBdF703948ddCEA3B11f675B4D1Fba9d2414A14'), "
        "receiver=Address('0xf081470f5C6FBCCF48cC4e5B82Dd926409DcdD67'), "
        "value=678964444503670483754)",
        "Transfer(sender=Address('0xf081470f5C6FBCCF48cC4e5B82Dd926409DcdD67'), "
        "receiver=Address('0x390f3595bCa2Df7d23783dFd126427CCeb997BF4'), "
        "value=678964444503670483754)",
    ]
