# `__init__`

### Signature

```python
def __init__(self, abi, bytecode, name, filename, compiler_output, source_code, vyper_version)
```

### Description

Initializes the `VVMDeployer` instance.

- `abi`: The contract's ABI.
- `bytecode`: The contract's bytecode.
- `name`: The contract name.
- `filename`: The filename of the contract.
- `compiler_output`: The raw compiler output dictionary.
- `source_code`: The Vyper source used for compilation.
- `vyper_version`: The Vyper version string used to compile the contract.

Prefer [`from_compiler_output`](from_compiler_output.md) or
`boa.loads_partial(...)` over constructing `VVMDeployer` manually.

### Examples

```python
>>> from boa.contracts.vvm.vvm_contract import VVMDeployer
>>> deployer = VVMDeployer(
...     abi=[...],
...     bytecode=b"...",
...     name="MyContract",
...     filename="MyContract.vy",
...     compiler_output={"abi": [...], "bytecode": "0x..."},
...     source_code="# pragma version 0.3.10\n...",
...     vyper_version="0.3.10",
... )
```
