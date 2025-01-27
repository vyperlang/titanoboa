from functools import cached_property
from typing import Optional

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.environment import Env
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

    def __init__(self, abi, bytecode, name, filename):
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

    @classmethod
    def from_compiler_output(cls, compiler_output, name, filename):
        abi = compiler_output["abi"]
        bytecode_nibbles = compiler_output["bytecode"]
        bytecode = bytes.fromhex(bytecode_nibbles.removeprefix("0x"))
        return cls(abi, bytecode, name, filename)

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
        return self.factory.at(address, nowarn=nowarn)
