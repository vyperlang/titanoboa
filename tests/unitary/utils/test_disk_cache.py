from shutil import rmtree

import pytest

from boa.interpret import compiler_data
from boa.util.disk_cache import CompileCache, DeployCache

_dummy = compiler_data("", "")


def cache_miss():
    return _dummy


@pytest.fixture
def cache(tmp_path):
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()
    cache = CompileCache(str(cache_dir), "version_salt")
    CompileCache._instance, old_cache = cache, CompileCache._instance
    yield cache
    rmtree(cache_dir)
    CompileCache._instance = old_cache


def test_deploy_cache_separate_instance(cache):
    assert CompileCache._instance == cache
    assert DeployCache._instance != cache


def test_init(cache):
    assert cache.cache_dir.exists()
    assert cache.version_salt == "version_salt"
    assert cache.ttl == 7 * 24 * 3600  # default ttl
    assert cache.last_gc == 0


def test_collect_garbage(cache):
    assert CompileCache.lookup("key", cache_miss)
    cache._collect_garbage(force=True)
    assert cache.last_gc > 0


def test__get_location(cache):
    path = cache._get_location("key")
    assert "version_salt" in str(path)
    assert ".pickle" in str(path)


def test_contains(cache):
    assert CompileCache.has("key") is False
    assert CompileCache.lookup("key", cache_miss) == _dummy
    assert CompileCache.has("key") is True
    assert CompileCache.lookup("key", cache_miss).__dict__ == _dummy.__dict__


def test_no_cache(cache):
    CompileCache._instance = None
    assert CompileCache.lookup("key", cache_miss) == _dummy
    with pytest.raises(TypeError):
        CompileCache.lookup("key", {})
    assert CompileCache.has("key") is None
    CompileCache._instance = cache
