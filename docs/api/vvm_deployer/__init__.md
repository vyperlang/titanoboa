# `__init__`

### Signature

```python
def __init__(self, abi, bytecode, filename)
```

### Description

Initializes the `VVMDeployer` instance with the given ABI, bytecode, and filename.

- `abi`: The ABI of the contract.
- `bytecode`: The bytecode of the contract.
- `filename`: The name of the contract file.

### Examples

```python
>>> abi = [...]  # ABI of the contract
>>> bytecode = "0x..."  # Bytecode of the contract
>>> filename = "MyContract"
>>> deployer = VVMDeployer(abi, bytecode, filename)
```