# Writing unit tests  pytest

Titanoboa integrates natively with [pytest](https://docs.pytest.org/) and [hypothesis](https://hypothesis.readthedocs.io/en/latest/quickstart.html). Nothing special is needed to enable these, as the plugins for these packages will be loaded automatically. By default, isolation is enabled for tests - that is, any changes to the EVM state inside the test case will automatically be rolled back after the test case completes.

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

<!-- note this is just llm generated, but it's enough for now -->

## Titanoboa Plugin

Titanoboa offers a pytest plugin that automatically resets the environment after each test.
This is useful to isolate each test and avoid side effects between them.
By using fixtures, pytest is able to correctly deploy the necessary contracts to run each specific test.

However, this can give errors when testing in network/fork mode.
Most importantly, some RPCs will not support the `evm_snapshot` and `evm_revert` methods, which are used to reset the state after each test.

To disable the plugin, you may add the `ignore_isolation` marker.

!!! python
    ```python
    import pytest

    # this will ignore the isolation for all tests in this file
    pytestmark = pytest.mark.ignore_isolation

    # this will ignore the isolation for this specific test
    @pytest.mark.ignore_isolation
    def test_set_foo(example):
        example.set_foo(50)
        assert example.foo() == 50
    ```

See more details in the [environment explanation](../explain/singleton_env.md#anchor--auto-revert).
