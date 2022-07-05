from typing import Union

from vyper.compiler.phases import CompilerData

from boa.contract import VyperContract, VyperFactory

_Contract = Union[VyperContract, VyperFactory]


def load(filename: str, *args, **kwargs) -> _Contract:  # type: ignore
    with open(filename) as f:
        return loads(f.read(), *args, **kwargs)


def loads(source_code: str, *args, as_factory=False, **kwargs) -> _Contract:  # type: ignore
    data = CompilerData(source_code, no_optimize=True)
    if as_factory:
        return VyperFactory(data, **kwargs)
    else:
        return VyperContract(data, *args, **kwargs)


def contract() -> _Contract:
    # returns an empty contract
    return loads("")
