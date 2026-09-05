from math import ceil

import pytest

from boa.network import NetworkEnv, TransactionSettings


class FakeRPC:
    def __init__(self, base_fee, rpc_priority_fee, chain_id):
        self.base_fee = base_fee
        self.rpc_priority_fee = rpc_priority_fee
        self.chain_id = chain_id

    def fetch_multi(self, reqs):
        assert reqs == [
            ("eth_getBlockByNumber", ["latest", False]),
            ("eth_maxPriorityFeePerGas", []),
            ("eth_chainId", []),
        ]
        return [
            {"baseFeePerGas": hex(self.base_fee)},
            hex(self.rpc_priority_fee),
            hex(self.chain_id),
        ]


def network_env(base_fee=1000, rpc_priority_fee=7, chain_id=1):
    env = NetworkEnv.__new__(NetworkEnv)
    env._rpc = FakeRPC(base_fee, rpc_priority_fee, chain_id)
    env.tx_settings = TransactionSettings()
    return env


def expected_base_fee_estimate(base_fee, blocks_ahead):
    return ceil(base_fee * (9 / 8) ** blocks_ahead)


def test_eip1559_fee_uses_rpc_priority_fee_by_default():
    env = network_env(base_fee=1000, rpc_priority_fee=7, chain_id=5)

    base_fee, priority_fee, max_fee, chain_id = env.get_eip1559_fee()

    base_fee_estimate = expected_base_fee_estimate(
        1000, env.tx_settings.base_fee_estimator_constant
    )
    assert base_fee == hex(base_fee_estimate)
    assert priority_fee == hex(7)
    assert max_fee == hex(base_fee_estimate + 7)
    assert chain_id == hex(5)


def test_eip1559_fee_uses_priority_fee_strategy():
    env = network_env(base_fee=1000, rpc_priority_fee=7, chain_id=5)
    seen_context = None

    def priority_fee_strategy(context):
        nonlocal seen_context
        seen_context = context
        return context.base_fee // 20

    env.tx_settings.priority_fee_strategy = priority_fee_strategy

    _, priority_fee, max_fee, _ = env.get_eip1559_fee()

    base_fee_estimate = expected_base_fee_estimate(
        1000, env.tx_settings.base_fee_estimator_constant
    )
    assert priority_fee == hex(50)
    assert max_fee == hex(base_fee_estimate + 50)
    assert seen_context.base_fee == 1000
    assert seen_context.base_fee_estimate == base_fee_estimate
    assert seen_context.rpc_priority_fee == 7
    assert seen_context.chain_id == 5


@pytest.mark.parametrize("priority_fee", [-1, "0x1"])
def test_eip1559_fee_rejects_invalid_priority_fee_strategy_result(priority_fee):
    env = network_env()
    env.tx_settings.priority_fee_strategy = lambda context: priority_fee

    with pytest.raises(ValueError, match="priority_fee_strategy"):
        env.get_eip1559_fee()
