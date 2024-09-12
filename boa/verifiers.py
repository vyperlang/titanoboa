import json
import time
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Optional

import requests
from attr import dataclass

from boa.util.abi import Address

DEFAULT_BLOCKSCOUT_URI = "https://eth.blockscout.com"


@dataclass
class Blockscout:
    """
    Allows users to verify contracts on Blockscout.
    This is independent of Vyper contracts, and can be used to verify any smart contract.
    """

    uri: str = DEFAULT_BLOCKSCOUT_URI
    api_key: Optional[str] = None
    timeout: timedelta = timedelta(minutes=2)
    backoff: timedelta = timedelta(milliseconds=500)
    backoff_factor: float = 1.1
    retry_http_codes: tuple[int, ...] = (
        HTTPStatus.NOT_FOUND,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    )

    def verify(
        self,
        address: Address,
        contract_name: str,
        standard_json: dict,
        evm_version: str,
        license_type: str = None,
    ) -> None:
        """
        Verifies the Vyper contract on Blockscout.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param standard_json: The standard JSON output of the Vyper compiler.
        :param evm_version: The EVM version to use for verification.
        :param license_type: The license to use for the contract. Defaults to "none".
        """
        if license_type is None:
            license_type = "none"
        response = requests.post(
            url=f"{self.uri}/api/v2/smart-contracts/{address.lower()}/"
            f"verification/via/vyper-standard-input?apikey={self.api_key or ''}",
            data={
                "compiler_version": standard_json["compiler_version"],
                "license_type": license_type,
                "evm_version": evm_version,
            },
            files={
                "files[0]": (
                    contract_name,
                    json.dumps(standard_json).encode("utf-8"),
                    "application/json",
                )
            },
        )
        response.raise_for_status()
        print(response.json().get("message"))  # usually verification started

        timeout = datetime.now() + timedelta(minutes=2)
        wait_time = self.backoff
        while datetime.now() < timeout:
            time.sleep(wait_time.total_seconds())
            if self.is_verified(address):
                print(
                    f"Contract verified! {self.uri}/address/{address.lower()}?tab=contract_code"
                )
                return
            wait_time *= self.backoff_factor

        raise TimeoutError("Timeout waiting for verification to complete")

    def is_verified(self, address: Address) -> bool:
        url = (
            f"{self.uri}/api/v2/smart-contracts/{address.lower()}?apikey={self.api_key}"
        )
        response = requests.get(url)
        if response.status_code in self.retry_http_codes:
            return False
        response.raise_for_status()
        return True
