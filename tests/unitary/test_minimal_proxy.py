import pytest
import vyper

import boa
from boa.contracts.vyper.vyper_contract import VyperContract

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
    if version != vyper.__version__:
        pytest.skip("not working yet for vvm contracts")

    blueprint = boa.loads(blueprint_code)
    factory = boa.loads(factory_code)
    child_contract_address = factory.create_child(blueprint.address)

    # check registration works inside of titanoboa.apply_create_message
    child_contract = boa.env.lookup_contract(child_contract_address)
    assert isinstance(child_contract, VyperContract)

    assert child_contract.some_function() == 5

    with boa.reverts(dev="fail"):
        child_contract.some_other_function()

    # second element is wrong, leaving it here to notify if this gets fixed
    error_pieces = ["assert msg.sender == self  # dev: fail", "return 5"]

    stack_trace = str(child_contract.stack_trace())
    for error in error_pieces:
        assert error in stack_trace, (error, stack_trace)
