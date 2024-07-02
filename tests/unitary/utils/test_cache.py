from vyper.compiler import CompilerData

from boa.contracts.vyper.vyper_contract import VyperDeployer
from boa.interpret import _disk_cache, compiler_data


def test_cache_contract_name():
    code = """
x: constant(int128) = 1000
"""
    assert _disk_cache is not None
    test1 = compiler_data(code, "test1", __file__, VyperDeployer)
    test2 = compiler_data(code, "test2", __file__, VyperDeployer)
    test3 = compiler_data(code, "test1", __file__, VyperDeployer)
    assert _to_dict(test1) == _to_dict(test3), "Should hit the cache"
    assert _to_dict(test1) != _to_dict(test2), "Should be different objects"
    assert str(test2.contract_path) == "test2"


def _to_dict(data: CompilerData) -> dict:
    """
    Serialize the `CompilerData` object to a dictionary for comparison.
    """
    d = data.__dict__.copy()
    d["input_bundle"] = d["input_bundle"].__dict__.copy()
    d["input_bundle"]["_cache"] = d["input_bundle"]["_cache"].__dict__.copy()
    return d
