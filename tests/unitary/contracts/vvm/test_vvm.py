import pytest

import boa

mock_3_10_path = "tests/unitary/contracts/vvm/mock_3_10.vy"


def test_load_partial_vvm():
    contract_deployer = boa.load_partial(mock_3_10_path)
    contract = contract_deployer.deploy(43)
    assert contract._computation is not None

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_partial_vvm():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract_deployer = boa.loads_partial(code)
    contract = contract_deployer.deploy(43)
    assert contract._computation is not None

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_load_vvm():
    contract = boa.load(mock_3_10_path, 43)
    assert contract._computation is not None

    assert contract.foo() == 42
    assert contract.bar() == 43


@pytest.mark.parametrize(
    "version_pragma",
    [
        "# @version ^0.3.1",
        "# @version ^0.3.7",
        "# @version ==0.3.10",
        "# @version ~=0.3.10",
        "# @version 0.3.10",
        "# pragma version >=0.3.8, <0.4.0, !=0.3.10",
        "# pragma version ==0.4.0rc3",
    ],
)
def test_load_complex_version_vvm(version_pragma):
    contract = boa.loads(version_pragma + "\nfoo: public(uint256)")
    assert contract._computation is not None
    assert contract.foo() == 0


def test_loads_vvm():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract = boa.loads(code, 43)
    assert contract._computation is not None

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_forward_args_on_deploy():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract_vvm_deployer = boa.loads_partial(code)

    random_addy = boa.env.generate_address()

    contract = contract_vvm_deployer.deploy(43, override_address=random_addy)
    assert contract._computation is not None

    assert random_addy == contract.address


def test_vvm_name_forwarding():
    # test that names passed to loads_partial() and deploy()
    # get forwarded to the final contract properly.
    with open(mock_3_10_path) as f:
        code = f.read()

    deployer1 = boa.loads_partial(code, name="foo")
    deployer2 = boa.loads_partial(code, name="bar")

    assert deployer1.name == "foo"
    assert deployer2.name == "bar"

    c1 = deployer1.deploy(100)
    c2 = deployer2.deploy(101)
    assert c1.contract_name == "foo"
    assert c2.contract_name == "bar"

    # test override in deploy()
    c = deployer1.deploy(100, contract_name="baz")
    assert c.contract_name == "baz"


def test_ctor_revert():
    # test that revert in ctor throws proper BoaError
    code = """
# pragma version 0.3.10
@external
def __init__():
    raise
    """
    with boa.reverts():
        boa.loads(code)


def test_logs():
    # test namedtuple decoder for logs
    code = """
# pragma version 0.3.10

event MyEvent1:
    x: uint256

event MyEvent2:
    _from: address
    addr: address

event MyEvent3:
    addr: address
    # throw in out-of-order indexed field for fun
    _from: indexed(address)

@external
def foo(x: uint256, y: address):
    log MyEvent1(x)
    log MyEvent2(msg.sender, y)
    log MyEvent2(y, msg.sender)
    log MyEvent3(y, msg.sender)
    """

    c = boa.loads(code)

    addr = boa.env.generate_address()
    c.foo(1, addr)

    logs = c.get_logs()
    assert len(logs) == 4

    assert type(logs[0]).__name__ == "MyEvent1"
    assert logs[0].x == 1

    assert type(logs[1]).__name__ == "MyEvent2"
    # namedtuple renames things with "from" to _1, _2 etc
    assert logs[1]._1 == boa.env.eoa
    assert logs[1].addr == addr

    assert type(logs[2]).__name__ == "MyEvent2"
    assert logs[2]._1 == addr
    assert logs[2].addr == boa.env.eoa

    assert type(logs[3]).__name__ == "MyEvent3"
    assert logs[3].addr == addr
    assert logs[3]._2 == boa.env.eoa

    for log in logs:
        assert log.address == c.address


def test_nested_logs():
    # test namedtuple decoder for nested logs
    code1 = """
# pragma version 0.3.10
event Foo:
    pass

@external
def foo():
    log Foo()
    """
    code2 = """
# pragma version 0.3.10
event Foo:
    pass

interface CallFoo:
    def foo(): nonpayable

@external
def bar(target: CallFoo):
    target.foo()
    log Foo()
    target.foo()
    """
    c1 = boa.loads(code1)
    c2 = boa.loads(code2)

    c1.foo()
    logs = c1.get_logs()
    assert len(logs) == 1
    assert type(logs[0]).__name__ == "Foo"
    assert len(logs[0]) == 1
    assert logs[0].address == c1.address

    c2.bar(c1)
    logs = c2.get_logs()
    expected_addresses = [c1.address, c2.address, c1.address]
    assert len(logs) == len(expected_addresses) == 3

    for addr, log in zip(expected_addresses, logs):
        assert type(log).__name__ == "Foo"
        assert len(log) == 1
        assert log.address == addr

    # test with no subcalls
    logs = c2.get_logs(include_child_logs=False)
    expected_addresses = [c2.address]
    assert len(logs) == len(expected_addresses) == 1

    for log in logs:
        assert type(log).__name__ == "Foo"
        assert len(log) == 1
        assert log.address == c2.address


def test_structs():
    # test namedtuple decoder for structs
    code = """
# pragma version 0.3.10

struct MyStruct1:
    x: uint256

struct MyStruct2:
    _from: address
    x: uint256

@external
def foo(x: uint256) -> MyStruct1:
    return MyStruct1({x: x})

@external
def bar(_from: address, x: uint256) -> MyStruct2:
    return MyStruct2({_from: _from, x: x})

@external
def baz(x: uint256, _from: address, y: uint256) -> (MyStruct1, MyStruct2):
    return MyStruct1({x: x}), MyStruct2({_from: _from, x: y})
    """

    c = boa.loads(code)

    t = c.foo(1)
    # don't get correct struct names from the abi.
    # assert type(t).__name__ == "MyStruct1"
    assert t.x == 1

    addy = boa.env.generate_address()
    s = c.bar(addy, 2)
    # assert type(s).__name__ == "MyStruct2"
    assert s._0 == addy  # test renames
    assert s.x == 2

    u, v = c.baz(3, addy, 4)
    # assert type(u).__name__ == "MyStruct1"
    assert u.x == 3
    # assert type(v).__name__ == "MyStruct2"
    assert v._0 == addy
    assert v.x == 4
