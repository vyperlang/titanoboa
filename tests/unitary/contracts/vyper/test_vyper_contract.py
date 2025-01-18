import boa


def test_decode_struct():
    code = """
struct Point:
    x: int8
    y: int8

point: Point

@deploy
def __init__():
    self.point = Point({x: 1, y: 2})
"""
    result = boa.loads(code)._storage.point.get()
    assert str(result) == "Point({'x': 1, 'y': 2})"


def test_decode_tuple():
    code = """
point: (int8, int8)

@deploy
def __init__():
    self.point[0] = 1
    self.point[1] = 2
"""
    assert boa.loads(code)._storage.point.get() == (1, 2)


def test_decode_string_array():
    code = """
point: int8[2]

@deploy
def __init__():
    self.point[0] = 1
    self.point[1] = 2
"""
    assert boa.loads(code)._storage.point.get() == [1, 2]


def test_decode_bytes_m():
    code = """
b: bytes2

@deploy
def __init__():
    self.b = 0xd9b6
"""
    assert boa.loads(code)._storage.b.get() == bytes.fromhex("d9b6")


def test_decode_dynarray():
    code = """
point: DynArray[int8, 10]

@deploy
def __init__():
    self.point = [1, 2]
"""
    assert boa.loads(code)._storage.point.get() == [1, 2]


def test_self_destruct():
    code = """
@external
def foo() -> bool:
    selfdestruct(msg.sender)
    """
    c = boa.loads(code)

    c.foo()


def test_contract_name():
    code = """
@external
def foo() -> bool:
    return True
    """
    c = boa.loads(code, name="return_one", filename="return_one.vy")

    assert c.contract_name == "return_one"
    assert c.filename == "return_one.vy"

    c = boa.loads(code, filename="a/b/return_one.vy")

    assert c.contract_name == "return_one"
    assert c.filename == "a/b/return_one.vy"

    c = boa.loads(code, filename=None, name="dummy_name")

    assert c.contract_name == "dummy_name"
    assert c.filename == "<unknown>"

    c = boa.loads(code, filename=None, name=None)

    assert c.contract_name == "<unknown>"
    assert c.filename == "<unknown>"


def test_stomp():
    code1 = """
VAR: immutable(uint256)

@deploy
def __init__():
    VAR = 12345

@external
def foo() -> uint256:
    return VAR

@external
def bar() -> bool:
    return True
    """
    code2 = """
VAR: immutable(uint256)

@deploy
def __init__():
    VAR = 12345

@external
def foo() -> uint256:
    return VAR

@external
def bar() -> bool:
    return False
    """

    deployer = boa.loads_partial(code1)

    c = deployer.deploy()

    assert c.foo() == 12345
    assert c.bar() is True

    deployer2 = boa.loads_partial(code2)

    c2 = deployer2.stomp(c.address)

    assert c2.foo() == 12345
    assert c2.bar() is False

    # the bytecode at the original contract has been stomped :scream:
    assert c.foo() == 12345
    assert c.bar() is False


def test_vyper_contract_logs():
    # test namedtuple decoder for logs
    # (note similarity to related test in test_vvm.mpy)
    code = """
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


def test_vyper_contract_nested_logs():
    # test namedtuple decoder for nested logs
    # (note similarity to related test in test_vvm.py)
    code1 = """
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


def test_vyper_contract_structs():
    # test namedtuple decoder for structs
    # (note similarity to related test in test_vvm.py)
    code = """
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
    assert type(t).__name__ == "MyStruct1"
    assert t.x == 1

    addy = boa.env.generate_address()
    s = c.bar(addy, 2)
    assert type(s).__name__ == "MyStruct2"
    assert s._0 == addy  # test renames
    assert s.x == 2

    u, v = c.baz(3, addy, 4)
    assert type(u).__name__ == "MyStruct1"
    assert u.x == 3
    assert type(v).__name__ == "MyStruct2"
    assert v._0 == addy
    assert v.x == 4
