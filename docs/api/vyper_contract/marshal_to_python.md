# `marshal_to_python`

### Signature

```python
marshal_to_python(computation, vyper_typ) -> Any
```

### Description

Converts the result of a computation to a Python object based on the Vyper type.

- `computation`: A py-evm computation object (not the already-decoded Python return value).
- `vyper_typ`: The Vyper type of the result (a Vyper type object, not a bare name like `uint256`).
- Returns: The result as a Python object.

Titanoboa calls this internally when you invoke a contract function. Prefer the
normal call path for application code:

```python
>>> import boa
>>> src = """
... @external
... def main() -> uint256:
...     return 42
... """
>>> contract = boa.loads(src, name="Foo")
>>> contract.main()
42
```

`marshal_to_python` is useful when you already have a computation object from a
lower-level path (for example after `env.execute_code` / `env.deploy`) and need
to decode its output with a known Vyper type.
