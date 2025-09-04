import boa
import pytest


@pytest.mark.parametrize(
    "pragma_line",
    [
        "# pragma version 0.3.10",
        "# @version 0.3.10",
    ],
)
def test_vvm_eval_expr_and_stmt(pragma_line):
    src = f"""
{pragma_line}

bar: uint256
"""
    c = boa.loads(src)

    # Statement should return None
    assert c.eval("self.bar = 456") is None

    # Expression should return its value
    assert c.eval("self.bar") == 456
