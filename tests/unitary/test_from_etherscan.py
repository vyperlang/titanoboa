import os

import boa

crvusd = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
voting_agent = "0xE478de485ad2fe566d49342Cbd03E49ed7DB3356"


def test_from_etherscan():
    boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
    contract = boa.from_etherscan(crvusd, name="crvUSD", api_key=os.environ["ETHERSCAN_API_KEY"])

    assert contract.totalSupply() > 0
    assert contract.symbol() == "crvUSD"


def test_proxy_contract():
    boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
    contract = boa.from_etherscan(voting_agent, name="VotingAgent", api_key=os.environ["ETHERSCAN_API_KEY"])

    assert contract.minTime() == 43200

