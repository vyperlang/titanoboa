import json
import re
from functools import cached_property
from pathlib import Path
from tempfile import NamedTemporaryFile

import vvm
from vvm.install import get_executable
from vvm.wrapper import vyper_wrapper
from vyper.utils import method_id

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.environment import Env
from boa.rpc import to_bytes
from boa.util.abi import Address

# TODO: maybe this doesn't detect release candidates
VERSION_RE = re.compile(r"\s*#\s*(pragma\s+version|@version)\s+(\d+\.\d+\.\d+)")


# TODO: maybe move this up to VVM?
def _detect_version(source_code: str):
    res = VERSION_RE.findall(source_code)
    if len(res) < 1:
        return None
    # TODO: handle len(res) > 1
    return res[0][1]


class VVMDeployer(ABIContractFactory):
    def __init__(
        self,
        name: str,
        compiler_output: dict,
        source_code: str,
        vyper_version: str,
        filename: str | Path | None = None,
    ):
        super().__init__(name, compiler_output["abi"], filename)
        self.compiler_output = compiler_output
        self.source_code = source_code
        self.vyper_version = vyper_version

    @cached_property
    def bytecode(self):
        return to_bytes(self.compiler_output["bytecode"])

    @property
    def layout(self):
        return self.compiler_output["layout"]

    @classmethod
    def from_compiler_output(
        cls,
        compiler_output: dict,
        source_code: str,
        vyper_version: str,
        filename: str | Path | None = None,
        name: str | None = None,
    ):
        if name is None:
            name = Path(filename).stem if filename is not None else "<VVMContract>"
        return cls(name, compiler_output, source_code, vyper_version, filename)

    @cached_property
    def constructor(self):
        for t in self.abi:
            if t["type"] == "constructor":
                return ABIFunction(t, contract_name=self.filename)
        return None

    def deploy(self, *args, env=None):
        encoded_args = b""
        if self.constructor is not None:
            encoded_args = self.constructor.prepare_calldata(*args)
        elif len(args) > 0:
            raise ValueError(f"No constructor, but args were provided: {args}")

        if env is None:
            env = Env.get_singleton()

        address, _ = env.deploy_code(bytecode=self.bytecode + encoded_args)

        return self.at(address)

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

    def eval(self, code, return_type=None):
        return VVMEval(code, self, return_type)()

    @cached_property
    def _storage(self):
        def storage():
            return None

        for name, spec in self.compiler_output["layout"]["storage_layout"].items():
            setattr(storage, name, VVMStorageVariable(name, spec, self))
        return storage

    @cached_property
    def internal(self):
        def internal():
            return None

        result = self._compile_metadata_fn_info()
        for fn_name, meta in result.items():
            if meta["visibility"] == "internal":
                function = VVMInternalFunction(meta, self)
                setattr(internal, function.name, function)
        return internal

    def _compile_metadata_fn_info(self):
        # todo: move this to vvm
        if self.filename is not None:
            return self._call_vyper(self.filename)
        with NamedTemporaryFile(suffix=".vy") as f:
            f.write(self.source_code.encode())
            f.flush()
            return self._call_vyper(f.name)

    def _call_vyper(self, filename):
        stdoutdata, stderrdata, command, proc = vyper_wrapper(
            vyper_binary=get_executable(self.vyper_version),
            f="metadata",
            source_files=[filename],
        )
        return json.loads(stdoutdata)["function_info"]


class _VVMInternal(ABIFunction):
    """
    An ABI function that temporarily changes the bytecode at the contract's address.
    """

    @cached_property
    def _override_bytecode(self) -> bytes:
        assert isinstance(self.contract, VVMContract)
        source = "\n".join((self.contract.source_code, self.source_code))
        compiled = vvm.compile_source(source, vyper_version=self.contract.vyper_version)
        return to_bytes(compiled["<stdin>"]["bytecode_runtime"])

    @property
    def source_code(self):
        raise NotImplementedError  # to be implemented in subclasses

    def __call__(self, *args, **kwargs):
        env = self.contract.env
        assert isinstance(self.contract, VVMContract)
        balance_before = env.get_balance(env.eoa)
        env.set_code(self.contract.address, self._override_bytecode)
        env.set_balance(env.eoa, 10**20)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            env.set_balance(env.eoa, balance_before)
            env.set_code(self.contract.address, self.contract.bytecode_runtime)


class VVMInternalFunction(_VVMInternal):
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
    def __init__(self, name, spec, contract):
        abi = {
            "anonymous": False,
            "inputs": [],
            "outputs": [{"name": name, "type": spec["type"]}],
            "name": name,
            "type": "function",
        }

        if spec["type"].startswith("HashMap"):
            key_type, value_type = spec["type"][8:-1].split(",")
            abi["inputs"] = [{"name": "key", "type": key_type}]
            abi["outputs"] = [{"name": "value", "type": value_type.strip()}]

        super().__init__(abi, contract.contract_name)
        self.contract = contract

    def get(self, *args):
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


class VVMEval(_VVMInternal):
    def __init__(self, code: str, contract: VVMContract, return_type: str = None):
        abi = {
            "anonymous": False,
            "inputs": [],
            "outputs": ([{"name": "eval", "type": return_type}] if return_type else []),
            "name": "__boa_debug__",
            "type": "function",
        }
        super().__init__(abi, contract.contract_name)
        self.contract = contract
        self.code = code

    @cached_property
    def source_code(self):
        debug_body = self.code
        return_sig = ""
        if self.return_type:
            return_sig = f"-> ({', '.join(self.return_type)})"
            debug_body = f"return {self.code}"
        return f"""
@external
@payable
def __boa_debug__() {return_sig}:
    {debug_body}
"""
