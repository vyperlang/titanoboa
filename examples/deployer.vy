from vyper.interfaces import ERC20

FACTORY: immutable(address)

@external
def __init__(factory_address: address):
    FACTORY = factory_address

@external
def create_new_erc20(name: String[32], symbol: String[32], decimals: uint8, supply: uint256) -> ERC20:
    t: address = create_from_factory(FACTORY, name, symbol, decimals, supply, code_offset=3)
    return ERC20(t)
