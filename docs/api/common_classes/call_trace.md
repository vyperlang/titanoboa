# `call_trace`

<!-- TODO: Format this with !!!function syntax -->

### Signature

```python
call_trace() -> TraceFrame
```

### Description

Returns the call trace of the computation.

- Returns: A `TraceFrame` instance.

### Examples

!!! python

    ```python
    >>> import boa
    >>> src = """
    ... @external
    ... def main():
    ...     pass
    ... """
    >>> deployer = boa.loads_partial(src, name="Foo")
    >>> contract = deployer.deploy()
    >>> contract.main()
    >>> contract.call_trace()
    <TraceFrame ...>
    ```
