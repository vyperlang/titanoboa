# `BrowserEnv`

Inherits: [`NetworkEnv`](network_env.md)

## Description

A `NetworkEnv` for JupyterLab and Google Colab. It sends JSON-RPC requests through the browser wallet and uses a `BrowserSigner` to request transactions and typed-data signatures.

## Constructor

```python
BrowserEnv(address=None, **kwargs)
```

### Parameters

- `address` - Wallet account to select (optional; defaults to the first account returned by `eth_requestAccounts`)
- `**kwargs` - Additional arguments passed to `NetworkEnv`

## Key Features

- **Browser Integration** - Uses `BrowserSigner` to request wallet signatures through JavaScript
- **Auto Address Detection** - Automatically discovers available wallet accounts
- **Chain Switching** - Can request users to switch networks via `set_chain_id()`
- **NetworkEnv semantics** - Simulates mutable calls locally before sending them and uses `eth_call` for view calls

## Usage

```python
import boa

# Set up browser environment
boa.set_browser_env()

# Deploy and interact with contracts
contract = boa.loads(
    """
@external
@pure
def get() -> uint256:
    return 42
"""
)

# Ask the wallet to switch to chain ID 1, then refresh forked state.
boa.env.set_chain_id(1)
```

The environment refreshes the selected signer before calls and deployments. The selected account must remain available in the wallet.

As with any `NetworkEnv`, `set_balance`, `set_code`, and `set_storage` are unavailable. Pytest isolation also requires the connected provider to implement `evm_snapshot` and `evm_revert`. Browser wallet confirmation and RPC errors can interrupt a call after local simulation succeeds.

Titanoboa exposes its callback endpoint as a Python Jupyter server extension. No separate JupyterLab frontend extension needs to be enabled.
