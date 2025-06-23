# `BrowserEnv`

Inherits: [`NetworkEnv`](network_env.md)

## Description

A specialized environment for running in Jupyter notebooks that connects to browser wallets (MetaMask, etc.) via JavaScript. Enables direct interaction with user wallets for transaction signing.

## Constructor

```python
BrowserEnv(address=None, **kwargs)
```

### Parameters

- `address` - Specific wallet address to use (optional, defaults to first available account)
- `**kwargs` - Additional arguments passed to `NetworkEnv`

## Key Features

- **Browser Integration** - Uses `BrowserSigner` to request wallet signatures through JavaScript
- **Auto Address Detection** - Automatically discovers available wallet accounts
- **Chain Switching** - Can request users to switch networks via `set_chain_id()`

## Usage

```python
import boa

# Set up browser environment
boa.set_browser_env()

# Deploy and interact with contracts
contract = boa.loads_partial("@external\ndef get() -> uint256: return 42").deploy()
```

The environment automatically handles wallet connection and transaction signing through the browser.
