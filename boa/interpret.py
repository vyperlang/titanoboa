from vyper.compiler.phases import CompilerData

from boa.contract import VyperContract


def load(filename: str, *args, **kwargs) -> VyperContract:  # type: ignore
    with open(filename) as f:
        return loads(f.read(), *args, **kwargs)


def loads(source_code: str, *args, **kwargs) -> VyperContract:  # type: ignore
    data = CompilerData(source_code, no_optimize=True)
    return VyperContract(data, *args, **kwargs)


def contract() -> VyperContract:
    # returns an empty contract
    return loads("")
