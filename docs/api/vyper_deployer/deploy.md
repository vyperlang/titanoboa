# `deploy`

### Signature

```python
deploy(*args, **kwargs) -> VyperContract
```

### Description

Deploys the Vyper contract and returns a `VyperContract` instance.

- `*args`: Positional constructor arguments.
- `**kwargs`: Deployment options such as `value`, `gas`, `sender`, `override_address`, and `skip_initcode` — not constructor keyword arguments.
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
<class 'boa.contracts.vyper.vyper_contract.VyperContract'>
```
