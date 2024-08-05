import re
from functools import cached_property

from boa.contracts.abi.abi_contract import ABIContractFactory, ABIFunction
from boa.environment import Env

# TODO: maybe this doesn't detect release candidates
VERSION_RE = re.compile(r"\s*#\s*(pragma\s+version|@version)\s+(\d+\.\d+\.\d+)")


# TODO: maybe move this up to vvm?
def _detect_version(source_code: str):
    res = VERSION_RE.findall(source_code)
    if len(res) < 1:
        return None
    # TODO: handle len(res) > 1
    return res[0][1]


class VVMDeployer:
    def __init__(self, abi, bytecode, filename):
        self.abi = abi
        self.bytecode = bytecode
        self.filename = filename

    @classmethod
    def from_compiler_output(cls, compiler_output, filename):
        abi = compiler_output["abi"]
        bytecode_nibbles = compiler_output["bytecode"]
        bytecode = bytes.fromhex(bytecode_nibbles.removeprefix("0x"))
        return cls(abi, bytecode, filename)

    @cached_property
    def factory(self):
        return ABIContractFactory.from_abi_dict(self.abi)

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

    def at(self, address):
        return self.factory.at(address)
