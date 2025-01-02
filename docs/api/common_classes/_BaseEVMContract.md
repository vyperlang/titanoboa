# `_BaseEVMContract`

### Description

The `_BaseEVMContract` class provides the base functionality for EVM contracts. It includes methods for handling contract deployment, execution, and interaction.

### Methods

- [stack_trace](stack_trace.md)
- [call_trace](call_trace.md)
- [handle_error](handle_error.md)

### Properties

- [address](address.md)

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> contract = deployer.deploy()
>>> type(contract)
<class 'boa.vyper.contract.VyperContract'>
```
