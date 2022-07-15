from typing import Union

import vyper
from vyper.compiler.phases import CompilerData

from boa.contract import VyperContract, VyperDeployer, VyperFactory
from boa.util.disk_cache import DiskCache

_Contract = Union[VyperContract, VyperFactory]


_disk_cache = None


def set_cache_dir(cache_dir="~/.cache/titanoboa"):
    global _disk_cache
    if cache_dir is None:
        _disk_cache = None
    compiler_version = f"{vyper.__version__}.{vyper.__commit__}"
    _disk_cache = DiskCache(cache_dir, compiler_version)


def compiler_data(source_code: str) -> CompilerData:
    global _disk_cache

    if _disk_cache is None:
        return CompilerData(source_code)

    def func():
        ret = CompilerData(source_code)
        ret.bytecode_runtime  # force compilation to happen
        return ret

    return _disk_cache.caching_lookup(source_code, func)


def load(filename: str, *args, **kwargs) -> _Contract:  # type: ignore
    with open(filename) as f:
        return loads(f.read(), *args, **kwargs)


def loads_partial(source_code: str) -> VyperDeployer:
    data = compiler_data(source_code)
    return VyperDeployer(data)


def load_partial(filename: str, *args, **kwargs) -> VyperDeployer:  # type: ignore
    with open(filename) as f:
        return loads_partial(f.read(), *args, **kwargs)


def loads(source_code: str, *args, as_factory=False, **kwargs) -> _Contract:  # type: ignore
    d = loads_partial(source_code)
    if as_factory:
        return d.deploy_as_factory(**kwargs)
    else:
        return d.deploy(*args, **kwargs)


def contract() -> _Contract:
    # returns an empty contract
    return loads("")
