import pytest

from boa.util.journal_dict import JournalingDict


def test_single_scope():
    x: JournalingDict = JournalingDict()
    x["a"] = 11
    x["a"] = 12
    with x.scoped():
        x["b"] = 13
        x["a"] = 14
        x["a"] = 15
    assert x["a"] == 12
    assert "b" not in x


def test_multi_scope():
    x: JournalingDict = JournalingDict()
    x["a"] = 11
    x["a"] = 12
    assert x["a"] == 12
    with x.scoped():
        assert x["a"] == 12
        x["b"] = 13
        x["b"] = 14
        x["a"] = 14
        x["a"] = 15
        with x.scoped():
            x["a"] += 1
            x["b"] = 16
            x["a"] += 1
            assert x["a"] == 17
            assert len(x) == 2
        assert x["a"] == 15

    assert len(x) == 1
    assert x["a"] == 12
    x.pop("a")
    assert len(x) == 0
    assert "b" not in x
