import boa
from boa.util.eip5202 import get_create2_address

blueprint_code = """
@external
def some_function() -> uint256:
    return 5
"""

factory_code = """
@external
def create_child(blueprint: address, salt: bytes32) -> address:
    return create_from_blueprint(blueprint, code_offset=3, salt=salt)
"""


def test_create2_address():
    blueprint = boa.loads_partial(blueprint_code).deploy_as_blueprint()
    factory = boa.loads(factory_code)

    salt = b"\x01" * 32

    child_contract_address = factory.create_child(blueprint.address, salt)

    blueprint_bytecode = boa.env.get_code(blueprint.address)
    assert child_contract_address == get_create2_address(
        blueprint_bytecode, factory.address, salt
    )
