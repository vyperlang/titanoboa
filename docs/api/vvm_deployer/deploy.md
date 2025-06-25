# `deploy`

### Signature

```python
def deploy(self, *args, contract_name=None, env=None, **kwargs)
```

### Description

Deploys the contract with optional arguments and environment.

- `*args`: Arguments to pass to the constructor.
- `contract_name`: Optional name to give the deployed contract.
- `env`: The environment to use for deployment. If not provided, a singleton environment is used.
- `**kwargs`: Additional keyword arguments including:
  - `value`: Amount of ETH to send with deployment (in wei)
  - `gas`: Gas limit for deployment
  - `override_address`: Override the deployment address
  - `authorization_list`: EIP-7702 authorization list (NetworkEnv only)
  - `authorize`: EIP-7702 convenience for single authorization (NetworkEnv only)

### Examples

```python
>>> deployer = VVMDeployer(abi, bytecode, filename)
>>> contract = deployer.deploy(arg1, arg2)

# With EIP-7702 authorization (NetworkEnv only)
>>> auth = boa.env.sign_authorization(account, contract_address)
>>> contract = deployer.deploy(authorization_list=[auth])
```
