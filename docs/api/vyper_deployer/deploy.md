# `deploy`

### Signature

```python
deploy(*args, **kwargs) -> VyperContract
```

### Description

Deploys the Vyper contract and returns a `VyperContract` instance.

- `*args`: Positional arguments to pass to the contract's constructor.
- `**kwargs`: Keyword arguments to pass to the contract's constructor, including:
  - `value`: Amount of ETH to send with deployment (in wei)
  - `gas`: Gas limit for deployment
  - `override_address`: Override the deployment address
  - `authorization_list`: EIP-7702 authorization list (NetworkEnv only)
  - `authorize`: EIP-7702 convenience for single authorization (NetworkEnv only)
- Returns: A `VyperContract` instance.

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

# With EIP-7702 authorization (NetworkEnv only)
>>> auth = boa.env.sign_authorization(account, contract_address)
>>> contract = deployer.deploy(authorization_list=[auth])
```
