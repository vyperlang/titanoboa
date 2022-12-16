import pytest

import boa

source_code = """
@external
@view
def foo(a: uint256, b: uint256) -> uint256:
    return unsafe_mul(a, b) + unsafe_div(a, b)

@external
@view
def bar(a: uint256, b: uint256) -> uint256:
    return isqrt(unsafe_div(a, b) + unsafe_mul(a, b))
"""

SETTINGS = {"max_examples": 20, "deadline": None}


@pytest.fixture(scope="module")
def boa_contract():
    return boa.loads(source_code)


def test_call_profiling_disabled_by_default(boa_contract):

    assert not boa_contract.profile_calls
    assert not boa_contract.call_profile


@pytest.mark.parametrize("a,b", [(42, 69), (420, 690), (42, 690), (420, 69)])
@pytest.mark.ignore_isolation
def test_populate_call_profile_property(boa_contract, a, b):

    boa_contract.profile_calls = True
    boa_contract.foo(a, b)
    boa_contract.bar(a, b)

    assert boa_contract.call_profile
    combined_calls = {}
    for d in (pytest.call_profile, boa_contract.call_profile):
        for key, value in d.items():
            if key not in combined_calls.keys():
                combined_calls[key] = value
            else:
                combined_calls[key].extend(value)

    pytest.call_profile = combined_calls
