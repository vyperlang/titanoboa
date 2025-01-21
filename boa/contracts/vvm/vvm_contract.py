from dataclasses import dataclass
from functools import cached_property

import vyper.utils

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.contracts.base_evm_contract import StackTrace
from boa.environment import Env
from boa.util.abi import Address
from boa.util.eip5202 import generate_blueprint_bytecode


class VVMContract(ABIContract):
    def __init__(
        self,
        name: str,
        abi: list[dict],
        functions: list[ABIFunction],
        events: list[dict],
        address: Address,
        deployer: "VVMDeployer",
        **kwargs,
    ):
        self._deployer = deployer
        super().__init__(name, abi, functions, events, address, **kwargs)

    @property
    def deployer(self) -> "VVMDeployer":
        # override deployer getter in ABIContract
        return self._deployer

    @cached_property
    def source_code(self) -> str:
        return self.deployer.source_code  # .split("\n")

    @cached_property
    def source_map(self) -> dict:
        return self.deployer.source_map

    def stack_trace(self, computation):
        code_stream = computation.code

        error_map = self.source_map["pc_pos_map"]

        error = None
        for pc in reversed(code_stream._trace):
            pc = str(pc)
            if pc in error_map:
                error = error_map[pc]
                break

        # we only report the line for simplicity, could be more precise
        lineno, *_ = error

        annotated_error = vyper.utils.annotate_source_code(
            self.source_code, lineno, context_lines=3, line_numbers=True
        )

        return StackTrace([VVMErrorDetail(annotated_error)])


@dataclass
class VVMErrorDetail:
    # this class is useful to detect that the error comes
    # from a VVM contract in BoaError. Also useful if
    # source_map based reporting is improved in the future
    # (similarly to ErrorDetail).
    annotated_source: str

    def __str__(self):
        return self.annotated_source


class VVMDeployer(ABIContractFactory):
    """
    A deployer that uses the Vyper Version Manager (VVM).
    This allows deployment of contracts written in older versions of Vyper that
    can interact with new versions using the ABI definition.
    """

    def __init__(self, abi, bytecode, name, filename, source_code, source_map):
        """
        Initialize a VVMDeployer instance.
        :param abi: The contract's ABI.
        :param bytecode: The contract's bytecode.
        :param filename: The filename of the contract.
        """
        self.bytecode: bytes = bytecode
        self.source_map: dict = source_map
        self.source_code = source_code
        super().__init__(name, abi, filename=filename)

    @classmethod
    def from_compiler_output(cls, compiler_output, name, filename, source_code):
        abi = compiler_output["abi"]
        bytecode_nibbles = compiler_output["bytecode"]
        bytecode = bytes.fromhex(bytecode_nibbles.removeprefix("0x"))
        source_map = compiler_output["source_map"]
        return cls(abi, bytecode, name, filename, source_code, source_map)

    @cached_property
    def constructor(self):
        for t in self.abi:
            if t["type"] == "constructor":
                return ABIFunction(t, contract_name=self.filename)
        return None

    def deploy(self, *args, contract_name=None, env=None, **kwargs):
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

        if computation.is_error:
            ret.handle_error(computation)

        return ret

    @cached_property
    def _blueprint_deployer(self):
        # TODO: this can definitely be removed with some refactoring
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
        address, computation = env.deploy(bytecode=blueprint_bytecode, **kwargs)

        ret = self._blueprint_deployer.at(address)

        if computation.is_error:
            ret.handle_error(computation)

        env.register_blueprint(self.bytecode, ret)
        return ret

    def __call__(self, *args, **kwargs):
        return self.deploy(*args, **kwargs)

    def at(self, address: Address | str, nowarn=False) -> VVMContract:
        """
        Create an VVMContract object for a deployed contract at `address`.
        """
        address = Address(address)
        contract = VVMContract(
            self._name,
            self.abi,
            self.functions,
            self.events,
            address,
            self,
            nowarn=nowarn,
        )

        contract.env.register_contract(address, contract)
        return contract
