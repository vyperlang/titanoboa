# an Environment which interacts with a real (prod or test) chain
import contextlib
import warnings
from dataclasses import dataclass
from functools import cached_property
from math import ceil

from eth_account import Account
from requests.exceptions import HTTPError

from boa.environment import Env
from boa.rpc import (
    RPC,
    EthereumRPC,
    RPCError,
    fixup_dict,
    to_bytes,
    to_hex,
    to_int,
    trim_dict,
)
from boa.util.abi import Address


class TraceObject:
    def __init__(self, raw_trace):
        self.raw_trace = raw_trace

    @cached_property
    def returndata(self):
        # per debug_traceTransaction, construct a fake computation.
        # hardhat/anvil only give structLogs, alchemy only gives callTracer.
        if "structLogs" in self.raw_trace:
            return self.raw_trace["returnValue"]
        else:
            return self.raw_trace.get("output", "0x")

    @cached_property
    def returndata_bytes(self):
        return to_bytes(self.returndata)

    @cached_property
    def is_error(self):
        if "structLogs" in self.raw_trace:
            return self.raw_trace["failed"]
        else:
            return "error" in self.raw_trace


class _EstimateGasFailed(Exception):
    pass


@dataclass
class TransactionSettings:
    # when calculating the base fee, the number of blocks N ahead
    # to compute a cap for the Nth block.
    # defaults to 4 (4 blocks ahead, pending block's baseFee * ~1.6)
    # but can be tweaked. if you get errors like
    # `boa.rpc.RPCError: -32000: err: max fee per gas less than block base fee`
    # try increasing the constant.
    # do not recommend setting below 0.
    base_fee_estimator_constant: int = 4

    # amount of time to wait, in seconds before giving up on a transaction
    poll_timeout: float = 240.0


@dataclass
class ExternalAccount:
    address: Address
    _rpc: EthereumRPC

    def __post_init__(self):
        self.address = Address(self.address)

    def send_transaction(self, tx_data):
        txhash = self._rpc.fetch("eth_sendTransaction", [tx_data])
        # format to be the same as what BrowserSigner returns
        return {"hash": txhash}


