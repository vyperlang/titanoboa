import contextlib
import logging
import sys
from typing import Any, Iterator, Optional, Union

import eth.constants as constants
import eth.tools.builder.chain as chain
import eth.vm.forks.spurious_dragon.computation as spurious_dragon
from eth.chains.mainnet import MainnetChain
from eth.db.atomic import AtomicDB
from eth.vm.code_stream import CodeStream
from eth.vm.message import Message
from eth.vm.opcode_values import STOP
from eth.vm.transaction_context import BaseTransactionContext
from eth_abi import decode_single
from eth_typing import Address
from eth_utils import setup_DEBUG2_logging, to_canonical_address, to_checksum_address


def enable_pyevm_verbose_logging():
    logging.basicConfig()
    logger = logging.getLogger("eth.vm.computation.Computation")
    setup_DEBUG2_logging()
    logger.setLevel("DEBUG2")


class VMPatcher:
    _exc_patchables = {
        # env vars vyper supports
        "block_number": "_block_number",
        "timestamp": "_timestamp",
        "coinbase": "_coinbase",
        "difficulty": "_difficulty",
        "prev_hashes": "_prev_hashes",
        "chain_id": "_chain_id",
    }

    _cmp_patchables = {"code_size_limit": "EIP170_CODE_SIZE_LIMIT"}

    def __init__(self, vm):
        patchables = [
            (self._exc_patchables, vm.state.execution_context),
            (self._cmp_patchables, spurious_dragon),
        ]
        # https://stackoverflow.com/a/12999019
        object.__setattr__(self, "_patchables", patchables)

    def __getattr__(self, attr):
        for s, p in self._patchables:
            if attr in s:
                return getattr(p, s[attr])
        raise AttributeError(attr)

    def __setattr__(self, attr, value):
        for s, p in self._patchables:
            if attr in s:
                setattr(p, s[attr], value)
                return

    # to help auto-complete
    def __dir__(self):
        patchable_keys = [k for p, _ in self._patchables for k in p]
        return dir(super()) + patchable_keys

    # save and restore patch values
    @contextlib.contextmanager
    def anchor(self):
        snap = {}
        for s, _ in self._patchables:
            for attr in s:
                snap[attr] = getattr(self, attr)

        try:
            yield

        finally:
            for s, _ in self._patchables:
                for attr in s:
                    setattr(self, attr, snap[attr])


def console_log(computation):
    msgdata = computation.msg.data_as_bytes
    schema, payload = decode_single("(string,bytes)", msgdata[4:])
    data = decode_single(schema, payload)
    print(*data, file=sys.stderr)
    return computation


CONSOLE_ADDRESS = bytes.fromhex("000000000000000000636F6E736F6C652E6C6F67")


AddressT = Union[Address, bytes, str]  # make mypy happy


def _addr(addr: AddressT) -> Address:
    return Address(to_canonical_address(addr))


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


# ### section: sha3 preimage tracing
# (TODO: move to dedicated module)
def to_int(value):
    if isinstance(value, tuple):
        return to_int(value[1])  # how py-evm stores stuff on stack
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int.from_bytes(value, "big")

    raise ValueError("invalid type %s", type(value))


def to_bytes(value):
    if isinstance(value, tuple):
        return to_bytes(value[1])  # how py-evm stores stuff on stack
    if isinstance(value, bytes):
        return value
    if isinstance(value, int):
        return value.to_bytes(32, "big")

    raise ValueError("invalid type %s", type(value))


class Sha3PreimageTracer:
    mnemonic = "SHA3"

    # trace preimages of sha3

    def __init__(self, sha3_op, preimage_map):
        self.preimages = preimage_map
        self.sha3 = sha3_op

    def __call__(self, computation):
        size, offset = [to_int(x) for x in computation._stack.values[-2:]]

        # dispatch into py-evm
        self.sha3(computation)

        if size != 64:
            return

        preimage = computation._memory.read_bytes(offset, size)

        image = to_bytes(computation._stack.values[-1])

        self.preimages[image] = preimage


