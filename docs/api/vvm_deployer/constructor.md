# `constructor`

### Signature

```python
@cached_property
def constructor(self)
```

### Description

Finds and returns the constructor function from the ABI.

### Examples

```python
>>> deployer = VVMDeployer(abi, bytecode, filename)
>>> constructor = deployer.constructor
```