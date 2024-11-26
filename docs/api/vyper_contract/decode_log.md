# `decode_log`

### Signature

```python
decode_log(e) -> Event
```

### Description

Decodes a log entry into an `Event` instance.

- `e`: The log entry to decode.
- Returns: An `Event` instance.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     log MyEvent()
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> contract = deployer.deploy()
>>> contract.main()
>>> log_entry = contract.get_logs()[0]
>>> contract.decode_log(log_entry)
<Event ...>
```