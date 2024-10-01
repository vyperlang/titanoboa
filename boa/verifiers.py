import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Optional

import requests

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
        wait: bool = False,
    ) -> Optional["VerificationResult"]:
        """
        Verify the Vyper contract on Blockscout.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param standard_json: The standard JSON output of the Vyper compiler.
        :param license_type: The license to use for the contract. Defaults to "none".
        :param wait: Whether to return a VerificationResult immediately
                     or wait for verification to complete. Defaults to False
        """
        if license_type is None:
            license_type = "none"

        api_key = self.api_key or ""

        url = f"{self.uri}/api/v2/smart-contracts/{address}/"
        url += f"verification/via/vyper-standard-input?apikey={api_key}"
        data = {
            "compiler_version": standard_json["compiler_version"],
            "license_type": license_type,
        }
        files = {
            "files[0]": (
                contract_name,
                json.dumps(standard_json).encode("utf-8"),
                "application/json",
            )
        }

        response = requests.post(url, data=data, files=files)
        response.raise_for_status()
        print(response.json().get("message"))  # usually verification started

        if not wait:
            return VerificationResult(address, self)

        self.wait_for_verification(address)
        return None

    def wait_for_verification(self, address: Address) -> None:
        """
        Waits for the contract to be verified on Blockscout.
        :param address: The address of the contract.
        """
        timeout = datetime.now() + self.timeout
        wait_time = self.backoff
        while datetime.now() < timeout:
            if self.is_verified(address):
                msg = "Contract verified!"
                msg += f" {self.uri}/address/{address}?tab=contract_code"
                print(msg)
                return
            time.sleep(wait_time.total_seconds())
            wait_time *= self.backoff_factor

        raise TimeoutError("Timeout waiting for verification to complete")

    def is_verified(self, address: Address) -> bool:
        api_key = self.api_key or ""
        url = f"{self.uri}/api/v2/smart-contracts/{address}?apikey={api_key}"

        response = requests.get(url)
        if response.status_code in self.retry_http_codes:
            return False
        response.raise_for_status()
        return response.json().get("is_verified", False)


_verifier = Blockscout()


@dataclass
class VerificationResult:
    address: Address
    verifier: Blockscout

    def wait_for_verification(self):
        self.verifier.wait_for_verification(self.address)

    def is_verified(self):
        return self.verifier.is_verified(self.address)


def _set_verifier(verifier):
    global _verifier
    _verifier = verifier


def get_verifier():
    global _verifier
    return _verifier


# TODO: maybe allow like `set_verifier("blockscout", *args, **kwargs)`
def set_verifier(verifier):
    return Open(get_verifier, _set_verifier, verifier)


def verify(contract, verifier=None, license_type: str = None) -> VerificationResult:
    """
    Verifies the contract on a block explorer.
    :param contract: The contract to verify.
    :param verifier: The block explorer verifier to use.
                     Defaults to get_verifier().
    :param license_type: Optional license to use for the contract.
    """
    if verifier is None:
        verifier = get_verifier()

    if not hasattr(contract, "deployer") or not hasattr(
        contract.deployer, "standard_json"
    ):
        raise ValueError(f"Not a contract! {contract}")

    address = contract.address
    return verifier.verify(
        address=address,
        standard_json=contract.deployer.standard_json,
        contract_name=contract.contract_name,
        license_type=license_type,
    )
