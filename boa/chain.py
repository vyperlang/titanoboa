# an Environment which interacts with a real (prod or test) chain
import time
from functools import cached_property

from boa.environment import Env
from boa.rpc import EthereumRPC, RPCError


def _computation_from_trace(trace):
    computation = lambda: None  # noqa: E731

    # per debug_traceTransaction. construct a fake computation.
    # hardhat just gives structLogs no matter what tracer you give it
    if "structLogs" in trace:
        returndata = trace["returnValue"]
    else:
        returndata = trace.get("output")

    computation.output = bytes.fromhex(returndata).strip("0x")

    return computation


class ChainEnv(Env):
    def __init__(self, rpc_url):
        self._rpc = EthereumRPC(rpc_url)

    @property
    def vm(self):
        raise RuntimeError("VM is not available in prod")

    def execute_code(self, to_address, sender=None, gas=None, value=0, data=b""):
        _, trace = self._tx_helper(
            from_=sender, to=to_address, value=value, gas=gas, data=data
        )

    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b""):
        sender = self.eoa if sender is None else sender
        _, trace = self._tx_helper(from_=sender, value=value, gas=gas, data=bytecode)
        return _computation_from_trace(trace)

    def _wait_for_tx_trace(self, tx_hash, timeout=60, poll_latency=0.25):
        start = time.time()
        while True:
            trace = self._rpc.fetch_single("debug_traceTransaction", [tx_hash])
            if trace is not None:
                break
            if time.time() + poll_latency > start + timeout:
                raise ValueError(f"Timed out waiting for ({tx_hash})")
            time.sleep(poll_latency)
        return trace

    @cached_property
    def _tracer(self):
        try:
            txn_hash = "0x" + "00" * 32
            # alchemy only can do callTracer, plus it has lowest
            # overhead.
            tracer = {"tracer": "callTracer", "onlyTopCall": True}
            self._rpc_helper("debug_traceTransaction", [txn_hash, tracer])
        except RPCError as e:
            if e.code == -32601:
                return None
        return tracer

    def _tx_helper(self, from_, to=None, gas=None, value=None, data=None):
        tx_data = {"from": from_, "to": to, "gas": gas, "value": value, "data": data}
        tx_data = {k: v for (k, v) in tx_data.items() if bool(v)}

        if from_ not in self._accounts:
            raise ValueError(f"Account not available: {from_}")

        signed = self._accounts[from_].sign_transaction(tx_data)

        tx_hash = self._rpc.fetch_single(
            "eth_sendRawTransaction", [signed.rawTransaction]
        )

        trace = self._wait_for_tx_trace(tx_hash)

        trace = self._rpc.fetch_single(
            "debug_traceTransaction", [tx_hash, self._tracer]
        )

        return tx_hash, trace
