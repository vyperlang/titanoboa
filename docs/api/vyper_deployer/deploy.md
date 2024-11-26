# `deploy`

### Signature

```python
deploy(*args, **kwargs) -> VyperContract
```

### Description

Deploys the Vyper contract and returns a `VyperContract` instance.

- `*args`: Positional arguments to pass to the contract's constructor.
- `**kwargs`: Keyword arguments to pass to the contract's constructor.
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
```