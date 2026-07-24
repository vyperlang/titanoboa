# Caching

## Forked States

Titanoboa automatically caches states when running in fork mode. It uses python's builtin [sqlite](https://docs.python.org/3/library/sqlite3.html) support
This allows forking to take less time and use less memory.

The cache file is located under `~/.cache/titanoboa/fork` by default. Remote RPCs share `chainid_<hex-chain-id>.sqlite.db`; loopback RPCs use `chainid_<hex-chain-id>-<rpc-hash>.sqlite.db` so ephemeral local nodes do not share state accidentally.
To customize this folder, pass `cache_dir=` to [`boa.fork`](../api/env/singleton.md#fork).
In case `cache_dir` is set to `None`, the cache will be disabled.
To debug cache hits and misses, pass `debug=True` to the `fork` function.

SQLite entries expire after 30 days. Reads refresh their expiry, so frequently used entries remain available. The cache is keyed by block-sensitive RPC requests; avoid forking mutable or insufficiently final blocks when reproducibility matters.

!!! warning
    Caching a fresh block might lead to incorrect results and stale cache files.

!!! warning
    When running boa in parallel (e.g. with pytest-xdist), the cache file will be shared between all processes.
    This can lead to more requests being made than necessary if multiple processes are requesting the same block.

## Compilation results

By default, Titanoboa caches compilation results on disk under `~/.cache/titanoboa/<vyper-version-and-commit>/<sha256>.pickle`. Compiler settings, source fingerprints, deployer type, and the Vyper version salt participate in cache identity.

Compilation entries expire after seven days without access. Garbage collection runs periodically during cache lookups.

To change the cache location, call [`boa.interpret.set_cache_dir`](../api/cache.md#set_cache_dir) with the desired path.
In case the path is `None`, caching will be disabled.
Alternatively, call [`disable_cache`](../api/cache.md#disable_cache) to disable caching.

## Etherscan

The utility [`from_etherscan`](../api/load_contracts.md#from_etherscan) fetches the ABI for a contract at a given address from Etherscan and returns an `ABIContract` instance.

Given Etherscan is rate-limited, it is recommended to cache the results.
In order to enable this, Titanoboa uses the [requests_cache](https://pypi.org/project/requests-cache/) package.

If `requests-cache` is installed, successful explorer responses are cached under `~/.cache/titanoboa/explorer_cache` for six hours. Failed API responses are not cached. Install the `forking-recommended` extra to include this dependency.
