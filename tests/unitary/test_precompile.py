import pytest

import boa


def _caller(fn_name: str) -> str:
    return f"""
@external
def call_it(v: uint256) -> uint256:
    return {fn_name}(v)
"""


def test_function_precompile():
    # register first: the precompile name becomes available at compile time
    @boa.precompile("def dbl_a(x: uint256) -> uint256")
    def double_precompile(x):
        return x * 2

    contract = boa.loads(_caller("dbl_a"))
    assert contract.call_it(21) == 42


def test_function_precompile_force_overwrite():
    @boa.precompile("def dbl_b(x: uint256) -> uint256")
    def double_v1(x):
        return x * 2

    @boa.precompile("def dbl_b(x: uint256) -> uint256", force=True)
    def double_v2(x):
        return x * 3

    contract = boa.loads(_caller("dbl_b"))
    assert contract.call_it(21) == 63


def test_function_precompile_requires_force():
    @boa.precompile("def dbl_c(x: uint256) -> uint256")
    def double_v1(x):
        return x * 2

    with pytest.raises(ValueError):

        @boa.precompile("def dbl_c(x: uint256) -> uint256")
        def double_v2(x):
            return x * 2
