# `BoaError`

## Description

Exception raised when contract execution fails. Contains detailed debugging information including call trace and stack trace.

ABI and VVM contracts display only the call trace to avoid repeating the same
information. Native Vyper contracts raise `VyperError`, a subclass of `BoaError`,
which also displays source locations, local variables, storage, and compiler
diagnostics. Catching `boa.BoaError` continues to handle all contract types.

Both exception types retain `call_trace` and `stack_trace` for inspection.

## Properties

- `call_trace` - Visual representation of the call hierarchy
- `stack_trace` - Detailed execution trace with source code context

## Usage

```python
import boa

contract = boa.loads('''
@external
def fail():
    raise "something went wrong"
''')

try:
    contract.fail()
except boa.BoaError as e:
    print(e.stack_trace)
    print(e.call_trace)
```

## Error Matching

Use with `boa.reverts()` context manager for testing expected failures:

```python
with boa.reverts("something went wrong"):
    contract.fail()
```
