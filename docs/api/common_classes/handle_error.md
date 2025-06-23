# `handle_error`

Base method for error handling in EVM contracts.

## Signature

```python
def handle_error(self, computation: ComputationAPI) -> None
```

## Parameters

- `self`: The contract instance
- `computation`: The failed computation object containing execution state and error information

## Description

Creates and raises a `BoaError` when contract execution fails. This method:

1. Creates a `BoaError` from the failed computation
2. Strips internal frames from the traceback to show only user-relevant code
3. Re-raises the error with clean stack trace

## Usage

This method is called automatically by the framework when contract execution encounters an error. It's not typically called directly by users.

## Related

- [`BoaError`](../exceptions/boa_error.md) - The exception type created by this method
- [`stack_trace`](stack_trace.md) - Used to generate detailed error information
