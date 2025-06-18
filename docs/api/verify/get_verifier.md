# `get_verifier`

Returns the current contract verifier instance.

## Signature

```python
def get_verifier() -> ContractVerifier
```

## Returns

The current `ContractVerifier` instance (defaults to `Blockscout()`)

## Example

```python
import boa

verifier = boa.get_verifier()
print(type(verifier))  # <class 'boa.verifiers.Blockscout'>
```