# `__call__`

### Signature

```python
def __call__(self, *args, **kwargs)
```

### Description

Allows the instance to be called like a function to deploy the contract.

- `*args`: Arguments to pass to the constructor.
- `**kwargs`: Keyword arguments to pass to the deploy method.

### Examples

```python
>>> deployer = VVMDeployer(abi, bytecode, filename)
>>> contract = deployer(arg1, arg2)
```