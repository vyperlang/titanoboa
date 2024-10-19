import re
from functools import cached_property
from pathlib import Path
from typing import Any, Optional

import vvm
from vyper.utils import method_id

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.environment import Env
from boa.rpc import to_bytes
from boa.util.abi import Address
from boa.util.disk_cache import get_disk_cache
from boa.util.eip5202 import generate_blueprint_bytecode


def _compile_source(*args, **kwargs) -> Any:
    """
    Compile Vyper source code via the VVM.
    When a disk cache is available, the result of the compilation is cached.
    """
    disk_cache = get_disk_cache()

    def _compile():
        return vvm.compile_source(*args, **kwargs)

    if disk_cache is None:
        return _compile()

    cache_key = f"{args}{kwargs}"
    return disk_cache.caching_lookup(cache_key, _compile)


class VVMDeployer(ABIContractFactory):
    """
    A deployer that uses the Vyper Version Manager (VVM).
    This allows deployment of contracts written in older versions of Vyper that
    can interact with new versions using the ABI definition.
    """

    def __init__(
        self,
        name: str,
        compiler_output: dict,
        source_code: str,
        vyper_version: str,
        filename: Optional[str] = None,
    ):
        """
        Initialize a VVMDeployer instance.
        :param name: The name of the contract.
        :param compiler_output: The compiler output of the contract.
        :param source_code: The source code of the contract.
        :param vyper_version: The Vyper version used to compile the contract.
        :param filename: The filename of the contract.
        """
        super().__init__(name, compiler_output["abi"], filename)
        self.compiler_output = compiler_output
        self.source_code = source_code
        self.vyper_version = vyper_version

    @cached_property
    def bytecode(self):
        return to_bytes(self.compiler_output["bytecode"])

    @classmethod
    def from_source_code(
        cls,
        source_code: str,
        vyper_version: str,
        filename: Optional[str] = None,
        name: Optional[str] = None,
    ):
        if name is None:
            name = Path(filename).stem if filename is not None else "<VVMContract>"
        compiled_src = _compile_source(source_code, vyper_version=vyper_version)
        compiler_output = compiled_src["<stdin>"]

        return cls(name, compiler_output, source_code, vyper_version, filename)

    @cached_property
    def constructor(self):
        for t in self.abi:
            if t["type"] == "constructor":
                return ABIFunction(t, contract_name=self.filename)
        return None

    def deploy(self, *args, env=None, **kwargs):
        encoded_args = b""
        if self.constructor is not None:
            encoded_args = self.constructor.prepare_calldata(*args)
        elif len(args) > 0:
            raise ValueError(f"No constructor, but args were provided: {args}")

        if env is None:
            env = Env.get_singleton()

        address, _ = env.deploy_code(bytecode=self.bytecode + encoded_args, **kwargs)

        return self.at(address)

    @cached_property
    def _blueprint_deployer(self):
        # TODO: add filename
        return ABIContractFactory.from_abi_dict([])

    def deploy_as_blueprint(self, env=None, blueprint_preamble=None, **kwargs):
        """
        Deploy a new blueprint from this contract.
        :param blueprint_preamble: The preamble to use for the blueprint.
        :param env: The environment to deploy the blueprint in.
        :param kwargs: Keyword arguments to pass to the environment `deploy_code` method.
        :returns: A contract instance.
        """
        if env is None:
            env = Env.get_singleton()

        blueprint_bytecode = generate_blueprint_bytecode(
            self.bytecode, blueprint_preamble
        )
        address, _ = env.deploy_code(bytecode=blueprint_bytecode, **kwargs)

        ret = self._blueprint_deployer.at(address)

        env.register_blueprint(self.bytecode, ret)
        return ret

    def __call__(self, *args, **kwargs):
        return self.deploy(*args, **kwargs)

    def at(self, address: Address | str) -> "VVMContract":
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)
        contract = VVMContract(
            compiler_output=self.compiler_output,
            source_code=self.source_code,
            vyper_version=self.vyper_version,
            name=self._name,
            abi=self._abi,
            functions=self.functions,
            address=address,
            filename=self.filename,
        )
        contract.env.register_contract(address, contract)
        return contract


