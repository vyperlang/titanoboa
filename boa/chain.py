# an Environment which interacts with a real (prod or test) chain
import time
import warnings
from functools import cached_property

from eth_account import Account
from eth_utils import to_canonical_address

from boa.environment import Env
from boa.rpc import EthereumRPC, RPCError, to_hex, to_int


class TraceObject:
    def __init__(self, raw_trace):
        self.raw_trace = raw_trace

    @cached_property
    def returndata(self):
        # per debug_traceTransaction, construct a fake computation.
        # hardhat/anvil only give structLogs, alchemy only gives callTracer.
        if "structLogs" in self.raw_trace:
            returndata = self.raw_trace["returnValue"]
        else:
            returndata = self.raw_trace.get("output")

        return returndata

    @cached_property
    def returndata_bytes(self):
        return bytes.fromhex(self.returndata.removeprefix("0x"))


def trim_dict(kv):
    return {k: v for (k, v) in kv.items() if bool(v)}


def _fixup_dict(kv):
    return {k: to_hex(v) for (k, v) in trim_dict(kv).items()}


class ChainEnv(Env):
    def __init__(self, rpc_url, accounts = None):
        super().__init__()

        self._reset_fork()

        self._rpc = EthereumRPC(rpc_url)

        self._accounts: dict[str, Account] = accounts or {}

        self.eoa = next(iter(self._accounts.keys()))

        self._gas_price = None

    def add_account(self, account: Account):
        self._accounts[account.address] = account

    # overrides
    def get_gas_price(self):
        if self._gas_price is not None:
            return self._gas_price
        return to_int(self._rpc.fetch_single("eth_gasPrice", []))

    def hex_gas_price(self):
        return to_hex(self.get_gas_price())

    # @property
    # def vm(self):
    #    raise RuntimeError("VM is not available in prod")

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
    ):
        # call execute_code for tracing side effects
        computation = super().execute_code(
            to_address=to_address,
            sender=sender,
            gas=gas,
            value=value,
            data=data,
            is_modifying=is_modifying,
            contract=contract,
        )

        sender = self.eoa if sender is None else sender

        data = to_hex(data)

        if is_modifying:
            receipt, trace = self._send_txn(
                from_=sender, to=to_address, value=value, gas=gas, data=data
            )
            # gas_used = to_int(receipt["gasUsed"])

        else:
            args = _fixup_dict(
                {
                    "from": sender,
                    "to": to_address,
                    "gas": gas,
                    "value": value,
                    "data": data,
                }
            )
            returnvalue = self._rpc.fetch_single("eth_call", [args, "latest"])
            # gas_used = to_int(self._rpc.fetch_single("eth_estimateGas", [args, "latest"]))

        if computation.output != bytes.fromhex(returnvalue.removeprefix("0x")):
            # not sure what to do about this, for now just complain
            warnings.warn(
                "local fork did not match node! this likely indicates a bug in titanoboa!",
                stacklevel=2,
            )

        return computation

    # OVERRIDES
    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b"", **kwargs):
        local_address, local_bytecode = super().deploy_code(
            sender=sender, gas=gas, value=value, bytecode=bytecode
        )
        if trim_dict(kwargs):
            raise TypeError(f"invalid kwargs to execute_code: {kwargs}")
        sender = self.eoa if sender is None else sender
        bytecode = to_hex(bytecode)

        receipt, trace = self._send_txn(
            from_=sender, value=value, gas=gas, data=bytecode
        )
        create_address = to_canonical_address(receipt["contractAddress"])

        if local_bytecode != trace.returndata_bytes:
            # not sure what to do about this, for now just complain
            warnings.warn(
                "local fork did not match node! this likely indicates a bug in titanoboa!",
                stacklevel=2,
            )
        if local_address != create_address:
            raise RuntimeError(f"uh oh! {local_address} != {create_address}")

        return create_address, trace.returndata_bytes

    def _wait_for_tx_trace(self, tx_hash, timeout=60, poll_latency=0.25):
        start = time.time()
        while True:
            receipt = self._rpc.fetch_single("eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                break
            if time.time() + poll_latency > start + timeout:
                raise ValueError(f"Timed out waiting for ({tx_hash})")
            time.sleep(poll_latency)
        trace = self._rpc.fetch_single(
            "debug_traceTransaction", [tx_hash, self._tracer]
        )
        return receipt, trace

    @cached_property
    def _tracer(self):
        try:
            txn_hash = "0x" + "00" * 32
            # alchemy only can do callTracer, plus it has lowest
            # overhead.
            call_tracer = {"tracer": "callTracer", "onlyTopCall": True}
            self._rpc.fetch_single("debug_traceTransaction", [txn_hash, call_tracer])
        except RPCError as e:
            if e.code == -32601:
                return None
            if e.code == -32602:
                return {}
        return call_tracer

    def _get_nonce(self, addr):
        return self._rpc.fetch_single("eth_getTransactionCount", [addr, "latest"])

    def _reset_fork(self, block_identifier="latest"):
        # use "latest" to make sure we are forking with up-to-date state
        super().fork(self._rpc._rpc_url, block_identifier)

    def _send_txn(self, from_, to=None, gas=None, value=None, data=None):
        tx_data = _fixup_dict(
            {"from": from_, "to": to, "gas": gas, "value": value, "data": data}
        )
        tx_data["gasPrice"] = self.hex_gas_price()
        tx_data["gas"] = self._rpc.fetch_single("eth_estimateGas", [tx_data])
        tx_data["nonce"] = self._get_nonce(from_)

        if from_ not in self._accounts:
            raise ValueError(f"Account not available: {from_}")

        signed = self._accounts[from_].sign_transaction(tx_data)

        # note: signed.rawTransaction has type HexBytes
        tx_hash = self._rpc.fetch_single(
            "eth_sendRawTransaction", [to_hex(bytes(signed.rawTransaction))]
        )

        receipt, trace = self._wait_for_tx_trace(tx_hash)

        # the block was mined, reset state
        self._reset_fork(block_identifier=receipt["blockNumber"])

        return receipt, TraceObject(trace)
