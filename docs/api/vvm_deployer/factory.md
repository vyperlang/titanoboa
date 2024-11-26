# `factory`

### Signature

```python
@cached_property
def factory(self)
```

### Description

Returns a contract factory from the ABI.

### Examples

```python
>>> deployer = VVMDeployer(abi, bytecode, filename)
>>> factory = deployer.factory
```
