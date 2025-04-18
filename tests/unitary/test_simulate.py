import boa


def test_simulate_local():
    code = """
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
