from ethereum.ercs import IERC20

BLUEPRINT: immutable(address)

@deploy
def __init__(blueprint_address: address):
    BLUEPRINT = blueprint_address

@external
def create_new_erc20(name: String[32], symbol: String[32], decimals: uint8, supply: uint256) -> IERC20:
    t: address = create_from_blueprint(BLUEPRINT, name, symbol, decimals, supply, code_offset=3)
    return IERC20(t)
