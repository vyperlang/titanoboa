import json
import textwrap
from pathlib import Path

import vyper
from vyper.cli.vyper_compile import get_interface_codes
from vyper.compiler.phases import CompilerData

from boa.util.disk_cache import DiskCache
from boa.vyper.contract import (
    ABIContractFactory,
    BoaError,
    VyperBlueprint,
    VyperContract,
    VyperDeployer,
)

_Contract = VyperContract | VyperBlueprint


_disk_cache = None


def set_cache_dir(cache_dir="~/.cache/titanoboa"):
    global _disk_cache
    if cache_dir is None:
        _disk_cache = None
        return
    compiler_version = f"{vyper.__version__}.{vyper.__commit__}"
    _disk_cache = DiskCache(cache_dir, compiler_version)


def compiler_data(source_code: str, contract_name: str, **kwargs) -> CompilerData:
    global _disk_cache

    def _ifaces():
        # use get_interface_codes to get the interface source dict
        # TODO revisit this once imports are cleaned up vyper-side
        ret = get_interface_codes(Path("."), {contract_name: source_code})
        return ret[contract_name]

    if _disk_cache is None:
        ifaces = _ifaces()
        ret = CompilerData(source_code, contract_name, interface_codes=ifaces, **kwargs)
        return ret

    def func():
        ifaces = _ifaces()
        ret = CompilerData(source_code, contract_name, interface_codes=ifaces, **kwargs)
        _ = ret.bytecode_runtime  # force compilation to happen
        return ret

    return _disk_cache.caching_lookup(str((kwargs, source_code)), func)


def load(filename: str, *args, **kwargs) -> _Contract:  # type: ignore
    name = filename
    # TODO: investigate if we can just put name in the signature
    if "name" in kwargs:
        name = kwargs.pop("name")
    with open(filename) as f:
        return loads(f.read(), *args, name=name, **kwargs, filename=filename)


def loads(
    source_code,
    *args,
    as_blueprint=False,
    name=None,
    filename=None,
    compiler_args=None,
    **kwargs,
):
    d = loads_partial(source_code, name, filename=filename, compiler_args=compiler_args)
    if as_blueprint:
        return d.deploy_as_blueprint(**kwargs)
    else:
        return d.deploy(*args, **kwargs)


def load_abi(filename: str, *args, name: str = None, **kwargs) -> ABIContractFactory:
    if name is None:
        name = filename
    with open(filename) as fp:
        return loads_abi(fp.read(), *args, name=name, **kwargs)


def loads_abi(json_str: str, *args, name: str = None, **kwargs) -> ABIContractFactory:
    return ABIContractFactory.from_abi_dict(json.loads(json_str), name, *args, **kwargs)


def loads_partial(
    source_code: str,
    name: str = None,
    filename: str = None,
    dedent: bool = True,
    compiler_args: dict = None,
) -> VyperDeployer:
    name = name or "VyperContract"  # TODO handle this upstream in CompilerData
    if dedent:
        source_code = textwrap.dedent(source_code)

    compiler_args = compiler_args or {}

    data = compiler_data(source_code, name, **compiler_args)
    return VyperDeployer(data, filename=filename)


def load_partial(filename: str, compiler_args=None) -> VyperDeployer:  # type: ignore
    with open(filename) as f:
        return loads_partial(
            f.read(), name=filename, filename=filename, compiler_args=compiler_args
        )


__all__ = ["BoaError"]
