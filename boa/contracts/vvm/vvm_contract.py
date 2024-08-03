from eth_abi import abi

from boa import Env
from boa.contracts.abi.abi_contract import ABIContractFactory


class VVMDeployer:
    def __init__(self, abi, bytecode, filename=None, env: Env = None):
        self.env = env or Env.get_singleton()
        self.abi = abi

        # extract constructor types from ABI
        self.types = next(
            iter(
                [
                    [x["type"] for x in entry["inputs"]]
                    for entry in abi
                    if entry["type"] == "constructor"
                ]
            ),
            [],
        )

        self.bytecode = bytecode
        self.filename = filename
        self.factory = ABIContractFactory.from_abi_dict(abi)

    def deploy(self, *args):
        if len(args) != len(self.types):
            raise ValueError(f"Expected {len(self.types)} arguments, got {len(args)}")

        encoded_args = abi.encode(self.types, args)
        address, _ = self.env.deploy_code(bytecode=self.bytecode + encoded_args)

        return self.factory.at(address)

    def __call__(self, *args):
        return self.deploy(*args)

    def at(self, address):
        return self.factory.at(address)
