# `VyperContract`

### Description

A contract instance.

Internal and external contract functions are available as methods on `VyperContract` instances.

### Methods

- [eval](eval.md)
- [deployer](deployer.md)
TODO mention common classes
<!-- - [Common Classes](../common_classes/overview.md) -->
- [marshal_to_python](marshal_to_python.md)
- [stack_trace](stack_trace.md)
- [trace_source](trace_source.md)
- [get_logs](get_logs.md)
- [decode_log](decode_log.md)
- [inject_function](inject_function.md)

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
