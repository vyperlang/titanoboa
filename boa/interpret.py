from vyper.compiler.phases import CompilerData

from boa.contract import VyperContract


def load(filename: str, *args, **kwargs) -> VyperContract:  # type: ignore
    with open(filename) as f:
        return loads(f.read(), *args, **kwargs)

def loads(source_code: str, *args, **kwargs):
    data = CompilerData(source_code)
    return VyperContract(data, *args, **kwargs)

def contract():
    # returns an empty contract
    return loads("")
