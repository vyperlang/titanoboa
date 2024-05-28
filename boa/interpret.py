import json
import sys
import textwrap
from importlib.abc import MetaPathFinder
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader
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
from boa.util.disk_cache import CompileCache

_Contract = Union[VyperContract, VyperBlueprint]


def set_cache_dir(cache_dir: str | None = "~/.cache/titanoboa"):
    if cache_dir is None:
        CompileCache._instance = None
        return
    compiler_version = f"{vyper.__version__}.{vyper.__commit__}"
    CompileCache._instance = CompileCache(cache_dir, compiler_version)


def disable_cache():
    set_cache_dir(cache_dir=None)


set_cache_dir()  # enable caching, by default!


class BoaImporter(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        path = Path(fullname.replace(".", "/")).with_suffix(".vy")

        for prefix in sys.path:
            to_try = Path(prefix) / path

            if to_try.exists():
                loader = BoaLoader(fullname, str(to_try))
                return spec_from_loader(fullname, loader)


class BoaLoader(SourceFileLoader):
    def get_code(self, fullname):
        # importlib docs say to return None, but that triggers an `ImportError`
        return ""

    def create_module(self, spec):
        ret = load_partial(self.path)

        # comply with PEP-302:
        ret.__name__ = spec.name
        ret.__file__ = self.path
        ret.__loader__ = self
        ret.__package__ = spec.name.rpartition(".")[0]
        return ret


sys.meta_path.append(BoaImporter())


def compiler_data(source_code: str, contract_name: str, **kwargs) -> CompilerData:
    def cache_miss():
        # use get_interface_codes to get the interface source dict
        # TODO revisit this once imports are cleaned up vyper-side
        ifaces = get_interface_codes(Path("."), {contract_name: source_code})[
            contract_name
        ]
        result = CompilerData(
            source_code, contract_name, interface_codes=ifaces, **kwargs
        )
        return result

    cache_key = str((kwargs, source_code))
    is_cached = CompileCache.has(cache_key)
    ret = CompileCache.lookup(cache_key, cache_miss)
    if is_cached is True:
        with anchor_compiler_settings(ret):
            _ = ret.bytecode, ret.bytecode_runtime  # force compilation to happen
    return ret


def load(filename: str | Path, *args, **kwargs) -> _Contract:  # type: ignore
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
    filename: str | Path | None = None,
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
