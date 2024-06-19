"""
The entry point for managing the execution environment.
"""
# the main "entry point" for patching py-evm.
# handles low level details around state and py-evm tracing.

import contextlib
import random
from typing import Any, Optional, TypeAlias

import eth.constants as constants
from eth_typing import Address as PYEVM_Address  # it's just bytes.

from boa.rpc import RPC, EthereumRPC
from boa.util.abi import Address
from boa.vm.gas_meters import GasMeter, NoGasMeter, ProfilingGasMeter
from boa.vm.py_evm import PyEVM

# make mypy happy
_AddressType: TypeAlias = Address | str | bytes | PYEVM_Address


# wrapper class around py-evm which provides a "contract-centric" API
class Env:
    _singleton = None
    _random = random.Random("titanoboa")  # something reproducible
    _coverage_enabled = False

    def __init__(self, fork_try_prefetch_state=False, fast_mode_enabled=False):
        self._gas_price = None

        self._aliases = {}

        # TODO differentiate between origin and sender
        self.eoa = self.generate_address("eoa")

        self._contracts = {}
        self._code_registry = {}

        self.sha3_trace: dict = {}
        self.sstore_trace: dict = {}

        self._profiled_contracts = {}
        self._cached_call_profiles = {}
        self._cached_line_profiles = {}
        self._coverage_data = {}

        self._gas_tracker = 0

        self.evm = PyEVM(self, fast_mode_enabled, fork_try_prefetch_state)

    def set_random_seed(self, seed=None):
        self._random = random.Random(seed)

    def get_gas_price(self):
        return self._gas_price or 0

    def enable_fast_mode(self, flag: bool = True):
        self.evm.enable_fast_mode(flag)

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
        # we usually want to reset the trace data structures
        # but sometimes don't, give caller the option.
        if reset_traces:
            self.sha3_trace = {}
            self.sstore_trace = {}

        self.evm.fork_rpc(rpc, block_identifier, **kwargs)

    def get_gas_meter_class(self):
        return self.evm.get_gas_meter_class()

    def set_gas_meter_class(self, cls: type) -> None:
        self.evm.set_gas_meter_class(cls)

    @contextlib.contextmanager
    def gas_meter_class(self, cls):
        tmp = self.evm.get_gas_meter_class()
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
        self.evm.set_balance(Address(addr), value)

    # get balance of address in py-evm
    def get_balance(self, addr):
        return self.evm.get_balance(Address(addr))

    def register_contract(self, address, obj):
        addr = Address(address)
        self._contracts[addr.canonical_address] = obj

        # also register it in the registry for
        # create_minimal_proxy_to and create_copy_of
        bytecode = self.evm.get_code(addr)
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
        self.evm.reset_access_counters()

    def get_gas_used(self):
        return self._gas_tracker

    def reset_gas_used(self):
        self._gas_tracker = 0
        self._reset_access_counters()

    # context manager which snapshots the state and reverts
    # to the snapshot on exiting the with statement
    @contextlib.contextmanager
    def anchor(self):
        snapshot_id = self.evm.snapshot()
        try:
            with self.evm.patch.anchor():
                yield
        finally:
            self.evm.revert(snapshot_id)

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
    def _get_sender(self, sender=None) -> Address:
        if sender is None:
            sender = self.eoa
        if self.eoa is None:
            raise ValueError(f"{self}.eoa not defined!")
        return Address(sender)

    def _update_gas_used(self, gas_used: int):
        self._gas_tracker += gas_used

    def deploy(
        self,
        sender: Optional[_AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        bytecode: bytes = b"",
        start_pc: int = 0,  # TODO: This isn't used
        # override the target address:
        override_address: Optional[_AddressType] = None,
    ):
        sender = self._get_sender(sender)

        if override_address is None:
            target_address = self.evm.generate_create_address(sender)
        else:
            target_address = Address(override_address)

        origin = sender  # XXX: consider making this parameterizable
        computation = self.evm.deploy_code(
            sender=sender,
            origin=origin,
            target_address=target_address,
            gas=gas,
            gas_price=self.get_gas_price(),
            value=value,
            bytecode=bytecode,
        )

        if computation._gas_meter_class != NoGasMeter:
            self._update_gas_used(computation.get_gas_used())
        return target_address, computation

    def deploy_code(self, *args, **kwargs) -> tuple[Address, bytes]:
        address, computation = self.deploy(*args, **kwargs)
        if computation.is_error:
            raise computation.error
        return address, computation.output

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
            gas = self.evm.get_gas_limit()

        sender = self._get_sender(sender)

        to = Address(to_address)

        bytecode = override_bytecode
        if override_bytecode is None:
            bytecode = self.evm.get_code(to)

        is_static = not is_modifying
        ret = self.evm.execute_code(
            sender=sender,
            to=to,
            gas=gas,
            gas_price=self.get_gas_price(),
            value=value,
            bytecode=bytecode,
            data=data,
            is_static=is_static,
            fake_codesize=fake_codesize,
            start_pc=start_pc,
            ir_executor=ir_executor,
            contract=contract,
        )
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
            self._hook_trace_computation(child, child_contract)

    def get_code(self, address: _AddressType) -> bytes:
        return self.evm.get_code(Address(address))

    def set_code(self, address: _AddressType, code: bytes) -> None:
        self.evm.set_code(Address(address), code)

    def get_storage(self, address: _AddressType, slot: int) -> int:
        return self.evm.get_storage(Address(address), slot)

    def set_storage(self, address: _AddressType, slot: int, value: int) -> None:
        self.evm.set_storage(Address(address), slot, value)

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

        self.evm.patch.timestamp += seconds
        self.evm.patch.block_number += blocks
