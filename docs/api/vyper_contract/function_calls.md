# Function Calls

## Overview

When calling functions on `VyperContract` instances, you can pass several special keyword arguments to control the execution context.

## Special Parameters

### `simulate=True`

The `simulate` parameter allows you to execute a function call without committing the state changes. The behavior differs between local and network environments:

- **Local environment (PyEVM)**: Uses `anchor()` internally to snapshot and revert state
- **Network mode**: Uses `eth_call` RPC method, which simulates the call without broadcasting a transaction

```python
import boa

contract = boa.loads("""
counter: public(uint256)

@external
def increment() -> uint256:
    self.counter += 1
    return self.counter
""")

# Normal call - state is modified
result = contract.increment()
assert result == 1
assert contract.counter() == 1

# Simulated call - state is NOT modified
result = contract.increment(simulate=True)
assert result == 2  # Would return 2 if executed
assert contract.counter() == 1  # But counter is still 1
```

### `simulate=True` vs `anchor()`

While both approaches prevent state changes, they have important differences:

#### `simulate=True`
- Works in both local and network modes
- In network mode, uses `eth_call` - no transaction is created
- Only affects the specific function call
- Returns the function result directly
- `boa.env.anchor()` may not be available in network mode
- More efficient in network mode (no state changes to revert)

```python
# Using simulate
result = contract.calculate_amount(100, simulate=True)
# State unchanged, result returned
```

#### `anchor()`
- Only works in local mode (PyEVM)
- Creates a snapshot of entire EVM state
- Can wrap multiple operations
- Reverts all state changes within the context

```python
# Using anchor
with boa.env.anchor():
    contract.increment()
    contract.increment()
    result = contract.counter()
    # All changes reverted when exiting context
# State unchanged
```

### Network Mode Behavior

In network mode, `simulate=True` is particularly useful because it:
1. Doesn't consume gas
2. Doesn't require a transaction to be mined
3. Provides instant results
4. Can be used to test transaction validity before execution
5. Can be used to simulate calling functions that are not marked view but without actually calling them

```python
# In network mode (e.g., after boa.set_network_env(...))
try:
    # This uses `eth_call` internally
    result = contract.expensive_operation(simulate=True)
    print(f"Operation would succeed with result: {result}")

except Exception as e:
    print(f"Operation would fail: {e}")

# Now execute it for real
actual_result = contract.expensive_operation()
```

### Other Parameters

- `value`: Amount of ETH to send with the transaction (in wei)
- `gas`: Gas limit for the transaction
- `sender`: Override the sender address for this call

```python
# Send ETH with a call
contract.deposit(value=10**18)  # Send 1 ETH

# Set gas limit
contract.expensive_operation(gas=500000)

# Override sender
contract.admin_function(sender="0x123...")
```

## Use Cases

### 1. Pre-flight Checks

```python
# Check if a transaction would succeed before executing
def safe_transfer(token, recipient, amount):
    try:
        # Simulate first
        success = token.transfer(recipient, amount, simulate=True)
        if success:
            # Execute for real
            return token.transfer(recipient, amount)
    except Exception as e:
        print(f"Transfer would fail: {e}")
        return False
```

### 2. Gas Estimation

```python
# Estimate gas using simulation (works in both local and network mode)
import boa

# The simulation still tracks gas usage
contract.complex_operation(simulate=True)
# In network mode, you can check the gas used from the eth_call
```

### 3. View Function Alternative

```python
# For functions that should be view but aren't marked as such
balance = contract.calculate_balance(user, simulate=True)
# No state change committed, even if function modifies state internally
```

## Important Notes

1. **External Calls**: When using `simulate=True`, all external calls made by the contract are also simulated
2. **Events**: Events are not emitted during simulated calls
3. **Reverts**: Simulated calls can still revert, which is useful for testing error conditions
4. **Gas**: In local mode, gas is still tracked; in network mode, gas limits still apply to the `eth_call`
