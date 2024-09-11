import os
import time
from dataclasses import dataclass
from typing import Optional

from boa.rpc import json

try:
    from requests_cache import CachedSession

    SESSION = CachedSession(
        "~/.cache/titanoboa/explorer_cache",
        filter_fn=lambda response: _is_success_response(response.json()),
        allowable_codes=[200],
        cache_control=True,
        expire_after=3600 * 6,
        stale_if_error=True,
        stale_while_revalidate=True,
    )
except ImportError:
    from requests import Session

    SESSION = Session()


@dataclass
class ExplorerSettings:
    api_key: Optional[str] = os.environ.get("ETHERSCAN_API_KEY")
    uri: str = os.environ.get("ETHERSCAN_URI", "https://api.etherscan.io/api")


def _fetch_etherscan(
    settings: ExplorerSettings, num_retries=10, backoff_ms=400, **params
) -> dict:
    """
    Fetch data from Etherscan API.
    Offers a simple caching mechanism to avoid redundant queries.
    Retries if rate limit is reached.
    :param settings: Etherscan settings
    :param num_retries: Number of retries
    :param backoff_ms: Backoff in milliseconds
    :param params: Additional query parameters
    :return: JSON response
    """
    params = {**params, "apiKey": settings.api_key}
    for i in range(num_retries):
        res = SESSION.get(settings.uri, params=params)
        res.raise_for_status()
        data = res.json()
        if not _is_rate_limited(data):
            break
        backoff_factor = 1.1**i  # 1.1**10 ~= 2.59
        time.sleep(backoff_factor * backoff_ms / 1000)

    if not _is_success_response(data):
        raise ValueError(f"Failed to retrieve data from API: {data}")

    return data


def _is_success_response(data: dict) -> bool:
    return data.get("status") == "1"


def _is_rate_limited(data: dict) -> bool:
    """
    Check if the response is rate limited. Possible error messages:
    - Max calls per sec rate limit reached (X/sec)
    - Max rate limit reached, please use API Key for higher rate limit
    - Max rate limit reached
    :param data: Etherscan API response
    :return: True if rate limited, False otherwise
    """
    return "rate limit" in data.get("result", "") and data.get("status") == "0"


def fetch_abi_from_etherscan(
    address: str, settings: ExplorerSettings = ExplorerSettings()
):
    # resolve implementation address if `address` is a proxy contract
    address = _resolve_implementation_address(address, settings)

    # fetch ABI of `address`
    params = dict(module="contract", action="getabi", address=address)
    data = _fetch_etherscan(settings, **params)

    return json.loads(data["result"].strip())


# fetch the address of a contract; resolves at most one layer of indirection
# if the address is a proxy contract.
def _resolve_implementation_address(address: str, settings: ExplorerSettings):
    params = dict(module="contract", action="getsourcecode", address=address)
    data = _fetch_etherscan(settings, **params)
    source_data = data["result"][0]

    # check if the contract is a proxy
    if int(source_data["Proxy"]) == 1:
        return source_data["Implementation"]
    else:
        return address
