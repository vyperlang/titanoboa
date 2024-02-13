import json
from typing import Optional

import requests

SESSION = requests.Session()


def _fetch_etherscan(uri: str, api_key: Optional[str] = None, **params) -> dict:
    if api_key is not None:
        params["apikey"] = api_key

    res = SESSION.get(uri, params=params)
    res.raise_for_status()
    data = res.json()

    if int(data["status"]) != 1:
        raise ValueError(f"Failed to retrieve data from API: {data}")

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
