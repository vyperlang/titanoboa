from typing import Optional, Union

import vyper
from vyper.compiler.phases import CompilerData

from boa.contract import BoaError, VyperBlueprint, VyperContract, VyperDeployer
from boa.util.disk_cache import DiskCache

_Contract = Union[VyperContract, VyperBlueprint]


_disk_cache = None


def set_cache_dir(cache_dir="~/.cache/titanoboa"):
    global _disk_cache
    if cache_dir is None:
        _disk_cache = None
        return
    compiler_version = f"{vyper.__version__}.{vyper.__commit__}"
    _disk_cache = DiskCache(cache_dir, compiler_version)


def compiler_data(source_code: str, contract_name: str) -> CompilerData:
    global _disk_cache

    if _disk_cache is None:
        return CompilerData(source_code, contract_name)

    def func():
        ret = CompilerData(source_code, contract_name)
        ret.bytecode_runtime  # force compilation to happen
        return ret

    return _disk_cache.caching_lookup(source_code, func)


def load(filename: str, *args, **kwargs) -> _Contract:  # type: ignore
    with open(filename) as f:
        return loads(f.read(), *args, name=filename, **kwargs)


def loads(source_code, *args, as_blueprint=False, name=None, **kwargs):
    d = loads_partial(source_code, name)
    if as_blueprint:
        return d.deploy_as_blueprint(**kwargs)
    else:
        return d.deploy(*args, **kwargs)


def loads_partial(source_code: str, name: Optional[str] = None) -> VyperDeployer:
    name = name or "VyperContract"  # TODO handle this upstream in CompilerData
    data = compiler_data(source_code, name)
    return VyperDeployer(data)


def load_partial(filename: str) -> VyperDeployer:  # type: ignore
    with open(filename) as f:
        return loads_partial(f.read(), name=filename)


__all__ = ["BoaError"]
