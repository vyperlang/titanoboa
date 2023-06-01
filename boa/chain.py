# an Environment which interacts with a real (prod or test) chain
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RPCError:
    code: int
    message: str

    @classmethod
    def from_json(cls, data):
        err = data["error"]
        return cls(code=err["code"], message=err["message"])

def _computation_from_struct_logs(trace):
    computation = lambda: None

    # per debug_traceTransaction. construct a fake computation.
    # res["structLogs"]["returnValue"]
    if "structLogs" in trace:
        returndata = trace["returnValue"]
    else:
        returndata = trace.get("output")

    computation.output = bytes.fromhex(returndata).strip("0x"))

    return computation


class Chain(Env):
    has_vm = False

    _supports_traces = None

    def __init__(self, rpc_url):
        self._rpc_url = rpc_url

    @cached_property
    def session(self):
        return requests.Session()

    @property
    def vm(self):
        raise RuntimeError("VM is not available in prod")

    def get_balance(self, account):
        return self.web3.eth.get_balance(account)

    def execute_code(
        self,
        to_address,
        sender=None,
        gas=None,
        value=0,
        data=b"",
    ):
        _, trace = self._tx_helper(
            from_=sender, to=to_address, value=value, gas=gas, data=data
        )

    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b""):
        sender = self.eoa if sender is None else sender
        _, trace = self._tx_helper(
            from_=sender,
            value=value,
            gas=gas,
            data=bytecode,
        )
        return _computation_from_trace(trace)

    def _wait_for_tx_trace(tx_hash, timeout = 60, poll_latency = 0.25):
        start = time.time()
        while True:
            trace = self._rpc_helper("debug_traceTransaction", [tx_hash])
            if trace is not None:
                break
            if time.time() + poll_latency > start + timeout:
                raise ValueError(f"Timed out waiting for ({tx_hash})")
            time.sleep(poll_latency)
        return trace

    def _rpc_helper(method, params, timeout = 60):
        req = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
        res = self._session.post(self._rpc_url, json=req, timeout=timeout)
        res.raise_for_status()
        ret = res.json()
        if "error" in ret:
            raise RPCError.from_json(ret)
        return ret["result"]

    @cached_property
    def _tracer(self):
        try:
            txn_hash = "0x" + "00" * 32
            tracer = {"tracer": "callTracer", "onlyTopCall": True}
            self._rpc_helper("debug_traceTransaction", [txn_hash, tracer])
        except RPCError as e:
            if e.code == -32601:
                return None
        return tracer



    def _tx_helper(self, from_, to=None, gas=None, value=None, data=None):
        tx_data = {"from": from_, "to": to, "gas": gas, "value": value, "data": data}
        tx_data = {k: v for (k, v) in tx_data.items() if bool(v)}

        if sender not in self._accounts:
            raise ValueError(f"Account not available: {self.eoa}")

        signed = self._accounts[eoa].sign_transaction(tx_data)

        tx_hash = self._rpc_helper("eth_sendRawTransaction", [signed.rawTransaction])

        trace = self._wait_for_tx_trace(tx_hash)

        # works with alchemy
        trace = self._rpc_helper("debug_traceTransaction", [tx_hash, self._tracer])

        return tx_hash, trace