class SstoreTracer:
    mnemonic = "SSTORE"

    def __init__(self, sstore_op, trace_db):
        self.trace_db = trace_db
        self.sstore = sstore_op

    def __call__(self, computation):
        value, slot = [to_bytes(t) for t in computation._stack.values[-2:]]
        account = to_checksum_address(computation.msg.to)

        self.trace_db.setdefault(account, set())
        # we don't want to deal with snapshots/commits/reverts, so just
        # register that the slot was touched and downstream can filter
        # zero entries.
        self.trace_db[account].add(slot)

        # dispatch into py-evm
        self.sstore(computation)


# ### End section: sha3 tracing


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
        self._gas_price = 0

        self._address_counter = self.__class__._initial_address_counter

        self._aliases = {}

        # TODO differentiate between origin and sender
        self.eoa = self.generate_address("root")

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

                self._precompiles[CONSOLE_ADDRESS] = console_log

        # TODO make metering toggle-able
        c = OpcodeTracingComputation

        self.vm.state.computation_class = c

        # patch in tracing opcodes
        self.sha3_trace = {}
        self.sstore_trace = {}
        c.opcodes[0x20] = Sha3PreimageTracer(c.opcodes[0x20], self.sha3_trace)
        c.opcodes[0x55] = SstoreTracer(c.opcodes[0x55], self.sstore_trace)

        self.vm.patch = VMPatcher(self.vm)

        self._contracts = {}

    def set_gas_metering(self, val: bool) -> None:
        self.vm.state.computation_class._gas_metering = val

    def register_contract(self, address, obj):
        self._contracts[to_checksum_address(address)] = obj

    def lookup_contract(self, address):
        return self._contracts.get(to_checksum_address(address))

    def alias(self, address, name):
        self._aliases[to_checksum_address(address)] = name

    def lookup_alias(self, address):
        return self._aliases[to_checksum_address(address)]

    # context manager which snapshots the state and reverts
    # to the snapshot on exiting the with statement
    @contextlib.contextmanager
    def anchor(self):
        snapshot_id = self.vm.state.snapshot()
        try:
            with self.vm.patch.anchor():
                yield
        finally:
            self.vm.state.revert(snapshot_id)

    # TODO is this a good name
    @contextlib.contextmanager
    def prank(self, address):
        tmp = self.eoa
        self.eoa = to_checksum_address(address)
        try:
            yield
        finally:
            self.eoa = tmp

    @classmethod
    def get_singleton(cls):
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def generate_address(self, alias: Optional[str] = None) -> AddressT:
        self._address_counter += 1
        t = self._address_counter.to_bytes(length=20, byteorder="big")
        # checksum addr easier for humans to debug
        ret = to_checksum_address(t)
        if alias is not None:
            self.alias(ret, alias)

        return ret


    def deploy_code(
        self,
        deploy_to: AddressT = constants.ZERO_ADDRESS,
        sender: Optional[AddressT] = None,
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
            to=_addr(deploy_to),
            sender=_addr(sender),
            gas=gas,
            value=value,
            code=bytecode,
            data=data,
        )
        tx_ctx = BaseTransactionContext(origin=_addr(sender), gas_price=self._gas_price)
        c = self.vm.state.computation_class.apply_create_message(
            self.vm.state, msg, tx_ctx
        )

        if c.is_error:
            raise c.error
        return c.output

    def execute_code(
        self,
        to_address: AddressT = constants.ZERO_ADDRESS,
        sender: AddressT = None,
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
            sender=_addr(sender),
            to=_addr(to_address),
            gas=gas,
            value=value,
            code=bytecode,
            data=data,
        )
        msg._fake_codesize = fake_codesize  # type: ignore
        msg._start_pc = start_pc  # type: ignore
        tx_ctx = BaseTransactionContext(origin=_addr(sender), gas_price=self._gas_price)
        return self.vm.state.computation_class.apply_message(self.vm.state, msg, tx_ctx)


GENESIS_PARAMS = {"difficulty": constants.GENESIS_DIFFICULTY, "gas_limit": int(1e8)}


# TODO make fork configurable - ex. "latest", "frontier", "berlin"
# TODO make genesis params+state configurable
def _make_chain():
    # TODO should we use MiningChain? is there a perf difference?
    # TODO debug why `fork_at()` cannot accept 0 as block num
    _Chain = chain.build(MainnetChain, chain.latest_mainnet_at(1))
    return _Chain.from_genesis(AtomicDB(), GENESIS_PARAMS)
