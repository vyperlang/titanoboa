from shutil import rmtree

import pytest

from boa.interpret import compiler_data
from boa.util.disk_cache import DiskCache

_dummy = compiler_data("", "")


def cache_miss():
    return _dummy


@pytest.fixture
def cache(tmp_path):
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()
    cache = DiskCache(str(cache_dir), "version_salt")
    yield cache
    rmtree(cache_dir)


def test_init(cache):
    assert cache.cache_dir.exists()
    assert cache.version_salt == "version_salt"
    assert cache.ttl == 7 * 24 * 3600  # default ttl
    assert cache.last_gc == 0


def test_collect_garbage(cache):
    assert cache.caching_lookup("key", cache_miss)
    cache.gc(force=True)
    assert cache.last_gc > 0


def test__get_location(cache):
    path = cache.cal("key")
    assert "version_salt" in str(path)
    assert ".pickle" in str(path)


def test_contains(cache):
    first = cache.caching_lookup("key", cache_miss)
    assert first == _dummy
    second = cache.caching_lookup("key", cache_miss)
    assert second.__dict__ == _dummy.__dict__
    assert first is not second, "should not be the same object given serialization"
