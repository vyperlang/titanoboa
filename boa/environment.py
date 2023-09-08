# the main "entry point" for patching py-evm.
# handles low level details around state and py-evm tracing.

import contextlib
import logging
import sys
import warnings
from typing import Any, Iterator, Optional, Union

import eth.constants as constants
import eth.tools.builder.chain as chain
import eth.vm.forks.spurious_dragon.computation as spurious_dragon
from eth._utils.address import generate_contract_address
from eth.chains.mainnet import MainnetChain
from eth.codecs import abi
from eth.db.atomic import AtomicDB
from eth.vm.code_stream import CodeStream
from eth.vm.message import Message
from eth.vm.opcode_values import STOP
from eth.vm.transaction_context import BaseTransactionContext
from eth_typing import Address
from eth_utils import setup_DEBUG2_logging, to_canonical_address, to_checksum_address

from boa.util.eip1167 import extract_eip1167_address, is_eip1167_contract
from boa.vm.fork import AccountDBFork
from boa.vm.gas_meters import GasMeter, NoGasMeter, ProfilingGasMeter


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
        "gas_limit": "_gas_limit",
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


AddressType = Union[Address, bytes, str]  # make mypy happy


def _addr(addr: AddressType) -> Address:
    return Address(to_canonical_address(addr))


_opcode_overrides = {}


def patch_opcode(opcode_value, fn):
    global _opcode_overrides
    _opcode_overrides[opcode_value] = fn


# _precompiles is a global which is loaded to the env computation
# every time one is created. the reasoning is that it would seem
# confusing to have registered precompiles not persist across envs -
# if somebody registers a precompile, presumably they want it to work
# on all envs.
_precompiles = {}


def register_precompile(*args, **kwargs):
    warnings.warn(
        "register_recompile has been renamed to register_raw_precompile!", stacklevel=2
    )


def register_raw_precompile(address, fn, force=False):
    global _precompiles
    address = _addr(address)
    if address in _precompiles and not force:
        raise ValueError(f"Already registered: {address}")
    _precompiles[address] = fn


def deregister_raw_precompile(address, force=True):
    address = _addr(address)
    if address not in _precompiles and not force:
        raise ValueError("Not registered: {address}")
    _precompiles.pop(address, None)


def console_log(computation):
    msgdata = computation.msg.data_as_bytes
    schema, payload = abi.decode("(string,bytes)", msgdata[4:])
    data = abi.decode(schema, payload)
    print(*data, file=sys.stderr)
    return computation


CONSOLE_ADDRESS = bytes.fromhex("000000000000000000636F6E736F6C652E6C6F67")


register_raw_precompile(CONSOLE_ADDRESS, console_log)


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

    def __init__(self, *args, start_pc=0, fake_codesize=None, contract=None, **kwargs):
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
        account = to_checksum_address(computation.msg.storage_address)

        self.trace_db.setdefault(account, set())
        # we don't want to deal with snapshots/commits/reverts, so just
        # register that the slot was touched and downstream can filter
        # zero entries.
        self.trace_db[account].add(slot)

        # dispatch into py-evm
        self.sstore(computation)


# ### End section: sha3 tracing


