import contextlib
import sys
from typing import Union

from boa.contracts.base_evm_contract import BoaError
from boa.contracts.vyper.vyper_contract import check_boa_error_matches
from boa.debugger import BoaDebug
from boa.environment import Env
from boa.interpret import (
    from_etherscan,
    load,
    load_abi,
    load_partial,
    loads,
    loads_abi,
    loads_partial,
)
from boa.network import NetworkEnv
from boa.precompile import precompile
from boa.test.strategies import fuzz
from boa.vm.py_evm import enable_pyevm_verbose_logging, patch_opcode

# turn off tracebacks if we are in repl
# https://stackoverflow.com/a/64523765
if hasattr(sys, "ps1"):  # pragma: no cover
    pass
    # sys.tracebacklimit = 0

env = Env.get_singleton()


@contextlib.contextmanager
def swap_env(new_env):
    old_env = env
    try:
        set_env(new_env)
        yield
    finally:
        set_env(old_env)


def set_env(new_env):
    global env
    env = new_env

    Env._singleton = new_env


def set_browser_env(address=None, chain_id: Union[None, str, int] = None):
    """Set the environment to use the browser's network in Jupyter/Colab"""
    # import locally because jupyter is generally not installed
    from boa.integrations.jupyter.browser import BrowserRPC, BrowserSigner

    rpc = BrowserRPC(chain_id)
    e = NetworkEnv(rpc)
    signer = BrowserSigner(address, rpc)
    setattr(e, "signer", signer)
    e.set_eoa(signer)
    return set_env(e)


def set_network_env(url):
    """Set the environment to use a custom network URL"""
    set_env(NetworkEnv.from_url(url))


def fork(*args, try_prefetch_state=False, fast_mode_enabled=False, **kwargs):
    """Fork the current environment to use a custom network URL"""
    e = Env(try_prefetch_state, fast_mode_enabled)
    e.fork(*args, **kwargs)
    return set_env(e)


def fork_browser(
    url: str,
    address=None,
    *args,
    chain_id: Union[None, str, int] = None,
    try_prefetch_state=False,
    fast_mode_enabled=False,
    **kwargs,
):
    """Fork the current environment to use browser RPC"""
    from boa.integrations.jupyter import BrowserRPC, BrowserSigner

    rpc = BrowserRPC(url)
    e = Env(try_prefetch_state, fast_mode_enabled)
    e.fork_rpc(rpc, *args, **kwargs)
    return set_env(e)


def reset_env():
    set_env(Env())


def _breakpoint(computation):
    BoaDebug(computation).start()


patch_opcode(0xA6, _breakpoint)


@contextlib.contextmanager
def reverts(*args, **kwargs):
    try:
        yield
        raise ValueError("Did not revert")
    except BoaError as b:
        if args or kwargs:
            check_boa_error_matches(b, *args, **kwargs)


def eval(code):
    return loads("").eval(code)


def _jupyter_server_extension_points() -> list[dict]:
    """
    Returns a list of dictionaries with metadata describing
    where to find the `_load_jupyter_server_extension` function.
    """
    return [{"module": "boa.integrations.jupyter"}]
