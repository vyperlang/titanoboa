# Caching

## Forked States

Titanoboa automatically caches states when running in fork mode. It uses python's builtin [sqlite](https://docs.python.org/3/library/sqlite3.html) support
This allows forking to take less time and use less memory.

The cache file is by default located at `~/.cache/titanoboa/fork/chainid_<0x_chainid>-sqlite.db` (one sqlite db file is generated per chain id).
To customize this folder, pass the `cache_dir` argument to the `fork` function (see [fork](../api/testing.md#fork)).
In case `cache_dir` is set to `None`, the cache will be disabled.
To debug cache hits and misses, pass `debug=True` to the `fork` function.

!!! warning
    Caching a fresh block might lead to incorrect results and stale cache files.

!!! warning
    When running boa in parallel (e.g. with pytest-xdist), the cache file will be shared between all processes.
    This can lead to more requests being made than necessary if multiple processes are requesting the same block.

## Compilation results

By default, Titanoboa caches compilation results on Disk.
The location of this cache is by default `~/.cache/titanoboa` and the files are called `{sha256_digest}.pickle`.

To change the cache location, call [`set_cache_dir`](../api/cache.md#set_cache_dir) with the desired path.
In case the path is `None`, caching will be disabled.
Alternatively, call [`disable_cache`](../api/cache.md#disable_cache) to disable caching.

## Etherscan

The utility [`from_etherscan`](../api/load_contracts.md#from_etherscan) fetches the ABI for a contract at a given address from Etherscan and returns an `ABIContract` instance.

Given Etherscan is rate-limited, it is recommended to cache the results.
In order to enable this, Titanoboa uses the [requests_cache](https://pypi.org/project/requests-cache/) package.

If the package is available in the environment, all requests to Etherscan will be cached.
