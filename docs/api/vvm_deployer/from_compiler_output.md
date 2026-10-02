# `from_compiler_output`

### Signature

```python
@classmethod
def from_compiler_output(cls, compiler_output, name, filename, source_code, vyper_version)
```

### Description

Creates an instance of `VVMDeployer` from compiler output.

- `compiler_output`: The compiler output dictionary containing `abi` and `bytecode`.
- `name`: The contract name.
- `filename`: The filename of the contract.
- `source_code`: The Vyper source used for compilation.
- `vyper_version`: The Vyper version string used to compile the contract.

### Examples

```python
>>> from boa.contracts.vvm.vvm_contract import VVMDeployer
>>> compiler_output = {
...     "abi": [...],
...     "bytecode": "0x..."
... }
>>> deployer = VVMDeployer.from_compiler_output(
...     compiler_output,
...     name="MyContract",
...     filename="MyContract.vy",
...     source_code="# pragma version 0.3.10\n...",
...     vyper_version="0.3.10",
... )
```
