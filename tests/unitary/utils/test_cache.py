from boa.interpret import _disk_cache, compiler_data


def test_cache_contract_name():
    code = """
x: constant(int128) = 1000
"""
    assert _disk_cache is not None
    test1 = compiler_data(code, "test1")
    test2 = compiler_data(code, "test2")
    assert (
        test1.__dict__ == compiler_data(code, "test1").__dict__
    ), "Should hit the cache"
    assert test1.__dict__ != test2.__dict__, "Should be different objects"
    assert test2.contract_name == "test2"
