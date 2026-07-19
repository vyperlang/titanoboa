# Runtime diagnostics

## `enable_pyevm_verbose_logging`

!!! function "`boa.enable_pyevm_verbose_logging()`"

    Enable py-evm's `DEBUG2` computation logger for opcode-level execution
    diagnostics.

    ```python
    import boa

    boa.enable_pyevm_verbose_logging()
    contract = boa.loads(
        """
@external
@pure
def add(a: uint256, b: uint256) -> uint256:
    return a + b
"""
    )
    contract.add(1, 2)
    ```

    This configures Python's root logging if it has not already been
    configured, installs the custom `DEBUG2` level, and sets
    `eth.vm.computation.Computation` to that level. It is process-wide and can
    produce a large amount of output, so enable it only while diagnosing
    local py-evm execution. It does not provide opcode logs for transactions
    executed by a live `NetworkEnv` node.

For source-oriented failures, prefer Titanoboa's contract traceback and
[call-trace](common_classes/call_trace.md) APIs. For aggregate gas analysis,
use the [gas profiling guide](../guides/testing/gas_profiling.md).
