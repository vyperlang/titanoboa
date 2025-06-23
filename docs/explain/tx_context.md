# Transaction Context

## Overview

Transaction context refers to the execution environment during contract calls, including sender addresses, gas limits, and block information. Titanoboa's handling of transaction context differs from mainnet Ethereum in important ways.

## Current Limitations

### No True Transaction Boundaries

In Titanoboa, contract calls execute sequentially within the same Python process rather than as separate blockchain transactions. This means:

- No transaction hash generation
- No transaction receipts in the traditional sense
- State changes are immediate and don't require mining
- Reverts only affect the current call, not a full transaction
- Transient storage persists throughout the Python session (since there's only one "transaction")

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
boa.env.vm.patch.timestamp = 1234567890

# Set block number
boa.env.vm.patch.block_number = 15000000

# Access in contract
contract.get_block_timestamp()  # returns 1234567890
```

## Best Practices

1. **Testing**: Be aware that gas costs in tests may differ from mainnet
2. **Transient Storage**: Remember that transient storage persists throughout your session
3. **Block variables**: Explicitly set block context when testing time-dependent logic
4. **Gas Profiling**: Use `pytest --gas-profile` for automatic gas profiling in tests
