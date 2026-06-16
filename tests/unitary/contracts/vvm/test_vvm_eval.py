import boa


def test_vvm_eval_expr_and_stmt():
    src = """
# pragma version 0.3.10

bar: uint256
"""
    c = boa.loads(src)

    assert c.eval("self.bar = 456") is None
    assert c.eval("self.bar", return_type="uint256") == 456
