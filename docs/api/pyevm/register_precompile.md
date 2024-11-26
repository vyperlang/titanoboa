# `register_precompile`

### Signature

```python
register_precompile(address: str, fn: Callable[[eth.abc.ComputationAPI], None], force: bool = False)
```

### Description

Register a precompile.

- `address`: The address to register the precompile at.
- `fn`: The function to execute when the precompile is called.
- `force`: Whether to overwrite the precompile function if one is already registered at the specified address.
- Raises `ValueError`: If a precompile is already registered at the specified address and the force argument is `False`.

### Examples

```python
>>> import boa
>>> log = lambda computation: print("0x" + computation.msg.sender.hex())
>>> boa.register_precompile("0x00000000000000000000000000000000000000ff", log)
>>> boa.eval("raw_call(0x00000000000000000000000000000000000000ff, b'')")
0x0000000000000000000000000000000000000069
```