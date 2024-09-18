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

DEFAULT_ETHERSCAN_URI = "https://api.etherscan.io/api"


@dataclass
class Etherscan:
    uri: Optional[str] = DEFAULT_ETHERSCAN_URI
    api_key: Optional[str] = None
    num_retries: int = 10
    backoff_ms: int | float = 400.0
    backoff_factor: float = 1.1  # 1.1**10 ~= 2.59

    def __post_init__(self):
        if self.uri is None:
            self.uri = DEFAULT_ETHERSCAN_URI

    def _fetch(self, **params) -> dict:
        """
        Fetch data from Etherscan API.
        Offers a simple caching mechanism to avoid redundant queries.
        Retries if rate limit is reached.
        :param num_retries: Number of retries
        :param backoff_ms: Backoff in milliseconds
        :param params: Additional query parameters
        :return: JSON response
        """
        params = {**params, "apiKey": self.api_key}
        for i in range(self.num_retries):
            res = SESSION.get(self.uri, params=params)
            res.raise_for_status()
            data = res.json()
            if not _is_rate_limited(data):
                break

            f = self.backoff_factor**i
            seconds = self.backoff_ms / 1000
            time.sleep(f * seconds)

        if not _is_success_response(data):
            raise ValueError(f"Failed to retrieve data from API: {data}")

        return data

    def fetch_abi(self, address: str):
        # resolve implementation address if `address` is a proxy contract
        address = self._resolve_implementation_address(address)

        # fetch ABI of `address`
        params = dict(module="contract", action="getabi", address=address)
        data = self._fetch(**params)

        return json.loads(data["result"].strip())

    # fetch the address of a contract; resolves at most one layer of
    # indirection if the address is a proxy contract.
    def _resolve_implementation_address(self, address: str):
        params = dict(module="contract", action="getsourcecode", address=address)
        data = self._fetch(**params)
        source_data = data["result"][0]

        # check if the contract is a proxy
        if int(source_data["Proxy"]) == 1:
            return source_data["Implementation"]
        else:
            return address


_etherscan = Etherscan()


def get_etherscan():
    return _etherscan


def _set_etherscan(etherscan: Etherscan):
    global _etherscan
    _etherscan = etherscan


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
