# Gas Profiling

Titanoboa provides comprehensive gas profiling tools that help you understand and optimize gas consumption in your contracts. The profiler tracks gas usage at both the function level and line-by-line, providing detailed statistics.

## Overview

When enabled, gas profiling:
- Tracks gas consumption for each contract call
- Provides line-by-line gas usage within functions
- Calculates statistical metrics (mean, median, standard deviation)
- Generates formatted tables for easy analysis

## Enabling Gas Profiling

### Method 1: Using pytest markers

Decorate specific tests with `@pytest.mark.gas_profile`:

```python
import pytest
import boa

@pytest.mark.gas_profile
def test_expensive_operation():
    contract = boa.load("MyContract.vy")
    contract.expensive_operation()
    # Gas profiling data will be collected for this test
```

### Method 2: Command-line flag

Run pytest with the `--gas-profile` flag to profile all tests:

```bash
pytest tests/unitary --gas-profile
```

When using `--gas-profile`, you can exclude specific tests:

```python
@pytest.mark.ignore_gas_profiling
def test_not_profiled():
    # This test won't be profiled even with --gas-profile
    pass
```

### Method 3: Programmatic control

Enable profiling within your code:

```python
import boa

# Enable gas profiling
boa.env.enable_gas_profiling()

# Your contract interactions here
contract = boa.load("MyContract.vy")
contract.some_function()

# Disable when done
boa.env.reset_gas_metering_behavior()
```

## Basic Example

```python
@pytest.mark.gas_profile
def test_profile():

    source_code = """
@external
@view
def foo(a: uint256 = 0):
    x: uint256 = a
"""
    contract = boa.loads(source_code, name="FooContract")
    contract.foo()
```

```
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┓
┃ Contract    ┃ Address                                    ┃ Computation ┃ Count ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
│ FooContract │ 0x0000000000000000000000000000000000000066 │ foo         │ 1     │ 88   │ 88     │ 0     │ 88  │ 88  │
└─────────────┴────────────────────────────────────────────┴─────────────┴───────┴──────┴────────┴───────┴─────┴─────┘


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ Contract                                             ┃ Computation                                                                ┃ Count ┃ Mean  ┃ Median ┃ Stdev ┃ Min   ┃ Max   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ Path:                                                │                                                                            │       │       │        │       │       │       │
│ Name: FooContract                                    │                                                                            │       │       │        │       │       │       │
│ Address: 0x0000000000000000000000000000000000000066  │                                                                            │ Count │ Mean  │ Median │ Stdev │ Min   │ Max   │
│ ---------------------------------------------------- │ -------------------------------------------------------------------------- │ ----- │ ----- │ -----  │ ----- │ ----- │ ----- │
│ Function: foo                                        │   4: def foo(a: uint256 = 0):                                              │ 1     │ 73    │ 73     │ 0     │ 73    │ 73    │
│                                                      │   5: x: uint256 = a                                                        │ 1     │ 15    │ 15     │ 0     │ 15    │ 15    │
└──────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────┴───────┴───────┴────────┴───────┴───────┴───────┘
```

## Understanding the Output

The profiler generates two tables:

### 1. Call Profile Table
Shows gas consumption statistics for each function call:
- **Contract**: The contract name
- **Address**: The deployed contract address
- **Computation**: The function name
- **Count**: Number of times the function was called
- **Mean/Median/Stdev**: Statistical metrics for gas usage
- **Min/Max**: Range of gas consumption

### 2. Line Profile Table
Shows gas consumption for each line of code within functions:
- Displays the actual source code line
- Shows how many times each line was executed
- Provides statistical metrics for each line's gas usage

## Advanced Usage

### Accessing Profile Data Programmatically

```python
from boa.profiling import get_line_profile_table, get_call_profile_table, global_profile

@pytest.mark.gas_profile
def test_analyze_gas():
    contract = boa.load("Complex.vy")
    
    # Multiple calls to gather statistics
    for i in range(10):
        contract.process(i)
    
    # Access raw profile data
    call_profiles = global_profile().call_profiles
    line_profiles = global_profile().line_profiles
    
    # Get specific function's gas usage
    for (contract_addr, fn_name), profile in call_profiles.items():
        if fn_name == "process":
            print(f"Process function - Mean gas: {profile.mean}")
            print(f"Process function - Max gas: {profile.max}")
```

