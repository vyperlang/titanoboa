import importlib
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Union

import vyper
from vyper.cli.vyper_compile import get_interface_codes
from vyper.compiler.phases import CompilerData

from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.contracts.vyper.compiler_utils import anchor_compiler_settings
from boa.contracts.vyper.vyper_contract import (
    VyperBlueprint,
    VyperContract,
    VyperDeployer,
)
from boa.explorer import fetch_abi_from_etherscan
from boa.util.abi import Address
from boa.util.disk_cache import DiskCache

_Contract = Union[VyperContract, VyperBlueprint]


_disk_cache = None


class BoaImporter(importlib.abc.MetaPathFinder):
    def __init__(self):
        self._path_lookup = {}

    # TODO: replace this with more modern `find_spec()`
    def find_module(self, fullname, package_path, target=None):
        path = Path(fullname.replace(".", "/")).with_suffix(".vy")

        for prefix in sys.path:
            to_try = Path(prefix) / path

            if to_try.exists():
                self._path_lookup[fullname] = to_try
                return self

        return None

    # TODO: replace with more modern `exec_module()` and `create_module()`
    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]

        # import system should guarantee this, but be paranoid
        if fullname not in self._path_lookup:
            raise ImportError(f"invariant violated: no lookup for {fullname}")

        path = self._path_lookup[fullname]
        ret = load_partial(path)

        # comply with PEP-302:
        ret.__name__ = path.name
        ret.__file__ = str(path)
        sys.modules[fullname] = ret
        return ret


sys.meta_path.append(BoaImporter())


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
        with anchor_compiler_settings(ret):
            _ = ret.bytecode, ret.bytecode_runtime  # force compilation to happen
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


def from_etherscan(
    address: Any, name=None, uri="https://api.etherscan.io/api", api_key=None
):
    addr = Address(address)
    abi = fetch_abi_from_etherscan(addr, uri, api_key)
    return ABIContractFactory.from_abi_dict(abi, name=name).at(addr)


__all__ = []  # type: ignore
