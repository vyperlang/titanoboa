from eth.chains.mainnet import MainnetChain
from eth.db.atomic import AtomicDB
import eth.tools.builder.chain as chain
import eth.constants as constants
from eth.vm.message import Message
from eth.vm.transaction_context import BaseTransactionContext

# wrapper class around py-evm which provides a "contract-centric" API
class Env:
    def __init__(self):
        self.chain = _make_chain()
        self.vm = self.chain.get_vm()
        self._sender = constants.ZERO_ADDRESS
        self._gas_price = 0

    def execute_code(self, to_address: bytes = constants.ZERO_ADDRESS, gas: int = None, value: int = 0, bytecode: bytes = b"", data: bytes = b""):
        if gas is None:
            gas = self.vm.state.gas_limit
        msg = Message(sender=self._sender,to=to_address,gas=gas,value=value,code=bytecode,data=data)
        tx_ctx = BaseTransactionContext(origin=self._sender, gas_price=self._gas_price)
        return self.vm.state.computation_class.apply_message(self.vm.state, msg, tx_ctx)

GENESIS_PARAMS = {
    "difficulty": constants.GENESIS_DIFFICULTY,
}

# TODO make fork configurable - ex. "latest", "frontier", "berlin"
# TODO make genesis params+state configurable
def _make_chain():
    # TODO should we use MiningChain? is there a perf difference?
    # TODO debug why `fork_at()` cannot accept 0 as block num
    _Chain = chain.build(MainnetChain, chain.latest_mainnet_at(1))
    return _Chain.from_genesis(AtomicDB(), GENESIS_PARAMS)
