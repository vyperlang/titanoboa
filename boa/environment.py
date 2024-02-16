# the main "entry point" for patching py-evm.
# handles low level details around state and py-evm tracing.

import contextlib
import logging
import random
import sys
import warnings
from typing import Any, Iterator, Optional, TypeAlias

import eth.constants as constants
import eth.tools.builder.chain as chain
import eth.vm.forks.spurious_dragon.computation as spurious_dragon
from eth._utils.address import generate_contract_address
from eth.chains.mainnet import MainnetChain
from eth.db.account import AccountDB
from eth.db.atomic import AtomicDB
from eth.exceptions import Halt
from eth.vm.code_stream import CodeStream
from eth.vm.gas_meter import allow_negative_refund_strategy
from eth.vm.message import Message
from eth.vm.opcode_values import STOP
from eth.vm.transaction_context import BaseTransactionContext
from eth_typing import Address as PYEVM_Address  # it's just bytes.
from eth_utils import setup_DEBUG2_logging

from boa.rpc import RPC, EthereumRPC
from boa.util.abi import Address, abi_decode
from boa.util.eip1167 import extract_eip1167_address, is_eip1167_contract
from boa.vm.fast_accountdb import patch_pyevm_state_object, unpatch_pyevm_state_object
from boa.vm.fork import AccountDBFork
from boa.vm.gas_meters import GasMeter, NoGasMeter, ProfilingGasMeter
from boa.vm.utils import to_bytes, to_int


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


# make mypy happy
_AddressType: TypeAlias = Address | str | bytes | PYEVM_Address


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
    address = Address(address)
    if address in _precompiles and not force:
        raise ValueError(f"Already registered: {address}")
    _precompiles[address.canonical_address] = fn


def deregister_raw_precompile(address, force=True):
    address = Address(address).canonical_address
    if address not in _precompiles and not force:
        raise ValueError("Not registered: {address}")
    _precompiles.pop(address, None)


def console_log(computation):
    msgdata = computation.msg.data_as_bytes
    schema, payload = abi_decode("(string,bytes)", msgdata[4:])
    data = abi_decode(schema, payload)
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
def _stackitem_to_int(value):
    if isinstance(value, tuple):
        return to_int(value[1])  # how py-evm<=0.8.0b1 stores stuff on stack
    else:
        return to_int(value)


def _stackitem_to_bytes(value):
    if isinstance(value, tuple):
        return to_bytes(value[1])  # how py-evm<=0.8.0b1 stores stuff on stack
    else:
        return to_bytes(value)


class Sha3PreimageTracer:
    mnemonic = "SHA3"

    # trace preimages of sha3

    def __init__(self, sha3_op, env):
        self.env = env
        self.sha3 = sha3_op

    def __call__(self, computation):
        size, offset = [_stackitem_to_int(x) for x in computation._stack.values[-2:]]

        # dispatch into py-evm
        self.sha3(computation)

        if size != 64:
            return

        preimage = computation._memory.read_bytes(offset, size)

        image = _stackitem_to_bytes(computation._stack.values[-1])

        self.env._trace_sha3_preimage(preimage, image)


class SstoreTracer:
    mnemonic = "SSTORE"

    def __init__(self, sstore_op, env):
        self.env = env
        self.sstore = sstore_op

    def __call__(self, computation):
        value, slot = [_stackitem_to_int(t) for t in computation._stack.values[-2:]]
        account = computation.msg.storage_address

        self.env._trace_sstore(account, slot)

        # dispatch into py-evm
        self.sstore(computation)


# ### End section: sha3 tracing


# py-evm uses class instantiaters which need to be classes
# instead of like factories or other easier to use architectures -
# `titanoboa_computation` is a class which can be constructed dynamically
class titanoboa_computation:
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

        self._gas_meter = self._gas_meter_class(
            self.msg.gas, refund_strategy=allow_negative_refund_strategy
        )
        if hasattr(self._gas_meter, "_set_code"):
            self._gas_meter._set_code(self.code)

        self._child_pcs = []
        self._contract_repr_before_revert = None

    @property
    def net_gas_used(self):
        return max(0, self.get_gas_used() - self.get_gas_refund())

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
            bytecode = cls.env.vm.state.get_code(contract_address)

        if bytecode in cls.env._code_registry:
            target = cls.env._code_registry[bytecode].deployer.at(contract_address)
            target.created_from = Address(msg.sender)
            cls.env.register_contract(contract_address, target)

        return computation

    @classmethod
    def apply_computation(cls, state, msg, tx_ctx):
        addr = msg.code_address
        contract = cls.env._lookup_contract_fast(addr) if addr else None

        def finalize(c):
            if c.is_error:
                # After the computation is applied with an error the state is
                # reverted. Before the revert, save the contract repr for the
                # error message
                c._contract_repr_before_revert = repr(contract)
            return c

        if contract is None or not cls.env._fast_mode_enabled:
            # print("SLOW MODE")
            computation = super().apply_computation(state, msg, tx_ctx)
            return finalize(computation)

        with cls(state, msg, tx_ctx) as computation:
            try:
                if getattr(msg, "_ir_executor", None) is not None:
                    # print("MSG HAS IR EXECUTOR")
                    # this happens when bytecode is overridden, e.g.
                    # for injected functions. note ir_executor is (correctly)
                    # used for the outer computation only because on subcalls
                    # a clean message is constructed for the child computation
                    msg._ir_executor.exec(computation)
                else:
                    # print("REGULAR FAST MODE")
                    contract.ir_executor.exec(computation)
            except Halt:
                pass

        # return computation outside of with block; computation.__exit__
        # swallows exceptions (including Revert).
        return finalize(computation)


