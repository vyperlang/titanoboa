import boa
from boa.contracts.vvm.vvm_contract import _detect_version

mock_3_10_path = "tests/unitary/contracts/vvm/mock_3_10.vy"


def test_load_partial_vvm():
    contract_deployer = boa.load_partial(mock_3_10_path)
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_partial_vvm():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract_deployer = boa.loads_partial(code)
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_load_vvm():
    contract = boa.load(mock_3_10_path, 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_vvm():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract = boa.loads(code, 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_detect_version():
    code_floating = """
# pragma version ^0.3.9
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
"""
    assert _detect_version(code_floating) == "0.3.9"

    code_ge = """
# pragma version >=0.3.9
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
"""
    assert _detect_version(code_ge) == "0.3.9"

    code_fixed = """
# pragma version 0.3.9
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
"""
    assert _detect_version(code_fixed) == "0.3.9"


def test_detect_version_with_vyper_version():
    code_floating = """
# pragma version ^0.3.9
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
"""
    assert _detect_version(code_floating, vyper_version="0.3.9") == "0.3.9"
    assert _detect_version(code_floating, vyper_version="0.3.10") == "0.3.10"
    assert _detect_version(code_floating, vyper_version="0.4.0") == "0.3.9"

    code_ge = """
# pragma version >=0.3.9
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
"""
    assert _detect_version(code_ge, vyper_version="0.3.9") == "0.3.9"
    assert _detect_version(code_ge, vyper_version="0.3.10") == "0.3.10"
    assert _detect_version(code_ge, vyper_version="0.4.0") == "0.4.0"

    code_fixed = """
# pragma version 0.3.9
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
"""
    assert _detect_version(code_fixed, vyper_version="0.3.9") == "0.3.9"
    assert _detect_version(code_fixed, vyper_version="0.3.10") == "0.3.9"
    assert _detect_version(code_fixed, vyper_version="0.4.0") == "0.3.9"
