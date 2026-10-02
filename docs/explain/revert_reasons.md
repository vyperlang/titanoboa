# Revert Reasons

A contract may revert during the runtime via the `REVERT` opcode.
During execution, the revert does exactly the same thing independent on the error source.
However, for a developer, there are different reasons to get a revert.
Each of them may be used with [`boa.reverts`](../api/testing.md#boareverts) to test the contract behavior.

## Compiler Revert Reasons

These happen when Vyper inserts a runtime check.
For example:
- Range errors
- Overflows
- Division by zero
- Re-entrancy locks

Things like syntax errors will not be caught during the runtime, but the contract will fail to compile on the first place.

Match these with the `compiler` keyword:

```python
with boa.reverts(compiler="safeadd"):
    contract.add(max_value, 1)
```

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

Pass a string positionally, or use `vm_error`, to match an onchain revert string:

```python
with boa.reverts("x must be greater than 0"):
    contract.foo(0)

with boa.reverts(vm_error="x must be greater than 0"):
    contract.foo(0)
```

## Dev Revert Reasons

Developer reasons are comments attached to a statement. The text before `:` is an arbitrary tag, not a fixed `dev` keyword. Titanoboa can recover the tag and reason from source information without adding the string to deployed bytecode.

!!! vyper
    ```vyper
    @external
    def foo(x: uint256):
        assert x > 0  # dev: x must be greater than 0

    @external
    def bar(x: uint256):
        assert x < 10  # rekt: x must be less than 10
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

    with boa.reverts(rekt="x must be less than 10"):
        contract.bar(10)
    ```

## Matching Reverts in Tests

`boa.reverts` accepts different keyword arguments, each matching a different kind of revert reason:

| kwarg | matches |
| --- | --- |
| (none) | any `BoaError` |
| positional string | the VM reason, compiler reason, or developer reason text |
| `reason=` | a `# reason: <reason>` comment |
| `vm_error=` | an onchain user revert string (`raise "reason"` or `assert cond, "reason"`) |
| `compiler=` | a compiler-generated reason (overflow, `safeadd`, bounds checks, ...) |
| `dev=` | a `# dev: <reason>` comment |
| `rekt=` | a `# rekt: <reason>` comment |

The positional form can match a developer reason without specifying its tag:

```python
# given: raise  # reason: x is 1
with boa.reverts("x is 1"):
    contract.foo(1)

with boa.reverts(reason="x is 1"):
    contract.foo(1)
```

`compiler` and `vm_error` have special matching behavior. Any other keyword is treated as a developer tag, so its spelling must match the source comment. A mismatched reason raises `ValueError`.

A wildcard `with boa.reverts():` catches any revert, and fails the test if the call does *not* revert. That makes it a cheap sanity check, but prefer a specific matcher when the revert reason matters, so your test fails loudly if the contract starts reverting for a different reason.

### Precedence

Matching depends on the kind of failure and the source statement:

- A **compiler reason** takes precedence over a plain `assert` string. If `assert x + 1 == 5` overflows, the reason is the compiler's overflow, not the assert string.
- On an `assert` or `raise` statement, a developer tag matches only when that statement itself caused the revert; it cannot mask an overflow while evaluating the assertion. On other statements, a **`# dev:` / `# rekt:` comment** can name a compiler failure, such as overflow in a `return` expression, with zero gas or bytecode cost.
- A dev comment on an unrelated line does *not* mask the real reason.

In practice this means: match `compiler=` when you are exercising a language-level failure, and match `dev=`/`rekt=` when the contract author gave the revert a name. If you are unsure which reason a revert produces, let a test fail once and read the error message: Titanoboa reports the mismatch.

### Testing Compiler Reverts

```python
# uint256 addition overflow is a compiler (safeadd) revert
with boa.reverts(compiler="safeadd"):
    contract.bar(2**256 - 1)
```

### Testing Dev Reverts

```python
# given:  def bar(x: uint256) -> uint256: return x + 1  # dev: could overflow
with boa.reverts(dev="could overflow"):
    contract.bar(2**256 - 1)

# `# rekt: <reason>` is matched with the rekt= kwarg
with boa.reverts(rekt="overflow!"):
    contract.baz(2**256 - 1)
```

All the examples above are exercised in `tests/unitary/test_reverts.py`, which is the most complete reference for the edge cases (multiline asserts, nested calls, constructor reverts).
