from boa.util.lrudict import lrudict


def test_lru():
    d = lrudict(10)
    for x in range(20):
        d.setdefault_lambda(x, lambda k: x)
        d.setdefault_lambda(x, lambda k: x * 100)
    assert d == {k: k * 100 for k in range(10, 20)}
