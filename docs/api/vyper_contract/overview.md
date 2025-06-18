# `VyperContract`

### Description

A contract instance.

Internal and external contract functions are available as methods on `VyperContract` instances.

### Methods

- [eval](eval.md)
- [deployer](deployer.md)
- [marshal_to_python](marshal_to_python.md)
- [stack_trace](stack_trace.md)
- [trace_source](trace_source.md)
- [get_logs](get_logs.md)
- [decode_log](decode_log.md)
- [inject_function](inject_function.md)
- [storage_introspection](storage_introspection.md) - Access storage, immutables, and constants

### Properties

- `_storage` - Access storage variables with automatic decoding
- `_immutables` - Access immutable values
- `_constants` - Access contract constants
- `address` - The deployed address of the contract
- `created_from` - Address that deployed this contract

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
...
... @internal
... def foo() -> uint256:
...     return 123
... """
>>> contract = boa.loads_partial(src, name="Foo").deploy()
>>> type(contract.main)
<class 'boa.vyper.contract.VyperFunction'>
>>> type(contract.internal.foo)
<class 'boa.vyper.contract.VyperInternalFunction'>
>>> contract.internal.foo()
123
```
