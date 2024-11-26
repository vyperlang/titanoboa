# `deploy_as_blueprint`

### Signature

```python
deploy_as_blueprint(*args, **kwargs) -> VyperBlueprint
```

### Description

Deploys the Vyper contract as a blueprint and returns a `VyperBlueprint` instance.

- `*args`: Positional arguments to pass to the contract's constructor.
- `**kwargs`: Keyword arguments to pass to the contract's constructor.
- Returns: A `VyperBlueprint` instance.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, "Foo")
>>> blueprint = deployer.deploy_as_blueprint()
>>> type(blueprint)
<class 'boa.vyper.contract.VyperBlueprint'>
```