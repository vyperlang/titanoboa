# Pick your environment

This page documents the functions to set the singleton environment.
If you need help choosing an environment, see the [Titanoboa Environments](../../explain/singleton_env.md) page.

Note that all the `set_env` functions return an optional context manager.
See [context management](../../explain/singleton_env.md#automatic-context-management) section for more information.

## `set_env`

Sets the global environment to a custom `Env` instance.

```python
def set_env(new_env) -> Open
```

Returns a context manager that can optionally restore the previous environment.

```python
import boa

custom_env = boa.Env()
with boa.set_env(custom_env):
    # Use custom environment
    pass
# Previous environment restored
```

## `fork`

Forks from a live network, creating a new environment with the forked state.

```python
def fork(
    url: str, 
    block_identifier: int | str = "safe", 
    allow_dirty: bool = False, 
    **kwargs
) -> Open
```

```python
# Fork mainnet at latest safe block
with boa.fork("https://eth.llamarpc.com"):
    # Interact with forked mainnet state
    pass
```

## `set_browser_env`

Sets up a browser-connected environment for Jupyter notebooks.

```python
def set_browser_env(address=None) -> Open
```

```python
# Connect to browser wallet
boa.set_browser_env()
```

## `set_network_env`

Creates a network environment connected to a custom RPC URL.

```python
def set_network_env(url) -> Open
```

```python
# Connect to custom network
with boa.set_network_env("https://sepolia.infura.io/v3/API_KEY"):
    # Deploy on Sepolia
    pass
```

## `reset_env`

Resets to a fresh local environment.

```python
def reset_env() -> None
```

```python
boa.reset_env()  # Clean slate
```

## `swap_env` (Deprecated)

!!! warning "Deprecated API"
    `swap_env` is an older API that will likely be deprecated. Use `set_env` instead.

Context manager version of `set_env` that requires being used in a `with` statement.