class VVMContract(ABIContract):
    """
    A deployed contract compiled with vvm, which is called via ABI.
    """

    def __init__(self, compiler_output, source_code, vyper_version, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compiler_output = compiler_output
        self.source_code = source_code
        self.vyper_version = vyper_version

    @cached_property
    def bytecode(self):
        return to_bytes(self.compiler_output["bytecode"])

    @cached_property
    def bytecode_runtime(self):
        return to_bytes(self.compiler_output["bytecode_runtime"])

    def inject_function(self, fn_source_code, force=False):
        """
        Inject a function into this VVM Contract without affecting the
        contract's source code. useful for testing private functionality.
        :param fn_source_code: The source code of the function to inject.
        :param force: If True, the function will be injected even if it already exists.
        :returns: The result of the statement evaluation.
        """
        fn = VVMInjectedFunction(fn_source_code, self)
        if hasattr(self, fn.name) and not force:
            raise ValueError(f"Function {fn.name} already exists on contract.")
        setattr(self, fn.name, fn)
        fn.contract = self

    @cached_property
    def _storage(self):
        """
        Allows access to the storage variables of the contract.
        Note that this is quite slow, as it requires the complete contract to be
        recompiled.
        """

        def storage():
            return None

        for name, spec in self.compiler_output["layout"]["storage_layout"].items():
            setattr(storage, name, VVMStorageVariable(name, spec, self))
        return storage

    @cached_property
    def internal(self):
        """
        Allows access to internal functions of the contract.
        Note that this is quite slow, as it requires the complete contract to be
        recompiled.
        """

        # an object with working setattr
        def _obj():
            return None

        result = _compile_source(
            self.source_code, vyper_version=self.vyper_version, output_format="metadata"
        )["function_info"]
        for fn_name, meta in result.items():
            if meta["visibility"] == "internal":
                function = VVMInternalFunction(meta, self)
                setattr(_obj, function.name, function)
        return _obj


class _VVMInternal(ABIFunction):
    """
    An ABI function that temporarily changes the bytecode at the contract's address.
    Subclasses of this class are used to inject code into the contract via the
    `source_code` property using the vvm, temporarily changing the bytecode
    at the contract's address.
    """

    @cached_property
    def _override_bytecode(self) -> bytes:
        return to_bytes(self._compiler_output["bytecode_runtime"])

    @cached_property
    def _compiler_output(self):
        assert isinstance(self.contract, VVMContract)  # help mypy
        source = "\n".join((self.contract.source_code, self.source_code))
        compiled = _compile_source(source, vyper_version=self.contract.vyper_version)
        return compiled["<stdin>"]

    @property
    def source_code(self) -> str:
        """
        Returns the source code an internal function.
        Must be implemented in subclasses.
        """
        raise NotImplementedError


class VVMInternalFunction(_VVMInternal):
    """
    An internal function that is made available via the `internal` namespace.
    It will temporarily change the bytecode at the contract's address.
    """

    def __init__(self, meta: dict, contract: VVMContract):
        abi = {
            "anonymous": False,
            "inputs": [
                {"name": arg_name, "type": arg_type}
                for arg_name, arg_type in meta["positional_args"].items()
            ],
            "outputs": (
                [{"name": meta["name"], "type": meta["return_type"]}]
                if meta["return_type"] != "None"
                else []
            ),
            "stateMutability": meta["mutability"],
            "name": meta["name"],
            "type": "function",
        }
        super().__init__(abi, contract.contract_name)
        self.contract = contract

    @cached_property
    def method_id(self) -> bytes:
        return method_id(f"__boa_internal_{self.name}__" + self.signature)

    @cached_property
    def source_code(self):
        fn_args = ", ".join([arg["name"] for arg in self._abi["inputs"]])

        return_sig = ""
        fn_call = ""
        if self.return_type:
            return_sig = f" -> {self.return_type}"
            fn_call = "return "

        fn_call += f"self.{self.name}({fn_args})"
        fn_sig = ", ".join(
            f"{arg['name']}: {arg['type']}" for arg in self._abi["inputs"]
        )
        return f"""
@external
@payable
def __boa_internal_{self.name}__({fn_sig}){return_sig}:
    {fn_call}
"""


class VVMStorageVariable(_VVMInternal):
    """
    A storage variable that is made available via the `storage` namespace.
    It will temporarily change the bytecode at the contract's address.
    """

    def __init__(self, name, spec, contract):
        inputs, output_type = _get_storage_variable_types(spec)
        abi = {
            "anonymous": False,
            "inputs": inputs,
            "outputs": [{"name": name, "type": output_type}],
            "name": name,
            "type": "function",
        }
        super().__init__(abi, contract.contract_name)
        self.contract = contract

    def get(self, *args):
        # get the value of the storage variable. note that this is
        # different from the behavior of VyperContract storage variables!
        return self.__call__(*args)

    @cached_property
    def method_id(self) -> bytes:
        return method_id(f"__boa_private_{self.name}__" + self.signature)

    @cached_property
    def source_code(self):
        getter_call = "".join(f"[{i['name']}]" for i in self._abi["inputs"])
        args_signature = ", ".join(
            f"{i['name']}: {i['type']}" for i in self._abi["inputs"]
        )
        return f"""
@external
@payable
def __boa_private_{self.name}__({args_signature}) -> {self.return_type[0]}:
    return self.{self.name}{getter_call}
"""


class VVMInjectedFunction(_VVMInternal):
    """
    A Vyper function that is injected into a VVM contract.
    It will temporarily change the bytecode at the contract's address.
    """

    def __init__(self, source_code: str, contract: VVMContract):
        self.contract = contract
        self._source_code = source_code
        abi = [i for i in self._compiler_output["abi"] if i not in contract.abi]
        if len(abi) != 1:
            err = "Expected exactly one new ABI entry after injecting function. "
            err += f"Found {abi}."
            raise ValueError(err)

        super().__init__(abi[0], contract.contract_name)

    @cached_property
    def source_code(self):
        return self.code


def _get_storage_variable_types(spec: dict) -> tuple[list[dict], str]:
    """
    Get the types of a storage variable
    :param spec: The storage variable specification.
    :return: The types of the storage variable:
    1. A list of dictionaries containing the input types.
    2. The output type name.
    """
    hashmap_regex = re.compile(r"^HashMap\[([^[]+), (.+)]$")
    output_type = spec["type"]
    inputs: list[dict] = []
    while output_type.startswith("HashMap"):
        key_type, output_type = hashmap_regex.match(output_type).groups()  # type: ignore
        inputs.append({"name": f"key{len(inputs)}", "type": key_type})
    return inputs, output_type
