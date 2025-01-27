# `deploy`

### Signature

```python
def deploy(self, *args, env=None)
```

### Description

Deploys the contract with optional arguments and environment.

- `*args`: Arguments to pass to the constructor.
- `env`: The environment to use for deployment. If not provided, a singleton environment is used.

### Examples

```python
>>> deployer = VVMDeployer(abi, bytecode, filename)
>>> contract = deployer.deploy(arg1, arg2)
```
