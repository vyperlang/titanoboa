import contextlib
from typing import Any, Iterator, Optional

import eth.constants as constants
import eth.tools.builder.chain as chain
from eth.chains.mainnet import MainnetChain
from eth.db.atomic import AtomicDB
from eth.vm.code_stream import CodeStream
from eth.vm.message import Message
from eth.vm.opcode_values import STOP
from eth.vm.transaction_context import BaseTransactionContext
from eth_typing import Address


class VMPatcher:
    _patchables = {
        # env vars vyper supports
        "block_number": "_block_number",
        "timestamp": "_timestamp",
        "coinbase": "_coinbase",
        "difficulty": "_difficulty",
        "prev_hashes": "_prev_hashes",
        "chain_id": "_chain_id",
    }

    def __init__(self, vm):
        # https://stackoverflow.com/a/12999019
        object.__setattr__(self, "_patch", vm.state.execution_context)

    def __getattr__(self, attr):
        if attr in self._patchables:
            return getattr(self._patch, self._patchables[attr])
        raise AttributeError(attr)

    def __setattr__(self, attr, value):
        if attr in self._patchables:
            setattr(self._patch, self._patchables[attr], value)


# a code stream which keeps a trace of opcodes it has executed
class TracingCodeStream(CodeStream):
    __slots__ = [
        "_length_cache",
        "_fake_codesize",
        "_raw_code_bytes",
        "invalid_positions",
        "valid_positions",
        "program_counter",
    ]

    def __init__(self, *args, start_pc=0, fake_codesize=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._trace = []  # trace of opcodes that were run
        self.program_counter = start_pc  # configurable start PC
        self._fake_codesize = fake_codesize  # what CODESIZE returns

    def __iter__(self) -> Iterator[int]:
        # upstream says: "a very performance-sensitive method"
        # note: not clear to me that len(raw_code_bytes) is a hotspot
        while self.program_counter < self._length_cache:
            opcode = self._raw_code_bytes[self.program_counter]

            self._trace.append(self.program_counter)
            self.program_counter += 1
            yield opcode

        yield STOP

    def __len__(self):
        if self._fake_codesize is not None:
            return self._fake_codesize
        return self._length_cache


class TrivialGasMeter:
    def __init__(self, start_gas):
        self.start_gas = start_gas
        self.gas_remaining = start_gas

    def consume_gas(self, amount, reason):
        pass

    def refund_gas(self, amount):
        pass

    def return_gas(self, amount):
        pass


# wrapper class around py-evm which provides a "contract-centric" API
class Env:
    _singleton = None
    _initial_address_counter = 100

    def __init__(self):
        self.chain = _make_chain()
        self.vm = self.chain.get_vm()
        self.vm.patch = VMPatcher(self.vm)
        self._gas_price = 0

        self._address_counter = self.__class__._initial_address_counter

        # TODO differentiate between origin and sender
        self.eoa = self.generate_address()

        class OpcodeTracingComputation(self.vm.state.computation_class):
            _gas_metering = True

            def __init__(self, *args, **kwargs):
                # super() hardcodes CodeStream into the ctor
                # so we have to override it here
                super().__init__(*args, **kwargs)
                self.code = TracingCodeStream(
                    self.code._raw_code_bytes,
                    fake_codesize=getattr(self.msg, "_fake_codesize", None),
                    start_pc=getattr(self.msg, "_start_pc", 0),
                )
                if not self.__class__._gas_metering:
                    self._gas_meter = TrivialGasMeter(self.msg.gas)

        # TODO make metering toggle-able
        self.vm.state.computation_class = OpcodeTracingComputation

    def set_gas_metering(self, val: bool) -> None:
        self.vm.state.computation_class._gas_metering = val

    # TODO is this a good name
    @contextlib.contextmanager
    def prank(self, address: bytes) -> Iterator[None]:
        tmp = self.eoa
        self.eoa = address
        yield
        self.eoa = tmp

    @classmethod
    def get_singleton(cls):
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def generate_address(self):
        self._address_counter += 1
        return self._address_counter.to_bytes(length=20, byteorder="big")

    def deploy_code(
        self,
        deploy_to: bytes = constants.ZERO_ADDRESS,
        sender: Optional[bytes] = None,
        gas: int = None,
        value: int = 0,
        bytecode: bytes = b"",
        data: bytes = b"",
        start_pc: int = 0,
    ) -> bytes:
        if gas is None:
            gas = self.vm.state.gas_limit
        if sender is None:
            sender = self.eoa

        msg = Message(
            to=Address(deploy_to),
            sender=Address(sender),
            gas=gas,
            value=value,
            code=bytecode,
            data=data,
        )
        tx_ctx = BaseTransactionContext(
            origin=Address(sender), gas_price=self._gas_price
        )
        c = self.vm.state.computation_class.apply_create_message(
            self.vm.state, msg, tx_ctx
        )

        if c.is_error:
            raise c.error
        return c.output

    def execute_code(
        self,
        to_address: bytes = constants.ZERO_ADDRESS,
        sender: bytes = None,
        gas: int = None,
        value: int = 0,
        bytecode: bytes = b"",
        data: bytes = b"",
        start_pc: int = 0,
        fake_codesize: int = None,
    ) -> Any:
        if gas is None:
            gas = self.vm.state.gas_limit
        if sender is None:
            sender = self.eoa

        class FakeMessage(Message):  # Message object with settable attrs
            __dict__: dict = {}

        msg = FakeMessage(
            sender=Address(sender),
            to=Address(to_address),
            gas=gas,
            value=value,
            code=bytecode,
            data=data,
        )
        msg._fake_codesize = fake_codesize  # type: ignore
        msg._start_pc = start_pc  # type: ignore
        tx_ctx = BaseTransactionContext(
            origin=Address(sender), gas_price=self._gas_price
        )
        return self.vm.state.computation_class.apply_message(self.vm.state, msg, tx_ctx)


GENESIS_PARAMS = {"difficulty": constants.GENESIS_DIFFICULTY, "gas_limit": int(1e8)}


# TODO make fork configurable - ex. "latest", "frontier", "berlin"
# TODO make genesis params+state configurable
def _make_chain():
    # TODO should we use MiningChain? is there a perf difference?
    # TODO debug why `fork_at()` cannot accept 0 as block num
    _Chain = chain.build(MainnetChain, chain.latest_mainnet_at(1))
    return _Chain.from_genesis(AtomicDB(), GENESIS_PARAMS)
