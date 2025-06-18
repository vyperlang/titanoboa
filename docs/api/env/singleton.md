# Pick your environment

This page documents the functions to set the singleton environment.
If you need help choosing an environment, see the [Titanoboa Environments](../../explain/singleton_env.md) page.

Note that all the `set_env` functions return an optional context manager.
See [context management](../../explain/singleton_env.md#automatic-context-management) section for more information.

## `set_env`

Sets the global environment to a custom `Env` instance.

### Signature

```python
def set_env(new_env: Env) -> Open
```

### Parameters

- `new_env`: The new environment instance to set as the global environment

### Returns

An `Open` context manager that can optionally restore the previous environment when used with `with`.

### Usage

```python
import boa

# As a regular function call (environment persists)
custom_env = boa.Env()
boa.set_env(custom_env)

# As a context manager (environment restored on exit)
with boa.set_env(custom_env):
    # Use custom environment
    pass
# Previous environment restored
```

## `fork`

Forks from a live network, creating a new environment with the forked state.

### Signature

```python
def fork(
    url: str, 
    block_identifier: int | str = "safe", 
    allow_dirty: bool = False, 
    **kwargs
) -> Open
```

### Parameters

- `url`: The RPC URL of the network to fork from
- `block_identifier`: Block number or "safe"/"latest" to fork at (default: "safe")
- `allow_dirty`: Whether to allow forking with uncommitted changes in current environment (default: False)
- `**kwargs`: Additional keyword arguments passed to the underlying fork method

### Returns

An `Open` context manager that manages the forked environment.

### Raises

- `Exception`: If the current environment has dirty state and `allow_dirty` is False

### Usage

```python
# Fork mainnet at latest safe block
with boa.fork("https://eth.llamarpc.com"):
    # Interact with forked mainnet state
    pass

# Fork at specific block
with boa.fork("https://eth.llamarpc.com", block_identifier=17000000):
    pass
```

## `set_browser_env`

Sets up a browser-connected environment for Jupyter notebooks.

### Signature

```python
def set_browser_env(address=None) -> Open
```

### Parameters

- `address`: The account address to use (optional). If not provided, uses the connected wallet address.

### Returns

An `Open` context manager for the browser environment.

### Usage

```python
# Connect to browser wallet
boa.set_browser_env()

# Use specific address
boa.set_browser_env("0x...")
```

### Note

This function requires Jupyter to be installed and should be used in Jupyter/Colab notebooks.

## `set_network_env`

Creates a network environment connected to a custom RPC URL.

### Signature

```python
def set_network_env(url: str) -> Open
```

### Parameters

- `url`: The RPC URL to connect to

### Returns

An `Open` context manager for the network environment.

### Usage

```python
# Connect to custom network
with boa.set_network_env("https://sepolia.infura.io/v3/API_KEY"):
    # Deploy on Sepolia
    pass

# Or without context manager
boa.set_network_env("https://sepolia.infura.io/v3/API_KEY")
```

## `reset_env`

Resets to a fresh local environment.

### Signature

```python
def reset_env() -> None
```

### Parameters

None

### Returns

None. This function sets a new `Env()` instance but does not return the context manager.

### Usage

```python
boa.reset_env()  # Clean slate
```

### Note

Unlike other environment functions, `reset_env()` does not return a context manager. The environment change is persistent.

## `swap_env` (Deprecated)

!!! warning "Deprecated API"
    `swap_env` is an older API that will likely be deprecated. Use `set_env` instead.

Context manager version of `set_env` that requires being used in a `with` statement.
