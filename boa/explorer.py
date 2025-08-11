import re
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from boa.rpc import json
from boa.util.abi import Address
from boa.verifiers import ContractVerifier, VerificationResult

try:
    from requests_cache import CachedSession

    def filter_fn(response):
        return response.ok and _is_success_response(response.json())

    SESSION = CachedSession(
        "~/.cache/titanoboa/explorer_cache",
        filter_fn=filter_fn,
        allowable_codes=[200],
        cache_control=True,
        expire_after=3600 * 6,
        stale_if_error=True,
        stale_while_revalidate=True,
    )
except ImportError:
    from requests import Session

    SESSION = Session()

DEFAULT_ETHERSCAN_URI = "https://api.etherscan.io/v2/api"
VERSION_RE = re.compile(r"v(\d+\.\d+\.\d+)(\+commit.*)?")


@dataclass
class Etherscan(ContractVerifier[str]):
    uri: Optional[str] = DEFAULT_ETHERSCAN_URI
    api_key: Optional[str] = None
    chain_id: Optional[int] = None
    num_retries: int = 10
    backoff_ms: int | float = 400.0
    backoff_factor: float = 1.1  # 1.1**10 ~= 2.59
    timeout = timedelta(minutes=2)

    def verify(
        self,
        address: Address,
        contract_name: str,
        solc_json: dict,
        constructor_calldata: bytes,
        chain_id: int,
        license_type: str = "1",
        wait: bool = False,
    ) -> Optional["VerificationResult[str]"]:
        """
        Verify the Vyper contract on Etherscan.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param solc_json: The solc_json output of the Vyper compiler.
        :param constructor_calldata: The calldata for the contract constructor.
        :param chain_id: The ID of the chain where the contract is deployed.
        :param license_type: The license to use for the contract. Defaults to "none".
        :param wait: Whether to return a VerificationResult immediately
                     or wait for verification to complete. Defaults to False
        """
        api_key = self.api_key or ""
        # @dev for backward compatibility with parameter `chain_id`
        self.chain_id = chain_id or self.chain_id
        output_selection = solc_json["settings"]["outputSelection"]
        contract_file = next(k for k, v in output_selection.items() if "*" in v)
        compiler_version = solc_json["compiler_version"]
        version_match = re.match(VERSION_RE, compiler_version)
        if not version_match:
            raise ValueError(f"Failed to extract Vyper version from {compiler_version}")

            # V2 now use query parameters instead of data
        # @dev https://docs.etherscan.io/etherscan-v2/api-endpoints/contracts#verify-vyper-source-code
        params = {
            "module": "contract",
            "action": "verifysourcecode",
            "apikey": api_key,
            "chainid": chain_id,
            "contractname": f"{contract_file}:{contract_name}",
            "compilerversion": f"vyper:{version_match.group(1)}",
            "optimizationUsed": "1",
            "sourceCode": json.dumps(solc_json),
            "constructorArguments": constructor_calldata.hex(),
            "contractaddress": address,
        }

        # @dev maybe not needed anymore?
        data = {
            "codeformat": "vyper-json",
            "licenseType": license_type,
        }

        def verification_created():
            # we need to retry until the contract is found by Etherscan
            response = SESSION.post(self.uri, params=params, data=data)
            response.raise_for_status()
            response_json = response.json()
            if response_json.get("status") == "1":
                return response_json["result"]
            if (
                response_json.get("message") == "NOTOK"
                and "Unable to locate ContractCode" not in response_json["result"]
            ):
                raise ValueError(f"Failed to verify: {response_json['result']}")
            print(
                f"Verification could not be created yet: {response_json['result']}. Retrying..."
            )
            return None

        etherscan_guid = self._wait_until(
            verification_created, timedelta(minutes=2), timedelta(seconds=5), 1.1
        )
        print(f"Verification started with etherscan_guid {etherscan_guid}")
        if not wait:
            return VerificationResult(etherscan_guid, self)

        self.wait_for_verification(etherscan_guid)
        return None

    def wait_for_verification(self, etherscan_guid: str) -> None:
        """
        Waits for the contract to be verified on Etherscan.
        :param etherscan_guid: The unique ID of the contract verification.
        """
        self._wait_until(
            lambda: self.is_verified(etherscan_guid),
            self.timeout,
            self.backoff,
            self.backoff_factor,
        )
        print("Contract verified!")

    @property
    def backoff(self):
        return timedelta(milliseconds=self.backoff_ms)

    def is_verified(self, etherscan_guid: str) -> bool:
        api_key = self.api_key or ""
        chain_id = self.chain_id
        url = f"{self.uri}?module=contract&action=checkverifystatus"
        url += f"&guid={etherscan_guid}&apikey={api_key}&chainid={chain_id}"

        response = SESSION.get(url)
        response.raise_for_status()
        response_json = response.json()
        if (
            response_json.get("message") == "NOTOK"
            and "Pending in queue" not in response_json["result"]
        ):
            raise ValueError(f"Failed to verify: {response_json['result']}")
        return response_json.get("status") == "1"

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

    def fetch_abi(self, address: str, chain_id: int):
        # resolve implementation address if `address` is a proxy contract
        address = self._resolve_implementation_address(address, chain_id)

        # fetch ABI of `address`
        params = dict(
            module="contract", action="getabi", address=address, chainid=chain_id
        )
        data = self._fetch(**params)

        return json.loads(data["result"].strip())

    # fetch the address of a contract; resolves at most one layer of
    # indirection if the address is a proxy contract.
    def _resolve_implementation_address(self, address: str, chain_id: int) -> str:
        # Set chain_id here since fetch_abi requires it
        self.chain_id = chain_id or self.chain_id

        params = dict(
            module="contract", action="getsourcecode", address=address, chainid=chain_id
        )
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
