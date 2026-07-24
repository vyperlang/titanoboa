# Explorer configuration

## `set_etherscan`

!!! function "`boa.set_etherscan(uri=..., api_key=None, chain_id=1, **retry_options)`"

    Configure the `Etherscan` client used by `boa.from_etherscan()` and by
    Etherscan verification. The default endpoint is Etherscan API v2 and the
    default chain ID is Ethereum mainnet (`1`).

    The function returns a context-capable setting. Calling it normally keeps
    the new explorer configuration; using it in a `with` statement restores
    the previous configuration on exit.

    ```python
    import boa

    boa.set_etherscan(
        api_key="YOUR_ETHERSCAN_API_KEY",
        chain_id=1,
    )
    token = boa.from_etherscan(
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    )
    ```

    For temporary configuration:

    ```python
    with boa.set_etherscan(
        uri="https://api.etherscan.io/v2/api",
        api_key="YOUR_ETHERSCAN_API_KEY",
        chain_id=1,
    ):
        token = boa.from_etherscan(
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        )
    ```

    Supported retry options include `num_retries`, `backoff_ms`, and
    `backoff_factor`. `chain_id` must be a positive integer.

## `from_etherscan`

!!! function "`boa.from_etherscan(address, name=None, uri=None, api_key=None, chain_id=None)`"

    Fetch the contract ABI, resolve one proxy implementation layer when
    reported by the explorer, and return an `ABIContract` attached to
    `address`.

    With no one-off `chain_id`, Titanoboa uses the active environment's chain
    ID. Explicit `uri`, `api_key`, and `chain_id` arguments override the
    configured defaults for that request.

See [Loading contracts](load_contracts.md#from_etherscan) for more examples.
