# Performance Optimization Guide

Titanoboa provides several features to optimize performance during development and testing. This guide covers techniques to speed up your workflow.

## Compilation Caching

Titanoboa automatically caches compiled contracts to disk, significantly speeding up repeated compilations.

### How It Works

- Contracts are cached based on their content hash
- Cache includes compiler output and metadata
- Cache is automatically managed with TTL (time-to-live)

### Configuring the Cache

```python
import boa

# Set custom cache directory
boa.set_cache_dir("~/.my_boa_cache")

# Disable caching (not recommended for normal use)
boa.disable_cache()
```

### Cache Performance Impact

```python
import time
import boa

# First compilation - slow
start = time.time()
contract1 = boa.load("LargeContract.vy")
print(f"First load: {time.time() - start:.2f}s")  # e.g., 5.23s

# Second compilation - fast (from cache)
start = time.time()
contract2 = boa.load("LargeContract.vy")
print(f"Cached load: {time.time() - start:.2f}s")  # e.g., 0.05s
```

## Fast Mode

Fast mode uses emulation to skip EVM execution for maximum speed during interactive development. **Warning**: Fast mode is less accurate than normal mode and should NOT be used in CI/CD or production testing.

### Enabling Fast Mode

```python
import boa

# Enable fast mode for interactive development
boa.env.enable_fast_mode()

# Or create an environment with fast mode
from boa import Env
env = Env(fast_mode_enabled=True)
```

### What Fast Mode Does

- Uses Python emulation instead of EVM execution
- Skips gas calculations
- May produce different results than actual EVM
- Significantly faster for interactive testing

### When to Use Fast Mode

✅ **Good for:**
- Interactive development (REPL, Jupyter notebooks)
- Rapid prototyping
- Quick smoke tests during development

❌ **Never use for:**
- CI/CD pipelines
- Production testing
- Gas optimization work
- Security testing
- Any test that needs to match on-chain behavior

### Example: Interactive Development

```python
# development_session.py
import boa

# Enable fast mode for quick iteration
boa.env.enable_fast_mode()

# Rapid testing during development
contract = boa.load("MyContract.vy")
for i in range(1000):
    result = contract.calculate(i)
    print(f"Result {i}: {result}")
```

## Gas Metering Optimization

Control gas metering behavior for different testing scenarios.

### Disable Gas Metering

For tests where gas costs aren't relevant:

```python
import boa

# Disable gas metering completely
boa.env.disable_gas_metering()

# Run tests without gas overhead
contract = boa.load("MyContract.vy")
for i in range(10000):
    contract.process_transaction(i)  # No gas tracking
```

### Custom Gas Meters

```python
from boa.vm.gas_meters import GasMeter, NoGasMeter

# Temporarily disable gas metering
with boa.env.gas_meter_class(NoGasMeter):
    # Operations here have no gas overhead
    contract.expensive_operation()

# Gas metering resumes here
```

## Network Mode Optimization

When working with forked networks, optimize RPC calls and caching.

### Transaction Settings

```python
import boa

# Adjust timeouts for your network conditions
boa.env.tx_settings.poll_timeout = 60.0  # Reduce if network is fast

# Gas estimation settings
boa.env.tx_settings.base_fee_estimator_constant = 3  # Estimate base fee 3 blocks ahead (reduce for stable networks)
```

### Fork Caching

When forking, TitanoBoa caches remote state locally:

```python
import boa

# Fork with optimal block
boa.fork("https://eth-mainnet.g.alchemy.com/v2/KEY", block_identifier="safe")

# Repeated calls to same addresses are cached
usdc = boa.from_etherscan("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
# First call: fetches from network
balance1 = usdc.balanceOf(user)  
# Second call: uses cached state
balance2 = usdc.balanceOf(user)  # Much faster
```

## Testing Patterns

### Pytest Auto-Anchoring

The TitanoBoa pytest plugin automatically wraps each test in an `anchor()` context, providing automatic isolation:

```python
# test_contract.py
import boa
import pytest

# No need to manually use anchor() - pytest plugin handles it
def test_state_isolation():
    contract = boa.load("Stateful.vy")
    contract.set_value(42)
    assert contract.get_value() == 42
    # State automatically reverts after test

def test_next_test_has_clean_state():
    contract = boa.load("Stateful.vy")
    assert contract.get_value() == 0  # Clean state
```

### Disabling Auto-Anchoring

For special cases where you need to preserve state between tests:

```python
@pytest.mark.ignore_isolation
def test_without_isolation():
    # This test won't be wrapped in anchor()
    contract = boa.load("Persistent.vy")
    contract.increment()
    # State persists to next test marked with ignore_isolation
```

### Manual Anchoring for Sub-Tests

