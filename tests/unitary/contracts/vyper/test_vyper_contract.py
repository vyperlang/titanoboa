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