### Profiling Complex Scenarios

```python
@pytest.mark.gas_profile
def test_gas_optimization_comparison():
    # Compare two implementations
    contract_v1 = boa.load("OptimizedV1.vy")
    contract_v2 = boa.load("OptimizedV2.vy")
    
    # Test both versions
    for i in range(100):
        contract_v1.compute(i)
        contract_v2.compute(i)
    
    # Results will show gas differences in the profile tables
```

### Custom Gas Metering

```python
from boa.vm.gas_meters import ProfilingGasMeter

def test_specific_profiling():
    # Temporarily enable profiling for specific operations
    with boa.env.gas_meter_class(ProfilingGasMeter):
        contract = boa.load("MyContract.vy")
        result = contract.expensive_operation()
        
        # Get immediate results
        from boa.profiling import get_line_profile_table
        print(get_line_profile_table())
```

## Best Practices

### 1. Profile Representative Workloads

```python
@pytest.mark.gas_profile
def test_realistic_usage():
    contract = boa.load("DEX.vy")
    
    # Simulate realistic usage patterns
    users = [boa.env.generate_address() for _ in range(10)]
    
    # Various transaction types
    for user in users:
        with boa.env.prank(user):
            contract.swap(100, 0, path=[token_a, token_b])
            contract.add_liquidity([1000, 1000], 0)
            contract.remove_liquidity(50, [0, 0])
```

### 2. Use Statistical Significance

```python
@pytest.mark.gas_profile
def test_with_statistics():
    contract = boa.load("Storage.vy")
    
    # Run enough iterations for meaningful statistics
    for i in range(100):
        # Vary the input to test different code paths
        if i % 2 == 0:
            contract.store_single(i)
        else:
            contract.store_batch([i, i+1, i+2])
    
    # The stdev in the output will show consistency
```

### 3. Isolate Gas-Critical Functions

```python
@pytest.mark.gas_profile  
def test_critical_function_only():
    contract = boa.load("Protocol.vy")
    
    # Setup (not critical for gas)
    contract.initialize(admin, fee_recipient)
    
    # Reset gas tracking for the critical part
    boa.env.reset_gas_used()
    
    # Profile only the critical function
    contract.critical_operation(large_input_data)
```

## Integration with CI/CD

```yaml
# .github/workflows/gas-report.yml
name: Gas Report

on: [pull_request]

jobs:
  gas-profile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run Gas Profiling
        run: |
          pytest tests/ --gas-profile -v > gas-report.txt
      
      - name: Post Gas Report as Comment
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('gas-report.txt', 'utf8');
            // Extract and post relevant parts of the report
```

## Limitations and Considerations

!!! note
    If a specific fixture is called in two separate tests, pytest will re-instantiate it. Meaning, if a Contract is deployed in a fixture, calling the fixture on tests in two separate files can lead to two deployments of that Contract, and hence two separate addresses in the profile table.

!!! warning
    Profiling does not work with pytest-xdist plugin at the moment.

!!! tip
    Gas profiling adds overhead to test execution. For large test suites, consider profiling a subset of tests or using sampling techniques.

## Troubleshooting

### No Profile Output

If you don't see profiling output:

```python
# Check if profiling is enabled
from boa.profiling import global_profile
print(f"Has profiles: {len(global_profile().call_profiles) > 0}")

# Ensure the test has the correct marker
# Use @pytest.mark.gas_profile, not @pytest.mark.profile
```

### Inconsistent Results

For more consistent results:

```python
@pytest.mark.gas_profile
def test_consistent_gas():
    # Warm up the EVM
    contract = boa.load("MyContract.vy")
    contract.function()  # First call might have different gas
    
    # Reset before actual measurement
    boa.env.reset_gas_used()
    
    # Now measure
    for _ in range(50):
        contract.function()
```
