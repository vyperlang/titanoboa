import boa
import pytest

source_code = """
@internal
@pure
def _test_bool(a: uint256, b: bool = False) -> bool:
    return True


@internal
@pure
def _sort(unsorted_x: uint256[3]) -> uint256[3]:
    x: uint256[3] = unsorted_x
    temp_var: uint256 = x[0]
    if x[0] < x[1]:
        x[0] = x[1]
        x[1] = temp_var
    if x[0] < x[2]:
        temp_var = x[0]
        x[0] = x[2]
        x[2] = temp_var
    if x[1] < x[2]:
        temp_var = x[1]
        x[1] = x[2]
        x[2] = temp_var

    return x


@external
@view
def sort(unsorted_x: uint256[3]) -> uint256[3]:
    return self._sort(unsorted_x)
"""

c = boa.loads(source_code)

assert c.internal._test_bool(10, True)
assert c.internal._sort([1, 2, 3]) == c.sort([1, 2, 3])
assert c.internal._test_bool(10)
