import re

import pytest
import yaml
from vyper.compiler.output import build_abi_output

import boa
from boa import BoaError
from boa.contracts.abi.abi_contract import ABIContractFactory, ABIFunction
from boa.util.abi import Address


def load_via_abi(code):
    vyper_contract = boa.loads(code)
    abi = build_abi_output(vyper_contract.compiler_data)
    abi_contract = ABIContractFactory.from_abi_dict(abi).at(vyper_contract.address)
    return abi_contract, vyper_contract


@pytest.fixture()
def load_solidity_from_yaml(get_filepath):
    """
    Fixture to load a solidity contract from a yaml file.
    The file is expected to include the "abi" and "bytecode" fields.
    This is used to test ABI features that cannot be tested with Vyper.
    """

    def _load(yaml_filename):
        with open(get_filepath(f"fixtures/solidity_{yaml_filename}.yaml")) as f:
            data = yaml.safe_load(f)
        bytecode = bytes.fromhex(data["bytecode"]["object"])
        address, _ = boa.env.deploy_code(bytecode=bytecode)
        deployer = ABIContractFactory.from_abi_dict(data["abi"])
        return deployer.at(address)

    return _load


@pytest.mark.parametrize(
    "selector,value", [("from", "123"), ("global", "global"), ("local", "local")]
)
def test_python_keywords(load_solidity_from_yaml, selector, value):
    """
    Test that solidity contract can be used even if they use protected keywords.
    """
    contract = load_solidity_from_yaml("python_keywords")
    assert getattr(contract, selector)(value) is None
    assert getattr(contract, f"_{selector}")() == value


def test_solidity_overloading(load_solidity_from_yaml):
    contract = load_solidity_from_yaml("overload")
    with pytest.raises(Exception) as exc_info:
        contract.f(0)
    (error,) = exc_info.value.args
    assert (
        "Ambiguous call to f. Arguments can be encoded to multiple overloads: "
        "f(int8), f(uint256). (Hint: try using `disambiguate_signature=` "
        "to disambiguate)." == error
    )
    assert contract.f(-1) == -1
    assert contract.f(1000) == 1000


@pytest.mark.parametrize("abi_signature", ["f(int8)", "f(uint256)"])
def test_solidity_overloading_given_type(load_solidity_from_yaml, abi_signature):
    contract = load_solidity_from_yaml("overload")
    assert contract.f(0, disambiguate_signature=abi_signature) == 0


def test_solidity_bad_overloading_given_type(load_solidity_from_yaml):
    contract = load_solidity_from_yaml("overload")
    with pytest.raises(Exception) as exc_info:
        contract.f(0, disambiguate_signature="(int256)")
    (error,) = exc_info.value.args
    assert "Could not find matching f function for given arguments." == error


def test_address():
    code = """
@external
def test(_a: address) -> address:
    return _a
    """
    abi_contract, _ = load_via_abi(code)
    sender = boa.env.eoa
    result = abi_contract.test(sender)
    assert result == sender
    assert isinstance(result, Address)


def test_address_nested():
    code = """
struct Test:
    address: address
    number: uint256

@external
@view
def test(_a: DynArray[uint256, 100]) -> ((DynArray[Test, 2], uint256), uint256):
    first: DynArray[Test, 2] = [
        Test({address: msg.sender, number: _a[0]}),
        Test({address: msg.sender, number: _a[1]}),
    ]
    return (first, _a[2]), _a[3]
    """
    abi_contract, vyper_contract = load_via_abi(code)
    deployer_contract = abi_contract.deployer.at(abi_contract.address)
    given = [1, 2, 3, 4, 5]
    sender = Address(boa.env.eoa)
    expected = (([(sender, 1), (sender, 2)], 3), 4)
    abi_result = abi_contract.test(given)

    assert abi_result == expected
    assert isinstance(abi_result[0][0][0][0], Address)

    assert vyper_contract.test(given) == expected
    assert deployer_contract.test(given) == abi_result


def test_overloading():
    code = """
@external
def test(a: uint128 = 0, b: uint128 = 0) -> uint128:
    return a + b
"""
    c, _ = load_via_abi(code)
    assert c.test() == 0
    assert c.test(1) == 1
    assert c.test(a=1) == 1
    assert c.test(1, 2) == 3
    assert c.test(a=1, b=2) == 3
    assert c.test(a=1, b=2, value=0, gas=None) == 3

    with pytest.raises(Exception) as exc_info:
        c.test(1, 2, 3)
    (error,) = exc_info.value.args
    assert "Could not find matching test function for given arguments." == error

    with pytest.raises(Exception) as exc_info:
        c.test(1, c=2)
    (error,) = exc_info.value.args
    assert (
        "Missing keyword argument 'b' for `(uint128,uint128)`. Passed (1,) {'c': 2}"
        == error
    )


def test_bad_address():
    with pytest.warns(UserWarning, match=r"there is no bytecode at that address!$"):
        ABIContractFactory.from_abi_dict([]).at(boa.env.eoa)


def test_abi_reverts():
    code = """
@external
def test(n: uint256) -> uint256:
    assert n > 0
    return 0
"""
    c, _ = load_via_abi(code)
    with pytest.raises(BoaError) as exc_info:
        c.test(0)
    ((error,),) = exc_info.value.args
    assert re.match(r"^ +\(.*\.test\(uint256\) -> \['uint256']\)$", error)

    with pytest.raises(Exception) as exc_info:
        c.test(1, 2)
    (error,) = exc_info.value.args
    assert "expected 1 arguments, got 2" in error


def test_abi_not_deployed():
    f = ABIFunction({"name": "test", "inputs": [], "outputs": []}, contract_name="c")
    with pytest.raises(Exception) as exc_info:
        f()
    (error,) = exc_info.value.args
    assert "Cannot call ABI c.test() -> [] without deploying contract." == error


def test_method_not_in_abi():
    code = """
@external
def test(n: uint256) -> uint256:
    assert n > 0
    return n
"""
    abi_contract, _ = load_via_abi(code)
    abi_contract.method_id_map.clear()  # mess up the method IDs
    with pytest.raises(BoaError) as exc_info:
        abi_contract.test(0)
    ((error,),) = exc_info.value.args
    assert re.match(r"^ +\(unknown method id .*\.0x29e99f07\)$", error)
