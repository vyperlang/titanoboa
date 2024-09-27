import pytest
import vyper
from eth_utils import to_canonical_address

import boa
from boa.util.eip5202 import get_create2_address

_blueprint_code = """
# pragma version {}

@external
def some_function() -> uint256:
    return 5
"""

_factory_code = """
# pragma version {}

@external
def create_child(blueprint: address, salt: bytes32) -> address:
    return create_from_blueprint(blueprint, code_offset=3, salt=salt)
"""

VERSIONS = [vyper.__version__, "0.3.10"]


@pytest.fixture(params=VERSIONS)
def version(request):
    return request.param


@pytest.fixture
def blueprint_code(version):
    return _blueprint_code.format(version)


@pytest.fixture
def factory_code(version):
    return _factory_code.format(version)


def test_create2_address(blueprint_code, factory_code):
    blueprint = boa.loads_partial(blueprint_code).deploy_as_blueprint()
    factory = boa.loads(factory_code)

    salt = b"\x01" * 32

    child_contract_address = factory.create_child(blueprint.address, salt)

    blueprint_bytecode = boa.env.get_code(blueprint.address)
    assert child_contract_address == get_create2_address(
        blueprint_bytecode, factory.address, salt
    )


def test_create2_address_bad_salt(blueprint_code):
    blueprint = boa.loads_partial(blueprint_code).deploy_as_blueprint()
    blueprint_bytecode = boa.env.get_code(to_canonical_address(blueprint.address))
    with pytest.raises(ValueError) as e:
        get_create2_address(blueprint_bytecode, blueprint.address, salt=b"")

    assert str(e.value) == "bad salt (must be bytes32): b''"
