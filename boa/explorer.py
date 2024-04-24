import json
import logging
from time import sleep
from typing import Optional

import requests

SESSION = requests.Session()
_cached_abi: dict[str, dict] = {}


def _fetch_etherscan(uri: str, api_key: Optional[str] = None, **params) -> dict:
    """
    Fetch data from Etherscan API.
    Offers a simple caching mechanism to avoid redundant queries.
    Retries if rate limit is reached.
    :param uri: Etherscan API URI
    :param api_key: Etherscan API key
    :param params: Query parameters
    :return: JSON response
    """
    if uri in _cached_abi:
        return _cached_abi[uri]

    if api_key is not None:
        params["apikey"] = api_key

    for _ in range(10):
        res = SESSION.get(uri, params=params)
        res.raise_for_status()
        data = res.json()
        if data.get("result") != "Max rate limit reached":
            break
        logging.warning("Rate limit reached, retrying...")
        sleep(0.3)

    if int(data["status"]) != 1:
        raise ValueError(f"Failed to retrieve data from API: {data}")

    logging.warning(f"Queried Etherscan API with params: {params}")
    _cached_abi[uri] = data
    return data


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
