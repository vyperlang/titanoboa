# `VyperBlueprint`

### Description

The `VyperBlueprint` class represents a blueprint of a Vyper contract. It is used to deploy contracts using the blueprint pattern, which allows for more efficient contract deployment.

### Methods

`VyperBlueprint` shares the base EVM-contract tracing, address, and error
handling APIs:

- [`address`](../common_classes/address.md)
- [`stack_trace`](../common_classes/stack_trace.md)
- [`call_trace`](../common_classes/call_trace.md)
- [`handle_error`](../common_classes/handle_error.md)

Use the originating deployer's
[`deploy_as_blueprint`](../vyper_deployer/deploy_as_blueprint.md) method to
create a blueprint.

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
>>> blueprint.address
'0x...'
```
