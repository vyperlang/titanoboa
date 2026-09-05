import pytest

import boa
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.contracts.call_trace import TraceSource
from boa.contracts.vyper.vyper_contract import VyperError


@pytest.mark.parametrize("data", [b"", b"\x12\x34\x56\x78", b"\x08\xc3y\xa0"])
def test_error_data_without_decodable_reason(data):
    assert TraceSource._format_error(data) == "0x" + data.hex()


def test_abi_error_displays_call_trace_once():
    native = boa.loads(
        """
@external
def fail():
    raise "unique revert reason"
"""
    )
    contract = ABIContractFactory.from_abi_dict(native.abi, name="Example").at(
        native.address
    )
    with pytest.raises(boa.BoaError) as exc:
        contract.fail()

    error = exc.value
    rendered = str(error)
    assert type(error) is boa.BoaError
    assert rendered.count("Example.fail(") == 1
    assert rendered.count("unique revert reason") == 1
    assert "interface at" not in rendered
    assert error.args == (error.call_trace, error.stack_trace)
    assert "interface at" in str(error.stack_trace)
    assert str(error) == rendered


@pytest.mark.parametrize("constructor", [False, True])
def test_native_vyper_error_retains_source_details(constructor):
    code = """
@external
def fail():
    raise "unique revert reason"
"""
    if constructor:
        code = code.replace("@external", "@deploy").replace("fail()", "__init__()")

    with pytest.raises(boa.BoaError) as exc:
        contract = boa.loads(code)
        contract.fail()

    error = exc.value
    assert isinstance(error, VyperError)
    rendered = str(error)
    assert "unique revert reason" in rendered
    assert str(error.stack_trace) in rendered
    assert "user revert with reason" in rendered
    assert str(error) == rendered


@pytest.mark.parametrize("constructor", [False, True])
def test_vvm_error_retains_revert_reason(constructor):
    code = """
# pragma version 0.3.10
@external
def fail():
    raise "unique revert reason"
"""
    if constructor:
        code = code.replace("fail()", "__init__()")

    with pytest.raises(boa.BoaError) as exc:
        contract = boa.loads(code, name="Example")
        contract.fail()

    error = exc.value
    assert type(error) is boa.BoaError
    rendered = str(error)
    assert rendered.count("unique revert reason") == 1
    assert "interface at" not in rendered
    assert str(error) == rendered


def test_abi_error_retains_vm_failure():
    native = boa.loads(
        """
@external
def foo() -> uint256:
    return 42
"""
    )
    contract = ABIContractFactory.from_abi_dict(native.abi).at(native.address)
    with pytest.raises(boa.BoaError) as exc:
        contract.foo(gas=1)

    assert "OutOfGas" in str(exc.value)


def test_unknown_abi_method_retains_revert_reason():
    native = boa.loads(
        """
@external
def fail():
    raise "unique revert reason"
"""
    )
    contract = ABIContractFactory.from_abi_dict(native.abi).at(native.address)
    contract.method_id_map.clear()
    with pytest.raises(boa.BoaError) as exc:
        contract.fail()

    assert str(exc.value).count("unique revert reason") == 1
