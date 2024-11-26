# `__call__`

### Signature

```python
__call__(*args, **kwargs) -> VyperContract
```

### Description

Deploys the Vyper contract and returns a `VyperContract` instance. This method is a shorthand for the `deploy` method.

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
>>> contract = deployer()
>>> type(contract)
<class 'boa.vyper.contract.VyperContract'>
```