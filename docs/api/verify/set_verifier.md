# `set_verifier`

Sets the contract verifier, optionally as a context manager.

## Signature

```python
def set_verifier(verifier: ContractVerifier)
```

## Parameters

- `verifier` - The `ContractVerifier` instance to use

## Usage

```python
import boa
from boa.verifiers import Blockscout

# Set globally
custom_verifier = Blockscout(uri="https://custom.blockscout.com")
boa.set_verifier(custom_verifier)

# Use as context manager (temporary)
with boa.set_verifier(custom_verifier):
    boa.verify(contract)  # Uses custom verifier
# Reverts to original verifier after context
```