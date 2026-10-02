# Transaction Context

## Overview

Transaction context includes sender/origin addresses, gas limits, value, and block information. The local py-evm `Env` and live `NetworkEnv` have different lifecycles.

## Current Limitations

### Local execution

Calls in the default local `Env` execute synchronously without mining. This means:

- No transaction hash generation
- No transaction receipts in the traditional sense
- State changes are immediate and don't require mining
- A reverting top-level call rolls back that call's state
- `simulate=True` snapshots and restores state even when execution succeeds

`NetworkEnv` differs: it simulates mutable calls locally, then signs, broadcasts, and waits for a receipt. View calls and explicit `simulate=True` calls use `eth_call`.

### Sender and origin

`boa.env.eoa` is the default sender. A method's `sender=` argument overrides it for that call, while `with boa.env.sender(address):` (or its alias `prank`) changes the default within a scope.

For local top-level calls and deployments, Titanoboa currently sets `tx.origin` equal to the selected sender. Origin cannot be configured independently. Internal contract-to-contract calls still change `msg.sender` according to EVM rules while retaining the top-level origin.

In `NetworkEnv`, a mutable call's sender must be registered with `add_account`; choosing an arbitrary local address is not enough to sign a live transaction.

### Gas Profiling Considerations

Since Titanoboa doesn't enforce true transaction boundaries, gas profiling may not perfectly match mainnet behavior:

- Cross-contract calls don't incur the full transaction overhead
- Storage refunds work differently than in real transactions
- Cold/warm storage access patterns may differ

## Gas Metering Classes

Titanoboa provides three gas meter implementations:

### `GasMeter` (Default)
The standard py-evm gas meter that tracks gas consumption according to EVM rules.

```python
# This is the default - no configuration needed
```

### `NoGasMeter`
Disables gas tracking entirely for approximately 10% performance improvement.

```python
from boa.vm.gas_meters import NoGasMeter
boa.env.set_gas_meter_class(NoGasMeter)
```

### `ProfilingGasMeter`
Tracks gas usage per program counter for detailed analysis. This is automatically enabled when using pytest with the `--gas-profile` flag.

```python
# Automatically enabled with:
# pytest --gas-profile

# Or manually enable:
from boa.vm.gas_meters import ProfilingGasMeter
boa.env.set_gas_meter_class(ProfilingGasMeter)
```

## Working with Block Context

Block variables are accessible but controlled by the environment:

```python
# Set block timestamp
boa.env.timestamp = 1234567890

# Set block number
boa.env.evm.patch.block_number = 15000000

# Access in contract
contract.get_block_timestamp()  # returns 1234567890
```

## Best Practices

1. **Testing**: Be aware that gas costs in tests may differ from mainnet
2. **Sender/origin**: Do not use local tests to model a top-level sender and a different `tx.origin`
3. **Block variables**: Prefer `boa.env.time_travel(...)` or documented environment properties when testing time-dependent logic
4. **Gas Profiling**: Use `pytest --gas-profile` for automatic gas profiling in tests
