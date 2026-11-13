from boa.network import NetworkEnv
from boa.rpc import RPCError


def test_missing_probe_transaction_does_not_disable_tracing():
    env = NetworkEnv.__new__(NetworkEnv)

    class FakeRPC:
        def fetch(self, method, params):
            assert method == "debug_traceTransaction"
            assert params[0] == "0x" + "00" * 32
            raise RPCError("transaction not found", -32000)

    env._rpc = FakeRPC()
    assert env._tracer == {"tracer": "callTracer", "onlyTopCall": True}