class NetworkEnv(Env):
    """
    An Env object which can be swapped in via `boa.set_env()`.
    It runs non-mutable (view or pure) functions via eth_call,
    mutable functions and contract creation via eth_sendRawTransaction.
    """

    # always prefetch state in network mode
    _fork_try_prefetch_state = True

    def __init__(self, rpc: str | RPC, accounts: dict[str, Account] = None):
        super().__init__()

        if isinstance(rpc, str):
            warnings.warn(
                "NetworkEnv(url) is deprecated. Use boa.set_network_env(url) instead.",
                stacklevel=2,
            )
            rpc = EthereumRPC(rpc)

        self._rpc = rpc

        self._reset_fork()

        self._accounts = accounts or {}

        self.eoa = None

        self._gas_price = None

        self.tx_settings = TransactionSettings()

    @cached_property
    def _rpc_has_snapshot(self):
        try:
            snapshot_id = self._rpc.fetch("evm_snapshot", [])
            self._rpc.fetch("evm_revert", [snapshot_id])
            return True
        except RPCError:
            return False

    # OVERRIDES
    @contextlib.contextmanager
    def anchor(self):
        if not self._rpc_has_snapshot:
            raise RuntimeError("RPC does not have `evm_snapshot` capability!")
        try:
            blkid = self.vm.state._account_db._block_id
            snapshot_id = self._rpc.fetch("evm_snapshot", [])
            yield
            # note we cannot call super.anchor() because vm/accountdb fork
            # state is reset after every txn.
        finally:
            self._rpc.fetch("evm_revert", [snapshot_id])
            # wipe forked state
            self._reset_fork(blkid)

    # add account, or "Account-like" object. MUST expose
    # `sign_transaction` or `send_transaction` method!
    def add_account(self, account: Account, force_eoa=False):
        self._accounts[account.address] = account  # type: ignore
        if self.eoa is None or force_eoa:
            self.eoa = account.address  # type: ignore

    def add_accounts_from_rpc(self, rpc: str | EthereumRPC) -> None:
        if isinstance(rpc, str):
            rpc = EthereumRPC(rpc)

        # address strings, ex. ["0x0e5437b1b3448d22c07caed31e5bcdc4ec5284a9"]
        addresses = rpc.fetch("eth_accounts", [])
        if not addresses:
            # strip out content in the URL which might not want to get into logs
            warnings.warn(f"No accounts fetched from <{rpc.name}>!", stacklevel=2)
        for address in addresses:
            self.add_account(ExternalAccount(_rpc=rpc, address=address))  # type: ignore

    def set_eoa(self, eoa: Account) -> None:
        self.add_account(eoa, force_eoa=True)

    @classmethod
    def from_url(cls, url: str) -> "NetworkEnv":
        return cls(EthereumRPC(url))

    # overrides
    def get_gas_price(self) -> int:
        if self._gas_price is not None:
            return self._gas_price
        return to_int(self._rpc.fetch("eth_gasPrice", []))

    def get_eip1559_fee(self) -> tuple[str, str, str, str]:
        # returns: base_fee, max_fee, max_priority_fee
        reqs = [
            ("eth_getBlockByNumber", ["pending", False]),
            ("eth_maxPriorityFeePerGas", []),
            ("eth_chainId", []),
        ]
        block_info, max_priority_fee, chain_id = self._rpc.fetch_multi(reqs)
        base_fee = block_info["baseFeePerGas"]

        # Each block increases the base fee by 1/8 at most.
        # here we have the next block's base fee, compute a cap for the
        # next N blocks here.
        blocks_ahead = self.tx_settings.base_fee_estimator_constant
        base_fee_estimate = ceil(to_int(base_fee) * (9 / 8) ** blocks_ahead)

        max_fee = to_hex(base_fee_estimate + to_int(max_priority_fee))
        return to_hex(base_fee_estimate), max_priority_fee, max_fee, chain_id

    def get_static_fee(self) -> tuple[str, str]:
        # non eip-1559 transaction
        return tuple(self._rpc.fetch_multi([("eth_gasPrice", []), ("eth_chainId", [])]))

    def _check_sender(self, address):
        if address is None:
            raise ValueError("No sender!")
        return Address(address)

    # OVERRIDES
    def execute_code(
        self,
        to_address,
        sender=None,
        gas=None,
        value=0,
        data=b"",
        override_bytecode=None,
        contract=None,
        is_modifying=True,
        ir_executor=None,  # maybe just have **kwargs to collect extra kwargs
    ):
        # call execute_code for tracing side effects
        # note: we could get a perf improvement if we ran this in
        # the background while waiting on RPC network calls
        computation = super().execute_code(
            to_address=to_address,
            sender=sender,
            gas=gas,
            value=value,
            data=data,
            is_modifying=is_modifying,
            contract=contract,
        )

        sender = self._check_sender(self._get_sender(sender))

        hexdata = to_hex(data)

        if is_modifying:
            try:
                receipt, trace = self._send_txn(
                    from_=sender, to=to_address, value=value, gas=gas, data=hexdata
                )
            except _EstimateGasFailed:
                # no need to actually run the txn.
                # caller will decide what to do with the error - probably revert

                # if not computation.is_error, either a bug in boa
                # or out of sync with node.
                assert computation.is_error
                return computation

            output = None
            if trace is not None:
                output = trace.returndata_bytes
                # gas_used = to_int(receipt["gasUsed"])

                # the node reverted but we didn't. consider this an
                # unrecoverable error and bail out
                if trace.is_error and not computation.is_error:
                    raise RuntimeError(
                        f"panic: local computation succeeded but node didnt: {trace}"
                    )

        else:
            args = fixup_dict(
                {
                    "from": sender,
                    "to": to_address,
                    "gas": gas,
                    "value": value,
                    "data": hexdata,
                }
            )
            returnvalue = self._rpc.fetch("eth_call", [args, "latest"])
            output = to_bytes(returnvalue)
            # we don't need to do the check for computation.is_error
            # because if the eth_call failed it would have just raised
            # an actual RPC error

        # returndata not the same. this means either a bug in
        # titanoboa/py-evm or more likely, state got out of sync.
        # not the greatest, but we will just patch the returndata and
        # pretend nothing happened (which is not really a problem unless
        # the caller wants to inspect the trace or memory).
        if output is not None and computation.output != output:
            warnings.warn(
                "local fork did not match node! this indicates state got out "
                "of sync with the network or a bug in titanoboa!",
                stacklevel=2,
            )
            # just return whatever the node had.
            computation.output = output

        return computation

    # OVERRIDES
    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b"", **kwargs):
        local_address, local_bytecode = super().deploy_code(
            sender=sender, gas=gas, value=value, bytecode=bytecode
        )
        if trim_dict(kwargs):
            raise TypeError(f"invalid kwargs to execute_code: {kwargs}")
        bytecode = to_hex(bytecode)
        sender = self._check_sender(self._get_sender(sender))

        receipt, trace = self._send_txn(
            from_=sender, value=value, gas=gas, data=bytecode
        )

        create_address = Address(receipt["contractAddress"])

        deployed_bytecode = local_bytecode

        if trace is not None and local_bytecode != trace.returndata_bytes:
            # not sure what to do about this, for now just complain
            warnings.warn(
                "local fork did not match node! this indicates state got out "
                "of sync with the network or a bug in titanoboa!",
                stacklevel=2,
            )
            # return what the node returned anyway
            deployed_bytecode = trace.returndata_bytes

        if local_address != create_address:
            raise RuntimeError(f"uh oh! {local_address} != {create_address}")

        # TODO get contract info in here
        print(f"contract deployed at {create_address}")

        return create_address, deployed_bytecode

    @cached_property
    def _tracer(self):
        def _warn_no_tracer():
            warnings.warn(
                "debug_traceTransaction not available! "
                "titanoboa will try hard to interact with the network, but "
                "this means that titanoboa is not able to do certain "
                "safety checks at runtime. it is recommended to switch "
                "to a node or provider with debug_traceTransaction.",
                stacklevel=3,
            )

        try:
            txn_hash = "0x" + "00" * 32
            # alchemy only can do callTracer, plus it has lowest
            # overhead.
            call_tracer = {"tracer": "callTracer", "onlyTopCall": True}
            self._rpc.fetch("debug_traceTransaction", [txn_hash, call_tracer])

        except RPCError as e:
            # can't handle callTracer, use default (i.e. structLogs)
            if e.code == -32602:
                return {}

            # catchall - just don't have a tracer
            # note on error codes:
            # -32600 is alchemy unpaid tier error message
            # -32601 is infura error message (if i recall correctly)
            _warn_no_tracer()
            return None

        except HTTPError:
            _warn_no_tracer()
            return None

        return call_tracer

    def _get_nonce(self, addr):
        return self._rpc.fetch("eth_getTransactionCount", [addr, "latest"])

    def _reset_fork(self, block_identifier="latest"):
        # use "latest" to make sure we are forking with up-to-date state
        # but use reset_traces=False to help with storage dumps
        self.fork_rpc(
            self._rpc,
            reset_traces=False,
            block_identifier=block_identifier,
            cache_file=None,
        )
        self.vm.state._account_db._rpc._init_mem_db()

    def _send_txn(self, from_, to=None, gas=None, value=None, data=None):
        tx_data = fixup_dict(
            {"from": from_, "to": to, "gas": gas, "value": value, "data": data}
        )

        try:
            # eip-1559 txn
            (base_fee, max_priority_fee, max_fee, chain_id) = self.get_eip1559_fee()
            tx_data["maxPriorityFeePerGas"] = max_priority_fee
            tx_data["maxFeePerGas"] = max_fee
            tx_data["chainId"] = chain_id
        except (RPCError, KeyError):
            gas_price, chain_id = self.get_static_fee()
            tx_data["gasPrice"] = gas_price
            tx_data["chainId"] = chain_id

        tx_data["nonce"] = self._get_nonce(from_)

        if gas is None:
            try:
                tx_data["gas"] = self._rpc.fetch("eth_estimateGas", [tx_data])
            except RPCError as e:
                if e.code == 3:
                    # execution failed at estimateGas, probably the txn reverted
                    raise _EstimateGasFailed()
                raise e from e

        if from_ not in self._accounts:
            raise ValueError(f"Account not available: {from_}")
        account = self._accounts[from_]

        if hasattr(account, "sign_transaction"):
            signed = account.sign_transaction(tx_data)

            # note: signed.rawTransaction has type HexBytes
            tx_hash = self._rpc.fetch(
                "eth_sendRawTransaction", [to_hex(bytes(signed.rawTransaction))]
            )
        else:
            # some providers (i.e. metamask) don't have sign_transaction
            # we just have to call send_transaction and pray for the best
            tx_hash = account.send_transaction(tx_data)["hash"]

        # TODO real logging
        print(f"tx broadcasted: {tx_hash}")

        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)

        trace = None
        if self._tracer is not None:
            trace = self._rpc.fetch_uncached(
                "debug_traceTransaction", [tx_hash, self._tracer]
            )

        print(f"{tx_hash} mined in block {receipt['blockHash']}!")

        # the block was mined, reset state
        self._reset_fork(block_identifier=receipt["blockNumber"])

        t_obj = TraceObject(trace) if trace is not None else None
        return receipt, t_obj
