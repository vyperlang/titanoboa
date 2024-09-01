import contextlib

import pytest

import boa
from boa import BoaError

source_code = """
@external
def foo(x: uint256):
    if x == 0:
        return
    if x == 1:
        raise  # reason: x is 1
    if x > 1:
        assert x + 1 == 5, "x is not 4"

@external
def bar(x: uint256):
    # test the other syntax
    assert x + 1 == 6  # @rekt x is not 5

@external
def baz(x: uint256) -> uint256:
    return x + 1  # rekt: overflow!

@external
def qux(x: uint256):
    assert (
        x + 1 ==
        x + 2 # reason: multiline
    )
"""


@contextlib.contextmanager
def check_raises():
    try:
        yield
        raise Exception("Did not raise")
    except ValueError:  # boa.reverts checks
        pass


@pytest.fixture(scope="module")
def contract():
    return boa.loads(source_code)


def test_always_reverts(contract):
    with boa.reverts():  # wildcard. always catches
        contract.foo(1)


def test_does_not_revert(contract):
    with check_raises():
        with boa.reverts():
            contract.foo(0)  # does not revert


def test_revert_reason(contract):
    # kwarg version
    with boa.reverts(reason="x is 1"):
        contract.foo(1)

    # arg version
    with boa.reverts("x is 1"):
        contract.foo(1)


def test_revert_wrong_reason_type(contract):
    with check_raises():
        with boa.reverts(foooo="x is 1"):
            contract.foo(1)


def test_revert_wrong_reason_string(contract):
    with check_raises():
        with boa.reverts(reason="x is 2"):
            contract.foo(1)


def test_revert_multiline_statement(contract):
    with boa.reverts(reason="multiline"):
        contract.qux(1)


def test_reverts_correct_reason(contract):
    with boa.reverts(vm_error="x is not 4"):
        contract.foo(3)

    with boa.reverts(compiler="safeadd"):
        contract.foo(2**256 - 1)

    with boa.reverts(compiler="safeadd"):
        contract.bar(2**256 - 1)


def test_reason_does_not_stomp_compiler_reason(contract):
    # check that reason cannot stomp compiler reason: here the revert should
    # be because of overflow and not because x is not 5.
    with check_raises():
        with boa.reverts(rekt="x is not 5"):
            contract.bar(2**256 - 1)


def test_compiler_overflow(contract):
    # but only in assert statements. in other cases, stomp!
    with boa.reverts(rekt="overflow!"):
        contract.baz(2**256 - 1)


def test_compiler_reason_does_not_stop_dev_reason(contract):
    # check that compiler reason does not stomp dev reason
    with check_raises():
        with boa.reverts(compiler="safeadd"):
            contract.bar(3)


def test_strip_internal_frames(contract):
    # but only in assert statements. in other cases, stomp!
    with pytest.raises(BoaError) as context:
        contract.baz(2**256 - 1)

    assert str(context.traceback[-1].path) == __file__


@pytest.mark.parametrize(
    "type_,empty", [("DynArray[uint8, 8]", []), ("String[8]", ""), ("Bytes[8]", b"")]
)
def test_no_oom_for_uninitialized_variable(type_, empty):
    c = boa.loads(
        f"""
struct Test:
    data: {type_}

data: public(HashMap[address, Test])

@external
def foo(x: uint8):
    assert x == 0, "x is not 0 (make the error string longer than 8 bytes)"
    # unreachable
    uninitialized: {type_}  = self.data[msg.sender].data
    """
    )
    with pytest.raises(BoaError) as error_context:
        c.foo(1)

    # if we got here, there was no OOM on frame decoding
    frame = error_context.value.args[1].last_frame
    # note it has garbage instead of empty data.
    assert frame.frame_detail["uninitialized"] != empty
    # check the frame is always bounded properly.
    assert len(frame.frame_detail["uninitialized"]) == 8


def test_revert_check_storage():
    c = boa.loads(
        """
counter: public(uint256)
@external
def add():
    self.counter += 1
    assert self.counter == 0
    """
    )
    with pytest.raises(BoaError) as context:
        c.add()

    assert "<storage: counter=1>" in str(context.value)
    assert "Revert(b'')" in str(context.value)

    assert 0 == c._storage.counter.get()
    assert 0 == c.counter()


def test_reverts_dev_reason():
    pool_code = """
@external
@pure
def some_math(x: uint256) -> uint256:
    assert x < 10 # dev: math not ok
    return x
"""
    math_code = """
math: address

interface Math:
    def some_math(x: uint256) -> uint256: pure

@deploy
def __init__(math: address):
    self.math = math

@external
def math_call():
    _: uint256 = staticcall Math(self.math).some_math(11)

@external
def math_call_with_reason():
    _: uint256 = staticcall Math(self.math).some_math(11)  # dev: call math
"""
    m = boa.loads(pool_code)
    p = boa.loads(math_code, m.address)
    with boa.reverts(dev="math not ok"):
        p.math_call()
    with boa.reverts(dev="call math"):
        p.math_call_with_reason()


def test_stack_trace(contract):
    c = boa.loads(
        """
interface HasFoo:
     def foo(x: uint256): nonpayable

@external
def revert(contract: HasFoo):
    extcall contract.foo(5)
    """
    )

    with pytest.raises(BoaError) as context:
        c.revert(contract.address)

    trace = [
        (line.contract_repr, line.error_detail, line.pretty_vm_reason)
        for line in context.value.stack_trace
    ]
    assert trace == [
        (repr(contract), "user revert with reason", "x is not 4"),
        (repr(c), "external call failed", "x is not 4"),
    ]


def test_trace_constructor_revert():
    code = """
@deploy
def __init__():
    assert False, "revert reason"
"""
    with pytest.raises(BoaError) as error_context:
        boa.loads(code)

    assert "revert reason" in str(error_context.value)


def test_trace_constructor_stack_trace():
    called_code = """
@external
@pure
def check(x: uint256) -> uint256:
    assert x < 10 # dev: less than 10
    return x
"""
    caller_code = """
interface Called:
    def check(x: uint256) -> uint256: pure

@deploy
def __init__(math: address, x: uint256):
    _: uint256 = staticcall Called(math).check(x)
"""
    called = boa.loads(called_code)
    boa.loads(caller_code, called.address, 0)
    with pytest.raises(BoaError) as error_context:
        boa.loads(caller_code, called.address, 10)

    trace = error_context.value.stack_trace
    assert [repr(frame.vm_error) for frame in trace] == ["Revert(b'')"] * 2
    assert [frame.dev_reason.reason_str for frame in trace] == ["less than 10"] * 2
