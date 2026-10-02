# `decode_log`

### Signature

```python
decode_log(e) -> Event
```

### Description

Decodes a raw log entry into an `Event` instance.

- `e`: A `RawLogEntry` (or compatible raw log tuple) to decode.
- Returns: An `Event` instance (typically a namedtuple).

[`get_logs`](get_logs.md) already decodes logs when possible. Use `decode_log`
when you have a raw log entry and need to decode it yourself.

### Examples

```python
>>> import boa
>>> src = """
... event MyEvent:
...     value: uint256
...
... @external
... def main():
...     log MyEvent(42)
... """
>>> contract = boa.loads(src, name="Foo")
>>> contract.main()
>>> # Prefer get_logs() for already-decoded events:
>>> contract.get_logs()
[MyEvent(value=42)]
```
