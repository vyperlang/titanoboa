# `VyperBlueprint`

### Description

The `VyperBlueprint` class represents a blueprint of a Vyper contract. It is used to deploy contracts using the blueprint pattern, which allows for more efficient contract deployment.

### Methods

<!-- - [Common Classes](../common_classes/overview.md) -->
TODO mention common classes

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
<class 'boa.vyper.contract.VyperBlueprint'>
```