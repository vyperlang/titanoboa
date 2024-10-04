from typing import Any

import vvm

from boa.util.disk_cache import get_disk_cache


def compile_source(*args, **kwargs) -> Any:
    """
    Compile Vyper source code via the VVM.
    When a disk cache is available, the result of the compilation is cached.
    Note the cache only works if the function is called the same way (args/kwargs).
    :param args: Arguments to pass to vvm.compile_source
    :param kwargs: Keyword arguments to pass to vvm.compile_source
    :return: Compilation output
    """
    disk_cache = get_disk_cache()

    def _compile():
        return vvm.compile_source(*args, **kwargs)

    if disk_cache is None:
        return _compile()

    cache_key = f"{args}{kwargs}"
    return disk_cache.caching_lookup(cache_key, _compile)
