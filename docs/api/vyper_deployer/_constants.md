# `_constants`

### Property

```python
@property
_constants: ConstantsModel
```

### Description

Provides access to the constants defined in the Vyper contract.

- Returns: A `ConstantsModel` instance.

### Examples

```python
>>> import boa
>>> src = """
... x: constant(uint256) = 123
... """
>>> deployer = boa.loads_partial(src)
>>> deployer._constants.MY_CONSTANT
123
```