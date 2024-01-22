import boa, os

crvusd = '0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E'
voting_agent = "0xE478de485ad2fe566d49342Cbd03E49ed7DB3356"


def test_from_etherscan_abi():

    boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
    abi = boa.from_etherscan_abi(crvusd, api_key=os.environ["ETHERSCAN_API_KEY"])

    return abi


def test_from_etherscan():

    boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
    crvusd =  boa.from_etherscan(crvusd, api_key=os.environ["ETHERSCAN_API_KEY"])
    
    return crvusd.name()


def test_proxy_contract():

    boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
    contract =  boa.from_etherscan_abi(voting_agent, api_key=os.environ["ETHERSCAN_API_KEY"])

    return contract.getVote(100)


def test_proxy_contract_abi():

    boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
    contract =  boa.from_etherscan_abi(voting_agent, api_key=os.environ["ETHERSCAN_API_KEY"])

    return contract
