# API and import index

This page lists the supported import paths for Titanoboa's main public APIs.
Most everyday helpers are exported from `boa`; lower-level helpers stay in
their owning modules.

## Contract loading and interaction

- `boa.load`, `boa.loads`: compile and deploy Vyper source.
- `boa.load_partial`, `boa.loads_partial`: compile and return a deployer.
- `boa.load_abi`, `boa.loads_abi`: return an `ABIContractFactory`.
- `boa.load_vyi`, `boa.loads_vyi`: return an interface factory.
- `boa.from_etherscan`: fetch an ABI and attach it to a deployed address.
- `boa.set_etherscan`: temporarily or permanently configure explorer defaults.

See [Loading contracts](load_contracts.md) and
[Explorer configuration](explorer.md).

## Environments and testing

- `boa.env`: the current singleton environment.
- `boa.Env`, `boa.NetworkEnv`: environment classes.
- `boa.set_env`, `boa.reset_env`, `boa.fork`, `boa.set_network_env`,
  `boa.set_browser_env`: select the active environment.
- `boa.reverts`, `boa.deal`, `boa.fuzz`: test helpers.
- `boa.test.strategy`: a Hypothesis strategy for a canonical ABI type string.

See [Pick your environment](env/singleton.md), [Env](env/env.md),
[Testing and forking](testing.md), and [Fuzzing](fuzz.md).

## EVM customization and diagnostics

- `boa.precompile`: register a typed Python-backed Vyper builtin.
- `boa.patch_opcode`: replace an opcode implementation.
- `boa.enable_pyevm_verbose_logging`: enable py-evm's `DEBUG2` computation log.
- `boa.vm.py_evm.register_raw_precompile`: register a low-level computation
  callback at a fixed address.
- `boa.vm.py_evm.deregister_raw_precompile`: remove a raw precompile.

See [Typed precompiles](precompile.md),
[Raw precompiles](pyevm/register_precompile.md), and
[Runtime diagnostics](runtime.md).

## Compilation, cache, and deployment records

- `boa.interpret.set_cache_dir`, `boa.interpret.disable_cache`: configure the
  compilation cache.
- `boa.interpret.set_search_paths`: configure Vyper compiler import paths.
- `boa.deployments.DeploymentsDB`, `boa.deployments.set_deployments_db`,
  `boa.deployments.get_deployments_db`: record and query live-network
  deployments.
- `boa.profiling.get_call_profile_table`,
  `boa.profiling.get_line_profile_table`, `boa.profiling.global_profile`:
  inspect gas-profile data.

See [Cache](cache.md), [Deployments database](../guides/deployments.md), and
[Gas profiling](../guides/testing/gas_profiling.md).

## Deprecations

- Use `boa.fork(...)`, not `boa.env.fork(...)`. The top-level helper creates a
  fresh environment and can restore the previous one when used in a `with`
  statement.
- Use `boa.set_env(...)`, not `boa.swap_env(...)`. Both currently provide
  scoped environment replacement, but `set_env` is the canonical API.
- Use `boa.interpret.set_search_paths(...)`, not the deprecated singular
  `boa.interpret.set_search_path(...)`.

Deprecation does not imply immediate removal, but new code and documentation
should use the canonical forms above.
