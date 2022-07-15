from typing import Union

from vyper.compiler.phases import CompilerData

from boa.contract import VyperContract, VyperDeployer, VyperFactory

_Contract = Union[VyperContract, VyperFactory]


def load(filename: str, *args, **kwargs) -> _Contract:  # type: ignore
    with open(filename) as f:
        return loads(f.read(), *args, **kwargs)


def loads_partial(source_code: str) -> VyperDeployer:
    data = CompilerData(source_code)

    return VyperDeployer(data)


def load_partial(filename: str, *args, **kwargs) -> VyperDeployer:  # type: ignore
    with open(filename) as f:
        return loads_partial(f.read(), *args, **kwargs)


def loads(source_code: str, *args, as_factory=False, **kwargs) -> _Contract:  # type: ignore
    d = loads_partial(source_code)
    if as_factory:
        return d.deploy_as_factory(**kwargs)
    else:
        return d.deploy(*args, **kwargs)


def contract() -> _Contract:
    # returns an empty contract
    return loads("")