# wrapper class around py-evm which provides a "contract-centric" API
class Env:
    _singleton = None
    _initial_address_counter = 100
    _coverage_enabled = False

    def __init__(self):
        self.chain = _make_chain()

        self._gas_price = None

        self._address_counter = self.__class__._initial_address_counter

        self._aliases = {}

        # TODO differentiate between origin and sender
        self.eoa = self.generate_address("eoa")

        self._contracts = {}
        self._code_registry = {}

        self._profiled_contracts = {}
        self._cached_call_profiles = {}
        self._cached_line_profiles = {}
        self._coverage_data = {}

        self.sha3_trace = {}
        self.sstore_trace = {}

        self._init_vm()

    def get_gas_price(self):
        return self._gas_price or 0

    def _init_vm(self, reset_traces=True):
        self.vm = self.chain.get_vm()
        self.vm.patch = VMPatcher(self.vm)

        env = self

        class OpcodeTracingComputation(self.vm.state.computation_class):
            _gas_meter_class = GasMeter

            def __init__(self, *args, **kwargs):
                # super() hardcodes CodeStream into the ctor
                # so we have to override it here
                super().__init__(*args, **kwargs)
                self.code = TracingCodeStream(
                    self.code._raw_code_bytes,
                    fake_codesize=getattr(self.msg, "_fake_codesize", None),
                    start_pc=getattr(self.msg, "_start_pc", 0),
                )
                global _precompiles
                # copy so as not to mess with class state
                self._precompiles = self._precompiles.copy()
                self._precompiles.update(_precompiles)

                global _opcode_overrides
                # copy so as not to mess with class state
                self.opcodes = self.opcodes.copy()
                self.opcodes.update(_opcode_overrides)

                self._gas_meter = self._gas_meter_class(self.msg.gas)
                if hasattr(self._gas_meter, "_set_code"):
                    self._gas_meter._set_code(self.code)

                self._child_pcs = []

            def add_child_computation(self, child_computation):
                super().add_child_computation(child_computation)
                # track PCs of child calls for profiling purposes
                self._child_pcs.append(self.code.program_counter)

            # hijack creations to automatically generate blueprints
            @classmethod
            def apply_create_message(cls, state, msg, tx_ctx):
                computation = super().apply_create_message(state, msg, tx_ctx)

                bytecode = msg.code
                # cf. eth/vm/logic/system/Create* opcodes
                contract_address = msg.storage_address

                if is_eip1167_contract(bytecode):
                    contract_address = extract_eip1167_address(bytecode)
                    bytecode = self.vm.state.get_code(contract_address)

                if bytecode in self._code_registry:
                    target = self._code_registry[bytecode].deployer.at(contract_address)
                    target.created_from = to_checksum_address(msg.sender)
                    env.register_contract(contract_address, target)

                return computation

        # TODO make metering toggle-able
        c = OpcodeTracingComputation

        self.vm.state.computation_class = c

        # we usually want to reset the trace data structures
        # but sometimes don't, give caller the option.
        if reset_traces:
            self.sha3_trace = {}
            self.sstore_trace = {}

        # patch in tracing opcodes
        c.opcodes[0x20] = Sha3PreimageTracer(c.opcodes[0x20], self.sha3_trace)
        c.opcodes[0x55] = SstoreTracer(c.opcodes[0x55], self.sstore_trace)

    def fork(self, url, reset_traces=True, **kwargs):
        kwargs["url"] = url
        AccountDBFork._rpc_init_kwargs = kwargs
        self.vm.__class__._state_class.account_db_class = AccountDBFork
        self._init_vm(reset_traces=reset_traces)
        block_info = self.vm.state._account_db._block_info

        self.vm.patch.timestamp = int(block_info["timestamp"], 16)
        self.vm.patch.block_number = int(block_info["number"], 16)
        # TODO patch the other stuff

    def set_gas_meter_class(self, cls: type) -> None:
        self.vm.state.computation_class._gas_meter_class = cls

    @contextlib.contextmanager
    def gas_meter_class(self, cls):
        tmp = self.vm.state.computation_class._gas_meter_class
        try:
            self.set_gas_meter_class(cls)
            yield
        finally:
            self.set_gas_meter_class(tmp)

    def enable_gas_profiling(self) -> None:
        self.set_gas_meter_class(ProfilingGasMeter)

    def disable_gas_metering(self) -> None:
        self.set_gas_meter_class(NoGasMeter)

    def reset_gas_metering_behavior(self) -> None:
        # Reset gas metering to the default behavior
        self.set_gas_meter_class(GasMeter)

    # set balance of address in py-evm
    def set_balance(self, addr, value):
        self.vm.state.set_balance(to_canonical_address(addr), value)

    # get balance of address in py-evm
    def get_balance(self, addr):
        return self.vm.state.get_balance(to_canonical_address(addr))

    def register_contract(self, address, obj):
        self._contracts[to_checksum_address(address)] = obj

        # also register it in the registry for
        # create_minimal_proxy_to and create_copy_of
        bytecode = self.vm.state.get_code(to_canonical_address(address))
        self._code_registry[bytecode] = obj

    def register_blueprint(self, bytecode, obj):
        self._code_registry[bytecode] = obj

    def lookup_contract(self, address):
        if address == b"":
            return None
        return self._contracts.get(to_checksum_address(address))

    def alias(self, address, name):
        self._aliases[to_checksum_address(address)] = name

    def lookup_alias(self, address):
        return self._aliases[to_checksum_address(address)]

    # advanced: reset warm/cold counters for addresses and storage
    def _reset_access_counters(self):
        self.vm.state._account_db._reset_access_counters()

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

    @contextlib.contextmanager
    def sender(self, address):
        tmp = self.eoa
        self.eoa = to_checksum_address(address)
        try:
            yield
        finally:
            self.eoa = tmp

    def prank(self, *args, **kwargs):
        return self.sender(*args, **kwargs)

    @classmethod
    def get_singleton(cls):
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def generate_address(self, alias: Optional[str] = None) -> AddressType:
        self._address_counter += 1
        t = self._address_counter.to_bytes(length=20, byteorder="big")
        # checksum addr easier for humans to debug
        ret = to_checksum_address(t)
        if alias is not None:
            self.alias(ret, alias)

        return ret

    # helper fn
    def _get_sender(self, sender=None) -> Address:
        if sender is None:
            sender = self.eoa
        if self.eoa is None:
            raise ValueError(f"{self}.eoa not defined!")
        return _addr(sender)

    def deploy_code(
        self,
        sender: Optional[AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        bytecode: bytes = b"",
        start_pc: int = 0,
        # override the target address:
        override_address: Optional[AddressType] = None,
    ) -> tuple[AddressType, bytes]:
        if gas is None:
            gas = self.vm.state.gas_limit
        sender = self._get_sender(sender)

        if override_address is not None:
            target_address = _addr(override_address)
        else:
            nonce = self.vm.state.get_nonce(sender)
            self.vm.state.increment_nonce(sender)
            target_address = generate_contract_address(sender, nonce)

        msg = Message(
            to=constants.CREATE_CONTRACT_ADDRESS,  # i.e., b""
            sender=sender,
            gas=gas,
            value=value,
            code=bytecode,
            create_address=target_address,
            data=b"",
        )
        origin = sender  # XXX: consider making this parametrizable
        tx_ctx = BaseTransactionContext(origin=origin, gas_price=self.get_gas_price())
        c = self.vm.state.computation_class.apply_create_message(
            self.vm.state, msg, tx_ctx
        )

        if c.is_error:
            raise c.error

        return target_address, c.output

    def raw_call(
        self,
        to_address,
        sender: Optional[AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        data: bytes = b"",
    ):
        # simple wrapper around `execute_code` to help simulate calling
        # a contract from an EOA.
        ret = self.execute_code(
            to_address=to_address, sender=sender, gas=gas, value=value, data=data
        )
        if ret.is_error:
            # differ from execute_code, consumers of execute_code want to get
            # error returned "silently" (not thru exception handling mechanism)
            # whereas users of call() expect the exception to be thrown, just
            # like a regular contract call.
            raise ret.error

        return ret

    def execute_code(
        self,
        to_address: AddressType = constants.ZERO_ADDRESS,
        sender: Optional[AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        data: bytes = b"",
        override_bytecode: Optional[bytes] = None,
        is_modifying: bool = True,
        start_pc: int = 0,
        fake_codesize: Optional[int] = None,
        contract: Any = None,  # the calling VyperContract
    ) -> Any:
        if gas is None:
            gas = self.vm.state.gas_limit
        sender = self._get_sender(sender)

        class FakeMessage(Message):  # Message object with settable attrs
            __dict__: dict = {}

        to = _addr(to_address)

        bytecode = override_bytecode
        if override_bytecode is None:
            bytecode = self.vm.state.get_code(to)

        is_static = not is_modifying

        msg = FakeMessage(
            sender=sender,
            to=to,
            gas=gas,
            value=value,
            code=bytecode,  # type: ignore
            data=data,
            is_static=is_static,
        )

        msg._fake_codesize = fake_codesize  # type: ignore
        msg._start_pc = start_pc  # type: ignore
        msg._contract = contract  # type: ignore
        origin = sender  # XXX: consider making this parametrizable
        tx_ctx = BaseTransactionContext(origin=origin, gas_price=self.get_gas_price())
        ret = self.vm.state.computation_class.apply_message(self.vm.state, msg, tx_ctx)

        if self._coverage_enabled:
            self._hook_trace_computation(ret, contract)

        return ret

    def _hook_trace_computation(self, computation, contract=None):
        # XXX perf: don't trace if contract is None
        for _pc in computation.code._trace:
            # loop over pc so that it is available when coverage hooks into it
            pass
        for child in computation.children:
            if child.msg.code_address != b"":
                child_contract = self.lookup_contract(child.msg.code_address)
                self._hook_trace_computation(child, child_contract)

    # function to time travel
    def time_travel(
        self,
        seconds: Optional[int] = None,
        blocks: Optional[int] = None,
        block_delta: int = 12,
    ) -> None:
        if (seconds is None) == (blocks is None):
            raise ValueError("One of seconds or blocks should be set")
        if seconds is not None:
            blocks = seconds // block_delta
        else:
            assert blocks is not None  # mypy hint
            seconds = blocks * block_delta

        self.vm.patch.timestamp += seconds
        self.vm.patch.block_number += blocks


GENESIS_PARAMS = {"difficulty": constants.GENESIS_DIFFICULTY, "gas_limit": int(1e8)}


# TODO make fork configurable - ex. "latest", "frontier", "berlin"
# TODO make genesis params+state configurable
def _make_chain():
    # TODO should we use MiningChain? is there a perf difference?
    # TODO debug why `fork_at()` cannot accept 0 as block num
    _Chain = chain.build(MainnetChain, chain.latest_mainnet_at(1))
    return _Chain.from_genesis(AtomicDB(), GENESIS_PARAMS)
