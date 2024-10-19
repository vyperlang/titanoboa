import sys
import textwrap
from importlib.abc import MetaPathFinder
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import vvm
import vyper
from packaging.version import Version
from vyper.ast.parse import parse_to_ast
from vyper.cli.vyper_compile import get_search_paths
from vyper.compiler.input_bundle import (
    ABIInput,
    CompilerInput,
    FileInput,
    FilesystemInputBundle,
)
from vyper.compiler.phases import CompilerData
from vyper.compiler.settings import Settings, anchor_settings
from vyper.semantics.analysis.module import analyze_module
from vyper.semantics.types.module import ModuleT
from vyper.utils import sha256sum

from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.contracts.vvm.vvm_contract import VVMDeployer
from boa.contracts.vyper.vyper_contract import (
    VyperBlueprint,
    VyperContract,
    VyperDeployer,
)
from boa.environment import Env
from boa.explorer import Etherscan, get_etherscan
from boa.rpc import json
from boa.util.abi import Address
# export set_cache_dir, NOTE: consider moving to boa/__init__.py
from boa.util.disk_cache import get_disk_cache, set_cache_dir  # noqa: F401

if TYPE_CHECKING:
    from vyper.semantics.analysis.base import ImportInfo

_Contract = Union[VyperContract, VyperBlueprint]

_search_path = None


def set_search_path(path: list[str]):
    global _search_path
    _search_path = path


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


def hash_input(compiler_input: CompilerInput) -> str:
    if isinstance(compiler_input, FileInput):
        return compiler_input.sha256sum
    if isinstance(compiler_input, ABIInput):
        return sha256sum(str(compiler_input.abi))
    raise RuntimeError(f"bad compiler input {compiler_input}")


# compute a fingerprint for a module which changes if any of its
# dependencies change
# TODO consider putting this in its own module
def get_module_fingerprint(
    module_t: ModuleT, seen: dict["ImportInfo", str] = None
) -> str:
    seen = seen or {}
    fingerprints = []
    for stmt in module_t.import_stmts:
        import_info = stmt._metadata["import_info"]
        if id(import_info) not in seen:
            if isinstance(import_info.typ, ModuleT):
                fingerprint = get_module_fingerprint(import_info.typ, seen)
            else:
                fingerprint = hash_input(import_info.compiler_input)
            seen[id(import_info)] = fingerprint
        fingerprint = seen[id(import_info)]
        fingerprints.append(fingerprint)
    fingerprints.append(module_t._module.source_sha256sum)

    return sha256sum("".join(fingerprints))


def compiler_data(
    source_code: str, contract_name: str, filename: str | Path, deployer=None, **kwargs
) -> CompilerData:
    global _search_path

    path = Path(contract_name)
    resolved_path = Path(filename).resolve(strict=False)

    file_input = FileInput(
        contents=source_code, source_id=-1, path=path, resolved_path=resolved_path
    )

    search_paths = get_search_paths(_search_path)
    input_bundle = FilesystemInputBundle(search_paths)

    settings = Settings(**kwargs)
    ret = CompilerData(file_input, input_bundle, settings)

    disk_cache = get_disk_cache()
    if disk_cache is None:
        return ret

    with anchor_settings(ret.settings):
        # note that this actually parses and analyzes all dependencies,
        # even if they haven't changed. an optimization would be to
        # somehow convince vyper (in ModuleAnalyzer) to get the module_t
        # from the cache.
        module_t = ret.annotated_vyper_module._metadata["type"]
    fingerprint = get_module_fingerprint(module_t)

    def get_compiler_data():
        with anchor_settings(ret.settings):
            # force compilation to happen so DiskCache will cache the compiled artifact:
            _ = ret.bytecode, ret.bytecode_runtime
        return ret

    assert isinstance(deployer, type) or deployer is None
    deployer_id = repr(deployer)  # a unique str identifying the deployer class
    cache_key = str((contract_name, fingerprint, kwargs, deployer_id))
    return disk_cache.caching_lookup(cache_key, get_compiler_data)


def load(filename: str | Path, *args, **kwargs) -> _Contract:  # type: ignore
    name = Path(filename).stem
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
        name = Path(filename).stem
    # TODO: pass filename to ABIContractFactory
    with open(filename) as fp:
        return loads_abi(fp.read(), *args, name=name, **kwargs)


def loads_abi(json_str: str, *args, name: str = None, **kwargs) -> ABIContractFactory:
    return ABIContractFactory.from_abi_dict(json.loads(json_str), name, *args, **kwargs)


# load from .vyi file.
# NOTE: substantially same interface as load_abi and loads_abi, consider
# fusing them into load_interface?
def load_vyi(filename: str, name: str = None) -> ABIContractFactory:
    if name is None:
        name = Path(filename).stem
    with open(filename) as fp:
        return loads_vyi(fp.read(), name=name, filename=filename)


# load interface from .vyi file string contents.
def loads_vyi(source_code: str, name: str = None, filename: str = None):
    global _search_path

    ast = parse_to_ast(source_code)

    if name is None:
        name = "VyperContract.vyi"

    search_paths = get_search_paths(_search_path)
    input_bundle = FilesystemInputBundle(search_paths)

    module_t = analyze_module(ast, input_bundle, is_interface=True)
    abi = module_t.interface.to_toplevel_abi_dict()
    return ABIContractFactory(name, abi, filename=filename)


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

    version = vvm.detect_vyper_version_from_source(source_code)
    if version is not None and version != Version(vyper.__version__):
        return _loads_partial_vvm(source_code, str(version), filename, name)

    compiler_args = compiler_args or {}

    deployer_class = _get_default_deployer_class()
    filename = filename or "<unknown>"
    data = compiler_data(source_code, name, filename, deployer_class, **compiler_args)
    return deployer_class(data, filename=filename)


def load_partial(filename: str, compiler_args=None):
    with open(filename) as f:
        return loads_partial(
            f.read(), name=filename, filename=filename, compiler_args=compiler_args
        )


def _loads_partial_vvm(
    source_code: str,
    version: str,
    filename: Optional[str | Path] = None,
    name: Optional[str] = None,
):
    if filename is not None:
        filename = str(filename)

    # install the requested version if not already installed
    vvm.install_vyper(version=version)

    return VVMDeployer.from_source_code(source_code, version, filename, name)


def from_etherscan(
    address: Any, name: str = None, uri: str = None, api_key: str = None
):
    addr = Address(address)

    if uri is not None or api_key is not None:
        etherscan = Etherscan(uri, api_key)
    else:
        etherscan = get_etherscan()

    abi = etherscan.fetch_abi(addr)
    return ABIContractFactory.from_abi_dict(abi, name=name).at(addr)


def _get_default_deployer_class():
    env = Env.get_singleton()
    if hasattr(env, "deployer_class"):
        return env.deployer_class
    return VyperDeployer


__all__ = []  # type: ignore
