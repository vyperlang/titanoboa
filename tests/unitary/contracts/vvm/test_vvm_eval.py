import boa


def test_vvm_eval_expr_and_stmt():
    # Use pragma to ensure the VVM code path
    src = """
# pragma version 0.3.10

bar: uint256
"""
    c = boa.loads(src)

    # Statement should return None
    assert c.eval("self.bar = 456") is None

    # Expression should return its value (explicit type)
    assert c.eval("self.bar", return_type="uint256") == 456
