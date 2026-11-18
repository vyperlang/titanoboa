import pytest

from boa.network import NetworkEnv
from boa.rpc import RPCError


def probe_tracer(error):
    env = NetworkEnv.__new__(NetworkEnv)

    class FakeRPC:
        def fetch(self, method, params):
            assert method == "debug_traceTransaction"
            assert params[0] == "0x" + "00" * 32
            raise error

    env._rpc = FakeRPC()
    return env._tracer


@pytest.mark.parametrize("code", [-32000, 3])
def test_missing_probe_transaction_does_not_disable_tracing(code):
    tracer = probe_tracer(RPCError("transaction not found", code))
    assert tracer == {"tracer": "callTracer", "onlyTopCall": True}


def test_reverted_probe_does_not_enable_tracing():
    with pytest.warns(UserWarning, match="debug_traceTransaction not available"):
        assert probe_tracer(RPCError("execution reverted", 3)) is None
