from vyper.compiler.phases import CompilerData

from boa.contract import VyperContract


def load(filename: str, *args, **kwargs) -> VyperContract:
    with open(filename) as f:
        data = CompilerData(f.read())

    return VyperContract(data, *args, **kwargs)
