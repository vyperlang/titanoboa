import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Callable, Generic, Optional, TypeVar

import requests

from boa.environment import Env
from boa.util.abi import Address
from boa.util.cached_session import get_session
from boa.util.open_ctx import Open

DEFAULT_BLOCKSCOUT_URI = "https://eth.blockscout.com"
T = TypeVar("T")
P = TypeVar("P")


class ContractVerifier(Generic[T]):
    """A base class for contract verifiers.

    This class should be extended by specific verifiers like Etherscan, Blockscout, etc.
    """

    # Methods
    def verify(
        self,
        address: Address,
        contract_name: str,
        solc_json: dict,
        constructor_calldata: bytes,
        license_type: str = "1",
        wait: bool = False,
    ) -> Optional["VerificationResult[T]"]:
        raise NotImplementedError

    def wait_for_verification(self, identifier: T) -> None:
        raise NotImplementedError

    def is_verified(self, identifier: T) -> bool:
        raise NotImplementedError

    @staticmethod
    def _wait_until(
        predicate: Callable[[], P],
        wait_for: timedelta,
        backoff: timedelta,
        backoff_factor: float,
    ) -> P:
        timeout = datetime.now() + wait_for
        wait_time = backoff
        while datetime.now() < timeout:
            if result := predicate():
                return result
            time.sleep(wait_time.total_seconds())
            wait_time *= backoff_factor

        raise TimeoutError("Timeout waiting for verification to complete")


@dataclass
class Blockscout(ContractVerifier[Address]):
    """
    Allows users to verify contracts on Blockscout.
    This is independent of Vyper contracts, and can be used to verify any smart contract.

    @dev Blockscout does not require an API key
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
        constructor_calldata: bytes,
        license_type: str = "1",
        wait: bool = False,
    ) -> Optional["VerificationResult[Address]"]:
        """
        Verify the Vyper contract on Blockscout.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param solc_json: The solc_json output of the Vyper compiler.
        :param constructor_calldata: The calldata for the constructor.
        :param license_type: The license to use for the contract. Defaults to "none".
        :param wait: Whether to return a VerificationResult immediately
                     or wait for verification to complete. Defaults to False
        """
        if license_type is None:
            license_type = "none"

        # Prepare the API URL from Blockscout
        api_contract_url = f"{self.uri}/api/v2/addresses/{address}"
        api_verify_url = f"{self.uri}/api/v2/smart-contracts/{address}/verification/via/vyper-standard-input"

        # Prepare the data and files for the verification request
        data = {
            "compiler_version": solc_json["compiler_version"],
            "license_type": license_type,
        }
        files = {
            "files[0]": (
                contract_name,
                json.dumps(solc_json).encode("utf-8"),
                "application/json",
            )
        }

        # Check if the contract is already created or verified on Blockscout
        response_contract = self._wait_until(
            lambda: self.contract_created(api_contract_url, address),
            timedelta(minutes=2),
            timedelta(seconds=5),
            1.1,
        )

        # Check if the contract is already verified or if it is a valid contract
        if response_contract.get("is_verified") is True:
            print(f"Address {address} is already verified on Blockscout.")
            return VerificationResult(address, self)

        if response_contract.get("is_contract") is not True:
            raise ValueError(f"Address {address} is not a contract on Blockscout.")

        # If the address exists, we can proceed with the verification
        print(f"Verification started with address {address}")
        response_verif = requests.post(api_verify_url, data=data, files=files)
        response_verif.raise_for_status()
        print(response_verif.json().get("message"))  # usually verification started

        if not wait:
            return VerificationResult(address, self)

        self.wait_for_verification(address)
        return None

    def wait_for_verification(self, address: Address) -> None:
        """
        Waits for the contract to be verified on Blockscout.
        :param address: The address of the contract.
        """
        self._wait_until(
            lambda: self.is_verified(address),
            self.timeout,
            self.backoff,
            self.backoff_factor,
        )
        msg = "Contract verified!"
        msg += f" {self.uri}/address/{address}?tab=contract_code"
        print(msg)

    def is_verified(self, address: Address) -> bool:
        url = f"{self.uri}/api/v2/smart-contracts/{address}"

        response = requests.get(url)
        if response.status_code in self.retry_http_codes:
            return False
        response.raise_for_status()
        return response.json().get("is_verified", False)

    # Check if the address is valid on Blockscout
    def contract_created(
        self, api_contract_url: str, address: Address
    ) -> Optional[dict]:
        """Checks if the contract is created or verified on Blockscout.
        :return: The response JSON if the contract is created or verified, None otherwise.
        """
        SESSION = get_session()
        # we need to retry until the contract is created on Blockscout
        response = SESSION.get(api_contract_url)
        response.raise_for_status()
        response_json = response.json()
        if response_json.get("is_verified") is True:
            print(f"Address {address} is already verified on Blockscout.")
            return response_json

        if response_json.get("is_contract") is True:
            print(f"Address {address} exists on Blockscout.")
            return response_json

        # If the address is not a contract or not verified, we return None
        print(
            f"Verification could not be created yet: Address {address} not found on Blockscout. Retrying..."
        )

        return None


_verifier: ContractVerifier = Blockscout()


@dataclass
class VerificationResult(Generic[T]):
    identifier: T
    verifier: ContractVerifier

    def wait_for_verification(self):
        self.verifier.wait_for_verification(self.identifier)

    def is_verified(self):
        return self.verifier.is_verified(self.identifier)


def _set_verifier(verifier):
    global _verifier
    _verifier = verifier


def get_verifier():
    global _verifier
    return _verifier


# TODO: maybe allow like `set_verifier("blockscout", *args, **kwargs)`
def set_verifier(verifier: ContractVerifier):
    return Open(get_verifier, _set_verifier, verifier)


def get_verification_bundle(contract_like):
    if not hasattr(contract_like, "deployer"):
        return None
    if not hasattr(contract_like.deployer, "solc_json"):
        return None
    return contract_like.deployer.solc_json


# should we also add a `verify_deployment` function?
def verify(
    contract, verifier: ContractVerifier = None, wait=False, **kwargs
) -> VerificationResult | None:
    """
    Verifies the contract on a block explorer.
    :param contract: The contract to verify.
    :param verifier: The block explorer verifier to use.
                     Defaults to get_verifier().
    :param wait: Whether to wait for verification to complete.
    """
    if verifier is None:
        verifier = get_verifier()

    if (bundle := get_verification_bundle(contract)) is None:
        raise ValueError(f"Not a contract! {contract}")

    # Set chain_id if verifier supports it
    if hasattr(verifier, "chain_id"):
        verifier.chain_id = Env.get_singleton().get_chain_id()

    return verifier.verify(
        address=contract.address,
        solc_json=bundle,
        contract_name=contract.contract_name,
        constructor_calldata=contract.ctor_calldata,
        wait=wait,
        **kwargs,
    )
