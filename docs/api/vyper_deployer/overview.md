# `VyperDeployer`

### Description

The `VyperDeployer` class is responsible for deploying Vyper contracts. It handles the compilation of Vyper source code and provides methods to deploy contracts and interact with them.

### Methods

- [deploy](deploy.md)
- [deploy_as_blueprint](deploy_as_blueprint.md)
- [stomp](stomp.md)
- [at](at.md)
- [\_\_call\_\_](__call__.md)

### Properties

- [solc_json](solc_json.md)
- [_constants](_constants.md)

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
