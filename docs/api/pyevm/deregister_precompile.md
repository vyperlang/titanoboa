# `deregister_precompile`

### Signature

```python
deregister_precompile(address: str, force: bool = True)
```

### Description

Deregister a precompile.

- `address`: The address of a previously registered precompile.
- `force`: Whether to force removal of the precompile at the specified address.
- Raises `ValueError`: If a precompile is not registered at the specified address and the force argument is `False`.
