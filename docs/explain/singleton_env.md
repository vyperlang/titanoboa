# Titanoboa Environments

When calling boa functions like `boa.load` or `boa.loads` to [deploy a contract](../api/load_contracts.md), the global (singleton) environment is used by default.

There are several types of environments depending on the usage.

## Env

The default environment, with a [py-evm](https://github.com/ethereum/py-evm) backend.
Without forking, this environment will start empty.

This is used for most testing purposes.
To set it as the singleton env, call [`boa.reset_env`](../api/env/singleton.md#reset_env).

### Forking

The `Env` can be backed by remote chain state using [`boa.fork`](../api/env/singleton.md#fork).
That requires an RPC URL and (optionally) a block identifier.
This will customize the environment's AccountDB to use the RPC as data source.

While forking, all execution will still run via [py-evm](https://github.com/ethereum/py-evm).
To set it as the singleton env, call [`boa.fork`](../api/env/singleton.md#fork).

## `NetworkEnv`

The [`NetworkEnv`](../api/env/network_env.md) is used to connect to a network via an RPC.
This is used to connect to a real network and deploy contracts.
To set it as the singleton env, call [`boa.set_network_env`](../api/env/singleton.md#set_network_env).

Mutable calls are simulated against a fresh local fork before `NetworkEnv` broadcasts them. View/pure calls use `eth_call`. Simulation catches many failures early, but it cannot prevent the live state changing before a transaction is mined.

To sign transactions, the `NetworkEnv` uses an `Account` or account-like object.
That object can be created from a private key, mnemonic or a keystore file.
It must be registered by calling [`add_account`](../api/env/network_env.md#add_account).

See also [`BrowserEnv`](#browserenv) to use a browser wallet.

## `BrowserEnv`

The [`BrowserEnv`](../api/env/browser_env.md) is actually a [`NetworkEnv`](#networkenv), but used in a Jupyter notebook (or in Google Colab).
However, it uses a browser to interact with the network:
- No RPC URL is needed, as it uses the browser's wallet.
- No need to configure accounts, as it integrates with the browser's wallet for signing transactions.

To set it as the singleton env, call [`boa.set_browser_env`](../api/env/singleton.md#set_browser_env).

### Communication between Python and the browser
The browser environment injects JavaScript code into the notebook with the `display` iPython functionality.
The injected code handles the communication between the wallet and the Python kernel.

When running in JupyterLab, a Tornado HTTP endpoint receives wallet callbacks. Titanoboa exposes this as a discoverable Python Jupyter server extension; a separate JupyterLab frontend-extension enable command is not required.
In Google Colab, communication uses Colab's JavaScript evaluation bridge.

## Automatic context management

`set_env`, `fork`, `set_network_env`, and `set_browser_env` return an optional context manager.
This allows you to use the environment in a `with` block, and it will automatically revert to the previous environment when the block exits.

!!! python
    ```python

    # set function may be called inside a context manager
    with boa.set_network_env(rpc_url):
        # This code will run in the network environment
        ...

    # here the previous environment is restored
    ```

They may also be called outside a context manager. In that case the new environment remains the singleton. `reset_env()` is persistent and returns `None`.

!!! python
    ```python

    boa.set_network_env(rpc_url)

    ```

## Anchor & auto-revert

All environment classes expose `anchor()`, but the implementation differs.
That means that anything that happens inside the `with` block, will be reverted in the end.

Local `Env` instances and RPC-backed local forks use py-evm snapshots. `NetworkEnv` and `BrowserEnv` call `evm_snapshot` and `evm_revert` on their RPC; if those nonstandard methods are unavailable, `anchor()` raises `RuntimeError`.

For example:
!!! python
    ```python

    with boa.env.anchor():
        contract = boa.loads(code)
        # use contract here

    # now the contract is gone!
    ```

### Test plugin
Titanoboa provides a pytest plugin that will automatically call `anchor` for every test function, unless the `ignore_isolation` marker is provided.
Read more in [testing with pytest](../tutorials/pytest.md#titanoboa-plugin).

Fixture setup is anchored separately, and Hypothesis receives an anchor around every generated example. On a live RPC, `ignore_isolation` suppresses snapshot use but cannot roll back broadcast transactions.
