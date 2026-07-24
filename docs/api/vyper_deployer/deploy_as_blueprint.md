# `deploy_as_blueprint`

### Signature

```python
deploy_as_blueprint(*args, **kwargs) -> VyperBlueprint
```

### Description

Deploys the Vyper contract as a blueprint and returns a `VyperBlueprint` instance.

Blueprint deployment does not run the implementation constructor. Arguments are
deployment options for the blueprint itself (for example `env`,
`override_address`, `blueprint_preamble`, and `gas`), not constructor calldata
for the implementation contract.

- Returns: A `VyperBlueprint` instance.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> blueprint = deployer.deploy_as_blueprint()
>>> type(blueprint)
<class 'boa.contracts.vyper.vyper_contract.VyperBlueprint'>
```
