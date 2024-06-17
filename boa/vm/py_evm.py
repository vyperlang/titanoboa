"""
A wrapper for the py-evm engine to provide a consistent interface for the environment.
Handles low level details around state and py-evm tracing.
"""

import contextlib
import logging
import sys
import warnings
from typing import Any, Iterator, Optional, Type

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
from eth_utils import setup_DEBUG2_logging

from boa.rpc import RPC
from boa.util.abi import Address, abi_decode
from boa.util.eip1167 import extract_eip1167_address, is_eip1167_contract
from boa.vm.fast_accountdb import patch_pyevm_state_object, unpatch_pyevm_state_object
from boa.vm.fork import AccountDBFork
from boa.vm.gas_meters import GasMeter
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
        "prevrandao": "_mix_hash",
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


class Sha3PreimageTracer:
    mnemonic = "SHA3"

    # trace preimages of sha3

    def __init__(self, sha3_op, env):
        self.env = env
        self.sha3 = sha3_op

    def __call__(self, computation):
        size, offset = [to_int(x) for x in computation._stack.values[-2:]]

        # dispatch into py-evm
        self.sha3(computation)

        if size != 64:
            return

        preimage = computation._memory.read_bytes(offset, size)

        value = computation._stack.values[-1]
        image = to_bytes(value)

        self.env.sha3_trace[preimage] = image


class SstoreTracer:
    mnemonic = "SSTORE"

    def __init__(self, sstore_op, env):
        self.env = env
        self.sstore = sstore_op

    def __call__(self, computation):
        value, slot = [to_int(t) for t in computation._stack.values[-2:]]
        account = computation.msg.storage_address

        # we don't want to deal with snapshots/commits/reverts, so just
        # register that the slot was touched and downstream can filter
        # zero entries.
        self.env.sstore_trace.setdefault(account, set()).add(slot)

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
    def apply_create_message(cls, state, msg, tx_ctx, **kwargs):
        computation = super().apply_create_message(state, msg, tx_ctx, **kwargs)

        bytecode = msg.code
        # cf. eth/vm/logic/system/Create* opcodes
        contract_address = msg.storage_address

        if is_eip1167_contract(bytecode):
            contract_address = extract_eip1167_address(bytecode)
            bytecode = cls.env.evm.vm.state.get_code(contract_address)

        if bytecode in cls.env._code_registry:
            target = cls.env._code_registry[bytecode].deployer.at(contract_address)
            target.created_from = Address(msg.sender)
            cls.env.register_contract(contract_address, target)

        return computation

    @classmethod
    def apply_computation(cls, state, msg, tx_ctx, **kwargs):
        addr = msg.code_address
        contract = cls.env._lookup_contract_fast(addr) if addr else None

        def finalize(c):
            if c.is_error:
                # After the computation is applied with an error the state is
                # reverted. Before the revert, save the contract repr for the
                # error message
                c._contract_repr_before_revert = repr(contract)
            return c

        if contract is None or not cls.env.evm._fast_mode_enabled:
            # print("SLOW MODE")
            computation = super().apply_computation(state, msg, tx_ctx, **kwargs)
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