Even though pytest provides automatic anchoring, you can still use manual anchoring for sub-test isolation:

```python
def test_multiple_scenarios():
    contract = boa.load("Complex.vy")
    
    scenarios = [
        {"input": 10, "expected": 100},
        {"input": 20, "expected": 400},
        {"input": 30, "expected": 900},
    ]
    
    for scenario in scenarios:
        with boa.env.anchor():
            # Each scenario gets its own isolated state
            contract.set_multiplier(scenario["input"])
            result = contract.calculate()
            assert result == scenario["expected"]
```

## When to Clear Caches

### Compilation Cache

Clear the compilation cache when:

1. **Vyper compiler version changes**
```python
# After updating Vyper
import shutil
import boa
shutil.rmtree(boa.interpret._disk_cache.cache_dir)
```

2. **Debugging compilation issues**
```python
# Temporarily disable to ensure fresh compilation
boa.disable_cache()
# Debug your issue
# Re-enable when done
```

3. **Cache corruption (rare)**
```python
# If you see serialization errors
try:
    contract = boa.load("MyContract.vy")
except Exception as e:
    if "pickle" in str(e) or "cache" in str(e):
        shutil.rmtree(boa.interpret._disk_cache.cache_dir)
        contract = boa.load("MyContract.vy")  # Retry
```

## Best Practices

### 1. **Use Fast Mode Only for Interactive Development**
```python
# In your development REPL or notebook
import boa
boa.env.enable_fast_mode()  # OK for interactive use

# In your test files - NO fast mode
def test_critical_function():
    # Tests run in accurate mode by default
    contract = boa.load("Critical.vy")
    # Test with full EVM accuracy
```

### 2. **Profile Before Optimizing**
```python
# Use pytest's gas profiling
pytest tests/ --gas-profile

# Or mark specific tests
@pytest.mark.gas_profile
def test_expensive_operation():
    contract = boa.load("Expensive.vy")
    contract.complex_calculation()
```

### 3. **Choose Appropriate Gas Metering**
```python
# For functional tests (no gas needed)
@pytest.fixture(autouse=True)
def no_gas():
    with boa.env.gas_meter_class(NoGasMeter):
        yield

# For gas optimization work
@pytest.mark.gas_profile
def test_gas_usage():
    # Automatic gas profiling
    contract.expensive_operation()
```

### 4. **Batch Operations**
```python
# Inefficient: Multiple separate operations
for user in users:
    contract.add_user(user)

# Efficient: Single batched operation
contract.add_users(users)
```

## Performance Comparison

Here's a typical performance improvement with optimizations:

| Operation | Normal Mode | With Optimizations | Fast Mode (Dev Only) |
|-----------|-------------|-------------------|---------------------|
| Compilation (cached) | 5.2s | 0.05s | 0.05s |
| 1000 simple calls | 12.3s | 8.1s (no gas) | 0.3s |
| Fork state queries | 2.1s | 0.3s (cached) | 0.3s |
| Test suite (100 tests) | 45s | 28s | 5s |

## CI/CD Best Practices

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      
      - name: Cache Vyper compilations
        uses: actions/cache@v3
        with:
          path: ~/.cache/titanoboa
          key: ${{ runner.os }}-vyper-${{ hashFiles('**/*.vy') }}
      
      - name: Install dependencies
        run: |
          pip install -e ".[test]"
      
      - name: Run tests (accurate mode)
        run: |
          # Tests run in accurate mode by default
          # DO NOT enable fast mode in CI!
          pytest tests/ -v
        env:
          # Set consistent cache location
          BOA_CACHE_DIR: ~/.cache/titanoboa
```

## Troubleshooting

### Slow Compilation

```python
# Check if caching is working
import boa
print(f"Cache dir: {boa.interpret._disk_cache.cache_dir}")
print(f"Cache enabled: {boa.interpret._disk_cache is not None}")

# Time compilation
import time
start = time.time()
contract = boa.load("MyContract.vy")
print(f"Compilation time: {time.time() - start:.2f}s")
```

### Memory Issues

For test suites with many contracts:

```python
import gc
import pytest

@pytest.fixture(autouse=True)
def cleanup():
    yield
    # Force garbage collection after each test
    gc.collect()
    
    # Reset gas profiling data if needed
    if hasattr(boa.env, "_gas_profile_state"):
        boa.env.reset_gas_used()
```

### Network Mode Performance

```python
# Check RPC latency
import time
import boa

# Time a simple RPC call
start = time.time()
balance = boa.env.get_balance("0x0000000000000000000000000000000000000000")
print(f"RPC latency: {(time.time() - start) * 1000:.0f}ms")

# For slow networks, increase timeouts
boa.env.tx_settings.poll_timeout = 300.0  # 5 minutes
```