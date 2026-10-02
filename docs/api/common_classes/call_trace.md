# `call_trace`

!!! function "`contract.call_trace() -> TraceFrame`"

    Return the most recent computation as a nested `TraceFrame`.

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

    The trace is attached to the contract's most recent computation. Call the
    contract function before requesting it. Child frames represent nested EVM
    calls and use registered contract metadata when available.
