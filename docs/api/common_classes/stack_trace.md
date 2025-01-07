# `stack_trace`

### Signature

```python
stack_trace(computation: ComputationAPI) -> StackTrace
```

### Description

Returns the stack trace of the computation.

- `computation`: The computation to get the stack trace for.
- Returns: A `StackTrace` instance.

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
>>> contract.stack_trace(contract._computation)
<StackTrace ...>
```
