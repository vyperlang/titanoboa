# `from_compiler_output`

### Signature

```python
@classmethod
def from_compiler_output(cls, compiler_output, filename)
```

### Description

Creates an instance of `VVMDeployer` from the compiler output.

- `compiler_output`: The output from the compiler containing the ABI and bytecode.
- `filename`: The name of the contract file.

### Examples

```python
>>> compiler_output = {
...     "abi": [...],
...     "bytecode": "0x..."
... }
>>> filename = "MyContract"
>>> deployer = VVMDeployer.from_compiler_output(compiler_output, filename)
```
