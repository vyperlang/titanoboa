from boa.util.lrudict import lrudict


def test_lru_setdefault():
    d = lrudict(10)
    for x in range(20):
        d.setdefault_lambda(x, lambda k: x)
        d.setdefault_lambda(x, lambda k: x * 100)  # no effect
    assert d == {k: k for k in range(10, 20)}


def test_lru_set():
    d = lrudict(10)
    for x in range(20):
        d.setdefault_lambda(x, lambda k: x)
        d[x] = x * 100
    assert d == {k: k * 100 for k in range(10, 20)}
