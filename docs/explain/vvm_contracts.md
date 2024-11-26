# Legacy Vyper Contracts

Titanoboa supports legacy Vyper contracts, which are Vyper contracts that are not compatible with the latest Vyper version.

[Vyper Version Manager (vvm)]() is used to whenver a contract with a Vyper version lower than the latest Vyper version is detected.

VVM will install the correct version of the compiler on the fly and use it to compile the contract.

However this comes with a performance overhead and some limitations, here's a non-exhaustive list of limitations:

- The correct version of the compiler has to be downloaded on the fly, which can be slow on the first run.
- Functionalities that are specific to [`VyperContract`](../api/vyper_contract/overview.md) might not be available (i.e. pretty error traces).
- Using a legacy Vyper contract is not recommended as older versions contain known bugs and security issues.
