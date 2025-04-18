import pytest

import boa


@pytest.mark.parametrize("pragma", ["# pragma version 0.4.0", ""])
def test_simulate_local(pragma):
    code = f"""
{pragma}

counter: public(uint256)

@external
def get_next_counter() -> uint256:
    self.counter += 1
    return self.counter
    """
    c = boa.loads(code)

    assert c.get_next_counter() == 1
    assert c.counter() == 1

    assert c.get_next_counter(simulate=True) == 2
    assert c.counter() == 1
