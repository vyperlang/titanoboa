# `trace_source`

### Signature

```python
trace_source(computation) -> Optional[VyperTraceSource]
```

### Description

Returns the source of the trace for the computation.

- `computation`: The computation to get the trace source for.
- Returns: A `VyperTraceSource` instance or `None`.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     assert False, "error"
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> contract = deployer.deploy()
>>> try:
...     contract.main()
... except:
...     pass
>>> contract.trace_source(contract._computation)
<VyperTraceSource ...>
```