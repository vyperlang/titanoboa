import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Optional

import requests
from cached_property import cached_property

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
        solc_json: dict,
        license_type: str = None,
        wait: bool = False,
    ) -> Optional["VerificationResult"]:
        """
        Verify the Vyper contract on Blockscout.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param solc_json: The solc_json output of the Vyper compiler.
        :param license_type: The license to use for the contract. Defaults to "none".
        :param wait: Whether to return a VerificationResult immediately
                     or wait for verification to complete. Defaults to False
        """
        if license_type is None:
            license_type = "none"

        api_key = self.api_key or ""

        url = f"{self.uri}/api/v2/smart-contracts/{address}/"
        url += f"verification/via/vyper-standard-input?apikey={api_key}"

        version = self._get_compiler_version(solc_json["compiler_version"])
        solc_json = {**solc_json, "compiler_version": version}
        data = {"compiler_version": version, "license_type": license_type}
        file = (contract_name, json.dumps(solc_json), "application/json")

        response = requests.post(url, data=data, files={"files[0]": file})
        response.raise_for_status()
        print(response.json().get("message"))  # usually verification started
        # print(f"Sent {data} to {url} with {file}")

        if not wait:
            return VerificationResult(address, self)

        self.wait_for_verification(address)
        return None

    def _get_compiler_version(self, compiler_version) -> str:
        """
        Runs a partial match based on the compiler version.
        Blockscout only accepts exact matches, but vyper can have a different
        commit hash length depending on the version and installation method.

        Raises a ValueError if no match is found or if multiple matches are found.
        """
        supported = self.supported_versions
        match [v for v in supported if compiler_version in v]:
            case [version]:
                return version
            case []:
                err = "Could not find a matching compiler version on Blockscout. "
                err += f"Given: {compiler_version}, supported: {supported}."
                raise Exception(err)
            case multiple:
                err = "Ambiguous compiler version for Blockscout verification. "
                err += f"Given: {compiler_version}, found: {multiple}."
                raise Exception(err)

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

        raise TimeoutError(f"Timeout waiting for verification of {address}")

    def is_verified(self, address: Address) -> bool:
        api_key = self.api_key or ""
        url = f"{self.uri}/api/v2/smart-contracts/{address}?apikey={api_key}"

        response = requests.get(url)
        if response.status_code in self.retry_http_codes:
            return False
        response.raise_for_status()
        return response.json().get("is_verified", False)

    @cached_property
    def supported_versions(self) -> list[str]:
        response = requests.get(
            "https://http.sc-verifier.services.blockscout.com/api/v2/verifier/vyper/versions"
        )
        response.raise_for_status()
        return response.json()["compilerVersions"]


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


def get_verification_bundle(contract_like):
    if not hasattr(contract_like, "deployer"):
        return None
    if not hasattr(contract_like.deployer, "solc_json"):
        return None
    return contract_like.deployer.solc_json


# should we also add a `verify_deployment` function?
def verify(
    contract, verifier=None, license_type: str = None, wait=False
) -> VerificationResult:
    """
    Verifies the contract on a block explorer.
    :param contract: The contract to verify.
    :param verifier: The block explorer verifier to use.
                     Defaults to get_verifier().
    :param license_type: Optional license to use for the contract.
    """
    if verifier is None:
        verifier = get_verifier()

    if (bundle := get_verification_bundle(contract)) is None:
        raise ValueError(f"Not a contract! {contract}")

    return verifier.verify(
        address=contract.address,
        solc_json=bundle,
        contract_name=contract.contract_name,
        license_type=license_type,
        wait=wait,
    )
