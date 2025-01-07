# `_BaseVyperContract`

### Description

The `_BaseVyperContract` class extends `_BaseEVMContract` and provides additional functionality specific to Vyper contracts. It includes methods for handling Vyper-specific features such as ABI encoding/decoding, event handling, and more.

### Methods

- [deployer](deployer.md)
- [abi](abi.md)
- [_constants](_constants.md)

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
