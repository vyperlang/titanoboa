# Writing unit tests with pytest

Titanoboa integrates with [pytest](https://docs.pytest.org/) and [Hypothesis](https://hypothesis.readthedocs.io/en/latest/quickstart.html). Its pytest plugin is installed with Titanoboa and provides automatic EVM-state isolation.

Since `titanoboa` is framework-agnostic any other testing framework should work as well.

Let's cover the basics of testing with boa and pytest.

Let's start with a simple example contract `Example.vy`:

!!!vyper

    ```vyper
    foo: public(uint256)

    @external
    def set_foo(foo: uint256):
        self.foo = foo
    ```

We want to test that the `set_foo` function works correctly. That is, given an input, it should set the `foo` variable to the input value.

In the same folder as `Example.vy`, we create a file `test_example.py`:

We first create a [pytest fixture](https://docs.pytest.org/en/8.3.x/how-to/fixtures.html) that will deploy the contract:
!!!python

    ```python
    import pytest
    import boa

    @pytest.fixture
    def example():
        return boa.load("Example.vy")
    ```

We can then write a test for the `set_foo` function, we can use `example` fixture to get an instance of the contract:

!!!python

    ```python
    def test_set_foo(example):
        example.set_foo(50)
        assert example.foo() == 50
    ```

We can run the test by calling `pytest`:

!!! example "Bash"

    ```bash
    > pytest test_example.py
    ============================= test session starts ==============================
    ...
    collected 1 item

    test_example.py::test_set_foo PASSED

    ============================== 1 passed in 0.01s ===============================
    ```

## Titanoboa Plugin

The plugin anchors both fixture setup and each test call. Fixture state therefore follows pytest fixture scopes while modifications made by a dependent fixture or test are reverted when that fixture or test finishes. Parametrized test cases are isolated from one another.

Hypothesis gets an additional anchor around every generated example, including state-machine examples. A contract fixture can therefore be reused while every example starts from the fixture's original state.

Local `Env` instances and RPC-backed py-evm forks can always snapshot locally. A live [`NetworkEnv`](../api/env/network_env.md) can isolate only when its RPC implements `evm_snapshot` and `evm_revert`; otherwise `anchor()` raises `RuntimeError`.

Use `ignore_isolation` only for tests that intentionally cannot be snapshotted:

!!! python
    ```python
    import pytest

    # Disable isolation for every test and fixture setup in this module.
    pytestmark = pytest.mark.ignore_isolation

    # this will ignore the isolation for this specific test
    @pytest.mark.ignore_isolation
    def test_set_foo(example):
        example.set_foo(50)
        assert example.foo() == 50
    ```

!!! warning
    On a live RPC without snapshot support, `ignore_isolation` avoids the error but cannot undo transactions. Broadcast state persists on the network. It also disables fixture-level anchors for the marked test, so do not rely on state leaking between tests unless that coupling is intentional.

Gas profiling uses `@pytest.mark.gas_profile` or the `--gas-profile` option. The collection hook recognizes `ignore_gas_profiling`, while the runtime conflict check currently looks for `ignore_profiling`; this naming inconsistency is a known implementation issue.

See more details in the [environment explanation](../explain/singleton_env.md#anchor-auto-revert).