# Message object with extra attrs we can use to thread things through
# the execution context.
class FakeMessage(Message):
    def __init__(
        self,
        *args,
        ir_executor=None,
        fake_codesize=None,
        start_pc=0,
        contract=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._ir_executor = ir_executor
        self._fake_codesize = fake_codesize
        self._start_pc = start_pc
        self._contract = contract


# wrapper class around py-evm which provides a "contract-centric" API
class Env:
    _singleton = None
    _random = random.Random("titanoboa")  # something reproducible
    _coverage_enabled = False
    _fast_mode_enabled = False
    _fork_try_prefetch_state = False

    def __init__(self):
        self.chain = _make_chain()

        self._gas_price = None

        self._aliases = {}

        # TODO differentiate between origin and sender
        self.eoa = self.generate_address("eoa")

        self._contracts = {}
        self._code_registry = {}

        self._profiled_contracts = {}
        self._cached_call_profiles = {}
        self._cached_line_profiles = {}
        self._coverage_data = {}

        self._gas_tracker = 0

        self.sha3_trace = {}
        self.sstore_trace = {}

        self._init_vm()

    def set_random_seed(self, seed=None):
        self._random = random.Random(seed)

    def get_gas_price(self):
        return self._gas_price or 0

    def _init_vm(self, reset_traces=True, account_db_class=AccountDB):
        self.vm = self.chain.get_vm()
        self.vm.__class__._state_class.account_db_class = account_db_class
        self.vm.patch = VMPatcher(self.vm)

        c = type(
            "TitanoboaComputation",
            (titanoboa_computation, self.vm.state.computation_class),
            {"env": self},
        )

        if self._fast_mode_enabled:
            patch_pyevm_state_object(self.vm.state)

        self.vm.state.computation_class = c

        # we usually want to reset the trace data structures
        # but sometimes don't, give caller the option.
        if reset_traces:
            self.sha3_trace = {}
            self.sstore_trace = {}

        # patch in tracing opcodes
        c.opcodes[0x20] = Sha3PreimageTracer(c.opcodes[0x20], self)
        c.opcodes[0x55] = SstoreTracer(c.opcodes[0x55], self)

    def _trace_sha3_preimage(self, preimage, image):
        self.sha3_trace[image] = preimage

    def _trace_sstore(self, account, slot):
        self.sstore_trace.setdefault(account, set())
        # we don't want to deal with snapshots/commits/reverts, so just
        # register that the slot was touched and downstream can filter
        # zero entries.
        self.sstore_trace[account].add(slot)

    def enable_fast_mode(self, flag: bool = True):
        self._fast_mode_enabled = flag
        if flag:
            patch_pyevm_state_object(self.vm.state)
        else:
            unpatch_pyevm_state_object(self.vm.state)

    def fork(self, url: str, reset_traces=True, block_identifier="safe", **kwargs):
        return self.fork_rpc(EthereumRPC(url), reset_traces, block_identifier, **kwargs)

    def fork_rpc(self, rpc: RPC, reset_traces=True, block_identifier="safe", **kwargs):
        """
        Fork the environment to a local chain.
        :param rpc: RPC to fork from
        :param reset_traces: Reset the traces
        :param block_identifier: Block identifier to fork from
        :param kwargs: Additional arguments for the RPC
        """
        account_db_class = AccountDBFork.class_from_rpc(rpc, block_identifier, **kwargs)
        self._init_vm(reset_traces, account_db_class)
        block_info = self.vm.state._account_db._block_info

        self.vm.patch.timestamp = int(block_info["timestamp"], 16)
        self.vm.patch.block_number = int(block_info["number"], 16)
        # TODO patch the other stuff

    @property
    def _fork_mode(self):
        return self.vm.__class__._state_class.account_db_class == AccountDBFork

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
        self.vm.state.set_balance(Address(addr).canonical_address, value)

    # get balance of address in py-evm
    def get_balance(self, addr):
        return self.vm.state.get_balance(Address(addr).canonical_address)

    def register_contract(self, address, obj):
        addr = Address(address).canonical_address
        self._contracts[addr] = obj

        # also register it in the registry for
        # create_minimal_proxy_to and create_copy_of
        bytecode = self.vm.state.get_code(addr)
        self._code_registry[bytecode] = obj

    def register_blueprint(self, bytecode, obj):
        self._code_registry[bytecode] = obj

    def _lookup_contract_fast(self, address: PYEVM_Address):
        return self._contracts.get(address)

    def lookup_contract(self, address: _AddressType):
        if address == b"":
            return None
        return self._contracts.get(Address(address).canonical_address)

    def alias(self, address, name):
        self._aliases[Address(address).canonical_address] = name

    def lookup_alias(self, address):
        return self._aliases[Address(address).canonical_address]

    # advanced: reset warm/cold counters for addresses and storage
    def _reset_access_counters(self):
        self.vm.state._account_db._reset_access_counters()

    def get_gas_used(self):
        return self._gas_tracker

    def reset_gas_used(self):
        self._gas_tracker = 0
        self._reset_access_counters()

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
        self.eoa = Address(address)
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

    def generate_address(self, alias: Optional[str] = None) -> _AddressType:
        t = Address(self._random.randbytes(20))
        if alias is not None:
            self.alias(t, alias)

        return t

    # helper fn
    def _get_sender(self, sender=None) -> PYEVM_Address:
        if sender is None:
            sender = self.eoa
        if self.eoa is None:
            raise ValueError(f"{self}.eoa not defined!")
        return Address(sender).canonical_address

    def _update_gas_used(self, gas_used: int):
        self._gas_tracker += gas_used

    def deploy_code(
        self,
        sender: Optional[_AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        bytecode: bytes = b"",
        start_pc: int = 0,
        # override the target address:
        override_address: Optional[_AddressType] = None,
    ) -> tuple[Address, bytes]:
        if gas is None:
            gas = self.vm.state.gas_limit

        sender = self._get_sender(sender)

        if override_address is not None:
            target_address = Address(override_address)
        else:
            nonce = self.vm.state.get_nonce(sender)
            self.vm.state.increment_nonce(sender)
            target_address = Address(generate_contract_address(sender, nonce))

        msg = Message(
            to=constants.CREATE_CONTRACT_ADDRESS,  # i.e., b""
            sender=sender,
            gas=gas,
            value=value,
            code=bytecode,
            create_address=target_address.canonical_address,
            data=b"",
        )

        if self._fork_mode and self._fork_try_prefetch_state:
            self.vm.state._account_db.try_prefetch_state(msg)

        origin = sender  # XXX: consider making this parametrizable
        tx_ctx = BaseTransactionContext(origin=origin, gas_price=self.get_gas_price())
        c = self.vm.state.computation_class.apply_create_message(
            self.vm.state, msg, tx_ctx
        )

        if c._gas_meter_class != NoGasMeter:
            self._update_gas_used(c.get_gas_used())

        if c.is_error:
            raise c.error

        return target_address, c.output

    def raw_call(
        self,
        to_address,
        sender: Optional[_AddressType] = None,
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
        to_address: _AddressType = constants.ZERO_ADDRESS,
        sender: Optional[_AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        data: bytes = b"",
        override_bytecode: Optional[bytes] = None,
        ir_executor: Any = None,
        is_modifying: bool = True,
        start_pc: int = 0,
        fake_codesize: Optional[int] = None,
        contract: Any = None,  # the calling VyperContract
    ) -> Any:
        if gas is None:
            gas = self.vm.state.gas_limit

        sender = self._get_sender(sender)

        to = Address(to_address).canonical_address

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
            fake_codesize=fake_codesize,
            start_pc=start_pc,
            ir_executor=ir_executor,
            contract=contract,
        )
        if self._fork_mode and self._fork_try_prefetch_state:
            self.vm.state._account_db.try_prefetch_state(msg)

        origin = sender  # XXX: consider making this parametrizable
        tx_ctx = BaseTransactionContext(origin=origin, gas_price=self.get_gas_price())

        ret = self.vm.state.computation_class.apply_message(self.vm.state, msg, tx_ctx)

        if self._coverage_enabled:
            self._hook_trace_computation(ret, contract)

        if ret._gas_meter_class != NoGasMeter:
            self._update_gas_used(ret.get_gas_used())

        return ret

    def _hook_trace_computation(self, computation, contract=None):
        # XXX perf: don't trace if contract is None
        for _pc in computation.code._trace:
            # loop over pc so that it is available when coverage hooks into it
            pass

        for child in computation.children:
            if child.msg.code_address == b"":
                continue
            child_contract = self._lookup_contract_fast(child.msg.code_address)
            self._hook_trace_computation(computation, child_contract)

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
