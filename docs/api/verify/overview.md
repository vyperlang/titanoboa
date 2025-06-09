# Contract Verification

The verification module provides tools for verifying smart contracts on block explorers.

## Available Functions

- [verify](verify.md) - Verify a contract on a block explorer
- [get_verifier](get_verifier.md) - Get the current verifier instance
- [set_verifier](set_verifier.md) - Set or temporarily change the verifier

## Supported Verifiers

- **Blockscout** - Default verifier for Blockscout-based explorers

## Quick Example

```python
import boa

# Deploy a contract
contract = boa.loads_partial("@external\ndef get_value() -> uint256: return 42").deploy()

# Verify it on the block explorer
result = boa.verify(contract)
```