class PyEVM:
    def __init__(self, env, fast_mode_enabled=False, fork_try_prefetch_state=False):
        self.chain = _make_chain()
        self.env = env
        self._fast_mode_enabled = fast_mode_enabled
        self._fork_try_prefetch_state = fork_try_prefetch_state
        self._init_vm()

    def _init_vm(self, account_db_class=AccountDB):
        self.vm = self.chain.get_vm()
        self.vm.__class__._state_class.account_db_class = account_db_class

        self.patch = VMPatcher(self.vm)

        c: Type[titanoboa_computation] = type(
            "TitanoboaComputation",
            (titanoboa_computation, self.vm.state.computation_class),
            {"env": self.env},
        )

        if self._fast_mode_enabled:
            patch_pyevm_state_object(self.vm.state)

        self.vm.state.computation_class = c

        # patch in tracing opcodes
        c.opcodes[0x20] = Sha3PreimageTracer(c.opcodes[0x20], self.env)
        c.opcodes[0x55] = SstoreTracer(c.opcodes[0x55], self.env)

    def enable_fast_mode(self, flag: bool = True):
        if flag:
            patch_pyevm_state_object(self.vm.state)
        else:
            unpatch_pyevm_state_object(self.vm.state)

    def fork_rpc(self, rpc: RPC, block_identifier: str, **kwargs):
        account_db_class = AccountDBFork.class_from_rpc(rpc, block_identifier, **kwargs)
        self._init_vm(account_db_class)
        block_info = self.vm.state._account_db._block_info

        self.patch.timestamp = int(block_info["timestamp"], 16)
        self.patch.block_number = int(block_info["number"], 16)
        self.patch.chain_id = int(rpc.fetch("eth_chainId", []), 16)

        self.vm.state._account_db._rpc._init_db()

    @property
    def is_forked(self):
        return issubclass(
            self.vm.__class__._state_class.account_db_class, AccountDBFork
        )

    def get_gas_meter_class(self):
        return self.vm.state.computation_class._gas_meter_class

    def set_gas_meter_class(self, cls: type):
        self.vm.state.computation_class._gas_meter_class = cls

    def get_balance(self, address: Address):
        return self.vm.state.get_balance(address.canonical_address)

    def set_balance(self, address: Address, value):
        self.vm.state.set_balance(address.canonical_address, value)

    def get_code(self, address: Address) -> bytes:
        return self.vm.state.get_code(address.canonical_address)

    def set_code(self, address: Address, code: bytes) -> None:
        self.vm.state.set_code(address.canonical_address, code)

    def get_storage(self, address: Address, slot: int) -> int:
        return self.vm.state.get_storage(address.canonical_address, slot)

    def set_storage(self, address: Address, slot: int, value: int) -> None:
        self.vm.state.set_storage(address.canonical_address, slot, value)

    def get_gas_limit(self):
        return self.vm.state.gas_limit

    # advanced: reset warm/cold counters for addresses and storage
    def reset_access_counters(self):
        self.vm.state._account_db._reset_access_counters()

    def snapshot(self) -> Any:
        return self.vm.state.snapshot()

    def revert(self, snapshot_id: Any) -> None:
        self.vm.state.revert(snapshot_id)

    def generate_create_address(self, sender: Address):
        nonce = self.vm.state.get_nonce(sender.canonical_address)
        self.vm.state.increment_nonce(sender.canonical_address)
        return Address(generate_contract_address(sender.canonical_address, nonce))

    def deploy_code(
        self,
        sender: Address,
        origin: Address,
        target_address: Address,
        gas: Optional[int],
        gas_price: int,
        value: int,
        bytecode: bytes,
    ):
        if gas is None:
            gas = self.vm.state.gas_limit

        msg = Message(
            to=constants.CREATE_CONTRACT_ADDRESS,  # i.e., b""
            sender=sender.canonical_address,
            gas=gas,
            value=value,
            code=bytecode,
            create_address=target_address.canonical_address,
            data=b"",
        )

        if self.is_forked and self._fork_try_prefetch_state:
            self.vm.state._account_db.try_prefetch_state(msg)

        tx_ctx = BaseTransactionContext(
            origin=origin.canonical_address, gas_price=gas_price
        )
        return self.vm.state.computation_class.apply_create_message(
            self.vm.state, msg, tx_ctx
        )

    def execute_code(
        self,
        sender: Address,
        to: Address,
        gas: int,
        gas_price: int,
        value: int,
        bytecode: bytes,
        data: bytes,
        is_static: bool,
        fake_codesize: Optional[int],
        start_pc: int,
        ir_executor: Any,
        contract: Any,
    ):
        msg = FakeMessage(
            sender=sender.canonical_address,
            to=to.canonical_address,
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

        if self.is_forked and self._fork_try_prefetch_state:
            self.vm.state._account_db.try_prefetch_state(msg)

        origin = sender.canonical_address  # XXX: consider making this parameterizable
        tx_ctx = BaseTransactionContext(origin=origin, gas_price=gas_price)
        return self.vm.state.computation_class.apply_message(self.vm.state, msg, tx_ctx)

    def get_storage_slot(self, address: Address, slot: int) -> bytes:
        data = self.vm.state._account_db.get_storage(address.canonical_address, slot)
        return data.to_bytes(32, "big")


GENESIS_PARAMS = {"difficulty": constants.GENESIS_DIFFICULTY, "gas_limit": int(1e8)}


# TODO make fork configurable - ex. "latest", "frontier", "berlin"
# TODO make genesis params+state configurable
def _make_chain():
    # TODO should we use MiningChain? is there a perf difference?
    # TODO debug why `fork_at()` cannot accept 0 as block num
    _Chain = chain.build(MainnetChain, chain.latest_mainnet_at(1))
    return _Chain.from_genesis(AtomicDB(), GENESIS_PARAMS)
