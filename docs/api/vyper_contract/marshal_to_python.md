# `marshal_to_python`

### Signature

```python
marshal_to_python(computation, vyper_typ) -> Any
```

### Description

Converts the result of a computation to a Python object based on the Vyper type.

- `computation`: The computation result to be converted.
- `vyper_typ`: The Vyper type of the result.
- Returns: The result as a Python object.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main() -> uint256:
...     return 42
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> contract = deployer.deploy()
>>> result = contract.main()
>>> contract.marshal_to_python(result, uint256)
42
```