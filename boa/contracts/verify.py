import json
from datetime import datetime, timedelta

import requests
from attr import dataclass

from boa.util.abi import Address


@dataclass
class Blockscout:
    api_key: str
    api_url: str = "https://eth.blockscout.com"

    def verify(
        self,
        address: Address,
        contract_name: str,
        standard_json: dict,
        evm_version: str,
        license="none",
    ):
        response = requests.post(
            url=f"{self.api_url}/api/v2/smart-contracts/{address.lower()}/"
            f"verification/via/vyper-standard-input?apikey={self.api_key}",
            data={
                "compiler_version": standard_json["compiler_version"],
                "license_type": license,
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
        message = response.json().get("message")
        if message != "Smart-contract verification started":
            raise Exception(f"Unexpected response: {response.text}")

        print(message)
        timeout = datetime.now() + timedelta(minutes=5)
        while datetime.now() < timeout:
            if self._is_verified(address):
                print(
                    f"Contract verified! {self.api_url}/address/{address.lower()}?tab=contract_code"
                )
                return

        raise TimeoutError("Timeout waiting for verification to complete")

    def _is_verified(self, address: Address) -> bool:
        url = f"{self.api_url}/api/v2/smart-contracts/{address.lower()}?apikey={self.api_key}"
        response = requests.get(url)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True
