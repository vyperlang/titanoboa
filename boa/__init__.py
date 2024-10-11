import contextlib
import sys

import boa.explorer
from boa.contracts.base_evm_contract import BoaError
from boa.contracts.vyper.vyper_contract import check_boa_error_matches
from boa.dealer import deal
from boa.debugger import BoaDebug
from boa.environment import Env
from boa.explorer import Etherscan, _set_etherscan, get_etherscan
from boa.interpret import (
    from_etherscan,
    load,
    load_abi,
    load_partial,
    load_vyi,
    loads,
    loads_abi,
    loads_partial,
    loads_vyi,
)
from boa.network import NetworkEnv
from boa.precompile import precompile
from boa.test.strategies import fuzz
from boa.util.open_ctx import Open
from boa.verifiers import get_verifier, set_verifier, verify
from boa.vm.py_evm import enable_pyevm_verbose_logging, patch_opcode

# turn off tracebacks if we are in repl
# https://stackoverflow.com/a/64523765
if hasattr(sys, "ps1"):  # pragma: no cover
    pass
    # sys.tracebacklimit = 0

env = Env.get_singleton()


@contextlib.contextmanager
def swap_env(new_env):
    with set_env(new_env):
        yield


def _set_env(new):
    global env
    env = new
    Env._singleton = new


def set_env(new_env):
    global env
    get_env = lambda: env  # noqa: E731
    return Open(get_env, _set_env, new_env)


def fork(
    url: str, block_identifier: int | str = "safe", allow_dirty: bool = False, **kwargs
):
    global env
    if env.evm.is_state_dirty and not allow_dirty:
        raise Exception(
            "Cannot fork with dirty state. Set allow_dirty=True to override."
        )

    new_env = Env()
    new_env.fork(url=url, block_identifier=block_identifier, deprecated=False, **kwargs)
    return set_env(new_env)


def set_browser_env(address=None):
    """Set the environment to use the browser's network in Jupyter/Colab"""
    # import locally because jupyter is generally not installed
    from boa.integrations.jupyter import BrowserEnv

    return set_env(BrowserEnv(address))


def set_network_env(url):
    """Set the environment to use a custom network URL"""
    return set_env(NetworkEnv.from_url(url))


def set_etherscan(*args, **kwargs):
    explorer = Etherscan(*args, **kwargs)
    return Open(get_etherscan, _set_etherscan, explorer)


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
