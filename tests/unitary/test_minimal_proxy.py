import pytest
import vyper
from eth_utils import to_canonical_address

import boa
from boa.contracts.vyper.vyper_contract import VyperContract
from boa.contracts.abi.abi_contract import ABIContract
from boa.util.eip5202 import get_create2_address

_blueprint_code = """
# pragma version {}

@external
def some_function() -> uint256:
    return 5

@external
def some_other_function():
    assert msg.sender == self  # dev: fail
"""

_factory_code = """
# pragma version {}

@external
def create_child(target: address) -> address:
    return create_minimal_proxy_to(target)
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


def test_minimal_proxy_registration(blueprint_code, factory_code, version):
    blueprint = boa.loads(blueprint_code)
    factory = boa.loads(factory_code)
    child_contract_address = factory.create_child(blueprint.address)

    # check registration works inside of titanoboa.apply_create_message
    child_contract = boa.env.lookup_contract(child_contract_address)
    if version == vyper.__version__:
        expected_contract_type = VyperContract
    else:
        expected_contract_type = ABIContract
    assert isinstance(child_contract, expected_contract_type)

    assert child_contract.some_function() == 5

    with boa.reverts(dev="fail"):
        child_contract.some_other_function()
