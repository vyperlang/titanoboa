import time
from typing import Optional

from boa.rpc import json

try:
    from requests_cache import CachedSession, Response

    def _filter_fn(res: Response) -> bool:
        data = res.json()
        return _is_success_response(data) and not _is_rate_limited(data)

    SESSION = CachedSession("etherscan_cache", filter_fn=_filter_fn)
except ImportError:
    from requests import Session

    SESSION = Session()


def _fetch_etherscan(
    uri: str,
    api_key: Optional[str] = None,
    num_retries=10,
    backoff_ms=400,
    backoff_exp=1.1,
    **params,
) -> dict:
    """
    Fetch data from Etherscan API.
    Offers a simple caching mechanism to avoid redundant queries.
    Retries if rate limit is reached.
    :param uri: Etherscan API URI
    :param api_key: Etherscan API key
    :param num_retries: Number of retries
    :param backoff_ms: Backoff in milliseconds
    :param params: Additional query parameters
    :return: JSON response
    """
    if api_key is not None:
        params["apikey"] = api_key

    for i in range(num_retries):
        res = SESSION.get(uri, params=params)
        res.raise_for_status()
        data = res.json()
        if not _is_rate_limited(data):
            break
        backoff_factor = backoff_exp**i  # 1.1**10 ~= 2.59
        time.sleep(backoff_factor * backoff_ms / 1000)

    if not _is_success_response(data):
        raise ValueError(f"Failed to retrieve data from API: {data}")

    return data


def _is_success_response(data: dict) -> bool:
    return int(data["status"]) == 1


def _is_rate_limited(data: dict) -> bool:
    """
    Check if the response is rate limited. Possible error messages:
    - Max calls per sec rate limit reached (X/sec)
    - Max rate limit reached, please use API Key for higher rate limit
    - Max rate limit reached
    :param data: Etherscan API response
    :return: True if rate limited, False otherwise
    """
    return int(data["status"]) == 0 and "rate limit" in data.get("result", "")


def fetch_abi_from_etherscan(
    address: str, uri: str = "https://api.etherscan.io/api", api_key: str = None
):
    # resolve implementation address if `address` is a proxy contract
    address = _resolve_implementation_address(address, uri, api_key)

    # fetch ABI of `address`
    params = dict(module="contract", action="getabi", address=address)
    data = _fetch_etherscan(uri, api_key, **params)

    return json.loads(data["result"].strip())


# fetch the address of a contract; resolves at most one layer of indirection
# if the address is a proxy contract.
def _resolve_implementation_address(address: str, uri: str, api_key: Optional[str]):
    params = dict(module="contract", action="getsourcecode", address=address)
    data = _fetch_etherscan(uri, api_key, **params)
    source_data = data["result"][0]

    # check if the contract is a proxy
    if int(source_data["Proxy"]) == 1:
        return source_data["Implementation"]
    else:
        return address
