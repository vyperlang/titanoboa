import json
import textwrap
from pathlib import Path
from typing import Any, Union

import vyper
from vyper.cli.vyper_compile import get_search_paths
from vyper.compiler.input_bundle import FileInput, FilesystemInputBundle
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
_search_path = None


def set_cache_dir(cache_dir="~/.cache/titanoboa"):
    global _disk_cache
    if cache_dir is None:
        _disk_cache = None
        return
    compiler_version = f"{vyper.__version__}.{vyper.__commit__}"
    _disk_cache = DiskCache(cache_dir, compiler_version)


def set_search_path(path: list[str]):
    global _search_path
    _search_path = path


def compiler_data(
    source_code: str, contract_name: str, filename: str, **kwargs
) -> CompilerData:
    global _disk_cache, _search_path

    # TODO: figure out how caching works with modules.
    if True:
        file_input = FileInput(
            source_code=source_code,
            source_id=-1,
            path=Path(contract_name),
            resolved_path=Path(contract_name),
        )
        search_paths = get_search_paths(_search_path)
        input_bundle = FilesystemInputBundle(search_paths)
        return CompilerData(file_input, input_bundle, **kwargs)

    def func():
        raise Exception("unreachable")
        ret = CompilerData(source_code, contract_name, **kwargs)
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

    data = compiler_data(source_code, name, filename, **compiler_args)
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
