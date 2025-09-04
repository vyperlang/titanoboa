import boa


def _base_code():
    return """
# pragma version 0.3.10

bar: uint256
"""


def test_vvm_eval_expr_and_stmt():
    c = boa.loads(_base_code())

    # Statement should return None
    assert c.eval("self.bar = 456") is None

    # Expression should return its value
    assert c.eval("self.bar") == 456

