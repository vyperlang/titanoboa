import pytest

import boa

FOO_CONTRACT = """
@external
def foo() -> uint256:
    return 5
"""

FOO_INTERFACE = """
@external
def foo() -> uint256:
    ...
"""


@pytest.fixture
def foo_contract():
    return boa.loads(FOO_CONTRACT)


@pytest.fixture
def foo_interface(foo_contract):
    return boa.loads_vyi(FOO_INTERFACE).at(foo_contract.address)


# from file
@pytest.fixture
def foo_interface2(foo_contract, tmp_path):
    p = tmp_path / "foo.vyi"
    with p.open("w") as f:
        f.write(FOO_INTERFACE)
    return boa.load_vyi(p).at(foo_contract.address)


def test_foo_interface(foo_interface):
    assert foo_interface.foo() == 5


def test_foo_interface2(foo_interface2):
    assert foo_interface2.foo() == 5
