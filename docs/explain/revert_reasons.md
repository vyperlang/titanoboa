# Revert Reasons

A contract may revert during the runtime via the `REVERT` opcode.
During execution, the revert does exactly the same thing independent on the error source.
However, for a developer, there are different reasons to get a revert.
Each of them may be used with [`boa.reverts`](../api/testing.md#boareverts) to test the contract behavior.

## Compiler Revert Reasons

These happen when the compiler generates the error message.
For example:
- Range errors
- Overflows
- Division by zero
- Re-entrancy locks

Things like syntax errors will not be caught during the runtime, but the contract will fail to compile on the first place.

## User Revert Reasons

These happen when the user calls `raise` or `assert` fails in the contract.
The user may provide a reason for the revert, which will be shown to the end user.
!!! vyper
    ```vyper
    @external
    def foo(x: uint256):
        assert x > 0, "x must be greater than 0"
    ```

Note that this may happen directly on the contract being called, or any external contract that the contract interacts with.

## Dev Revert Reasons

Developer reverts are also raised by `assert` statements in the code.
However, by adding a `# dev: <reason>` comment after the assert call, Titanoboa is able to verify the reason and provide a more detailed error message.

!!! vyper
    ```vyper
    @external
    def foo(x: uint256):
        assert x > 0 # dev: "x must be greater than 0"
    ```

These reasons are completely offchain and useful when the contract storage is limited (EIP 170).

Traditional revert strings cost gas and bytecode when deploying.
When a revert condition is triggered, extra gas will also be incurred.
Strings are relatively heavy - each character consumes gas.

However, when using [`VyperContract`](../api/vyper_contract/overview.md), Titanoboa is able to track the line where the revert happened.
If it finds a `# dev: <reason>` comment, it will provide a more detailed error message to the developer.

This is particularly useful when testing contracts with [`boa.reverts`](../api/testing.md#boareverts), for example:
!!! python
    ```python
    with boa.reverts(dev="x must be greater than 0"):
        contract.foo(0)
    ```
