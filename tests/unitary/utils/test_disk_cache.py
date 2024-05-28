from shutil import rmtree

import pytest

from boa.util.disk_cache import DiskCache


def cache_miss():
    return "value"


@pytest.fixture
def cache(tmp_path):
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()
    cache = DiskCache(str(cache_dir), "version_salt")
    DiskCache._instance, old_cache = cache, DiskCache._instance
    yield cache
    rmtree(cache_dir)
    DiskCache._instance = old_cache


def test_init(cache):
    assert cache.cache_dir.exists()
    assert cache.version_salt == "version_salt"
    assert cache.ttl == 7 * 24 * 3600  # default ttl
    assert cache.last_gc == 0


def test_collect_garbage(cache):
    assert DiskCache.lookup("key", cache_miss)
    cache._collect_garbage(force=True)
    assert cache.last_gc > 0


def test__get_location(cache):
    path = cache._get_location("key")
    assert "version_salt" in str(path)
    assert ".pickle" in str(path)


def test_contains(cache):
    assert DiskCache.has("key") is False
    assert DiskCache.lookup("key", cache_miss) == ("value", False)
    assert DiskCache.has("key") is True
    assert DiskCache.lookup("key", cache_miss) == ("value", True)


def test_no_cache(cache):
    DiskCache._instance = None
    assert DiskCache.lookup("key", cache_miss) == ("value", None)
    assert DiskCache.lookup("key", cache_miss) == ("value", None)
    assert DiskCache.has("key") is None
    DiskCache._instance = cache
