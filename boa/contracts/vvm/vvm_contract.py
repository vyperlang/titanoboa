from functools import cached_property
from typing import Optional

import vvm

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.environment import Env
from boa.rpc import to_bytes
from boa.util.abi import Address
from boa.util.eip5202 import generate_blueprint_bytecode


class VVMBlueprint(ABIContract):
    def __init__(self, deployer: "VVMDeployer", address: Address):
        name = deployer.name or "<unknown>"  # help mypy
        super().__init__(
            name,
            abi=[],
            address=address,
            filename=deployer.filename,
            functions=[],
            events=[],
        )
        self._deployer = deployer

    @property
    def deployer(self):
        return self._deployer


class VVMDeployer:
    """
    A deployer that uses the Vyper Version Manager (VVM).
    This allows deployment of contracts written in older versions of Vyper that
    can interact with new versions using the ABI definition.
    """

    def __init__(
        self, abi, bytecode, name, filename, compiler_output, source_code, vyper_version
    ):
        """
        Initialize a VVMDeployer instance.
        :param abi: The contract's ABI.
        :param bytecode: The contract's bytecode.
        :param filename: The filename of the contract.
        """
        self.abi: dict = abi
        self.bytecode: bytes = bytecode
        self.name: Optional[str] = name
        self.filename: str = filename
        self.compiler_output = compiler_output
        self.source_code = source_code
        self.vyper_version = vyper_version

    @classmethod
    def from_compiler_output(
        cls, compiler_output, name, filename, source_code, vyper_version
    ):
        abi = compiler_output["abi"]
        bytecode_nibbles = compiler_output["bytecode"]
        bytecode = bytes.fromhex(bytecode_nibbles.removeprefix("0x"))
        return cls(
            abi, bytecode, name, filename, compiler_output, source_code, vyper_version
        )

    @cached_property
    def factory(self):
        return ABIContractFactory.from_abi_dict(
            self.abi, name=self.name, filename=self.filename
        )

    @cached_property
    def constructor(self):
        for t in self.abi:
            if t["type"] == "constructor":
                return ABIFunction(t, contract_name=self.filename)
        return None

    def deploy(self, *args, **kwargs):
        # Accept optional kwargs without forcing keyword-only usage
        contract_name = kwargs.pop("contract_name", None)
        env = kwargs.pop("env", None)
        encoded_args = b""
        if self.constructor is not None:
            encoded_args = self.constructor.prepare_calldata(*args)
        elif len(args) > 0:
            raise ValueError(f"No constructor, but args were provided: {args}")

        if env is None:
            env = Env.get_singleton()

        address, computation = env.deploy(
            bytecode=self.bytecode + encoded_args, **kwargs
        )

        # set nowarn=True. if there was a problem in the deploy, it will
        # be caught at computation.is_error, so the warning is redundant
        # (and annoying!)
        ret = self.at(address, nowarn=True)
        if contract_name is not None:
            # override contract name
            ret.contract_name = contract_name
        ret._computation = computation

        if computation.is_error:
            ret.handle_error(computation)

        return ret

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
        address, computation = env.deploy(bytecode=blueprint_bytecode, **kwargs)

        ret = VVMBlueprint(self, address)

        if computation.is_error:
            ret.handle_error(computation)

        env.register_blueprint(self.bytecode, ret)
        return ret

    def __call__(self, *args, **kwargs):
        return self.deploy(*args, **kwargs)

    def at(self, address, nowarn=False):
        # Build a VVMContract directly so advanced features (e.g. injection)
        # have access to compiler/source context
        addr = Address(address)
        # Construct function and event descriptors from ABI
        contract_name = self.name or "<unknown>"
        functions = [
            ABIFunction(item, contract_name)
            for item in self.abi
            if item.get("type") == "function"
        ]
        events = [item for item in self.abi if item.get("type") == "event"]

        contract = VVMContract(
            self.compiler_output,
            self.source_code,
            self.vyper_version,
            name=contract_name,
            abi=self.abi,
            functions=functions,
            events=events,
            address=addr,
            filename=self.filename,
            nowarn=nowarn,
        )

        contract.env.register_contract(addr, contract)
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


class VVMInjectedFunction(ABIFunction):
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
    def _override_bytecode(self) -> bytes:
        return to_bytes(self._compiler_output["bytecode_runtime"])

    @cached_property
    def _compiler_output(self):
        assert isinstance(self.contract, VVMContract)  # help mypy
        source = "\n".join((self.contract.source_code, self.source_code))
        compiled = vvm.compile_source(source, vyper_version=self.contract.vyper_version)
        return compiled["<stdin>"]

    @cached_property
    def source_code(self):
        return self._source_code
