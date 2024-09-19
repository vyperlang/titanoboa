import json
import time
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Optional

import requests
from attr import dataclass

from boa.util.abi import Address
from boa.util.open_ctx import Open

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
        license_type: str = None,
    ) -> None:
        """
        Verifies the Vyper contract on Blockscout.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param standard_json: The standard JSON output of the Vyper compiler.
        :param license_type: The license to use for the contract. Defaults to "none".
        """
        if license_type is None:
            license_type = "none"

        api_key = self.api_key or ""

        response = requests.post(
            url=f"{self.uri}/api/v2/smart-contracts/{address}/"
            f"verification/via/vyper-standard-input?apikey={api_key}",
            data={
                "compiler_version": standard_json["compiler_version"],
                "license_type": license_type,
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

        timeout = datetime.now() + self.timeout
        wait_time = self.backoff
        while datetime.now() < timeout:
            time.sleep(wait_time.total_seconds())
            if self.is_verified(address):
                msg = "Contract verified!"
                msg += f" {self.uri}/address/{address}?tab=contract_code"
                print(msg)
                return
            wait_time *= self.backoff_factor

        raise TimeoutError("Timeout waiting for verification to complete")

    def is_verified(self, address: Address) -> bool:
        api_key = self.api_key or ""
        url = f"{self.uri}/api/v2/smart-contracts/{address}?apikey={api_key}"

        response = requests.get(url)
        if response.status_code in self.retry_http_codes:
            return False
        response.raise_for_status()
        return True


_verifier = Blockscout()


def _set_verifier(verifier):
    global _verifier
    _verifier = verifier


def get_verifier():
    global _verifier
    return _verifier


def set_verifier(verifier):
    return Open(get_verifier, _set_verifier, verifier)
