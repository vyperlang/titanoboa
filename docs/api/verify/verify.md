# `verify`

Verifies a smart contract on a block explorer.

## Signature

```python
def verify(
    contract,
    verifier: ContractVerifier = None,
    wait=False,
    **kwargs
) -> VerificationResult | None
```

## Parameters

- `contract` - The contract instance to verify
- `verifier` - The verifier to use (defaults to current verifier)
- `wait` - Whether to wait for verification to complete
- `**kwargs` - Additional arguments passed to the verifier

## Returns

- `VerificationResult` if `wait=False`
- `None` if `wait=True` (blocks until complete)

## Examples

```python
import boa

contract = boa.loads_partial("@external\ndef get() -> uint256: return 42").deploy()

# Start verification (non-blocking)
result = boa.verify(contract)
result.wait_for_verification()

# Verify and wait for completion
boa.verify(contract, wait=True)
```
