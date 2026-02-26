import os
import tempfile

import coverage
import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

import boa
from boa.environment import Env
from boa.interpret import _disk_cache, set_cache_dir


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path):
    saved = _disk_cache.cache_dir
    try:
        set_cache_dir(tmp_path)
        yield
    finally:
        set_cache_dir(saved)


@pytest.fixture(scope="module")
def external_contract():
    source_code = """
@external
@view
def foo(a: uint256) -> uint256:
    return a * a
"""
    return boa.loads(source_code, name="ExternalContract")


@pytest.fixture(scope="module")
def source_contract(external_contract):
    source_code = """
interface Foo:
    def foo(a: uint256) -> uint256: view

FOO: immutable(address)

@deploy
def __init__(_foo_address: address):
    FOO = _foo_address

@external
@view
def bar(b: uint256) -> uint256:
    c: uint256 = staticcall Foo(FOO).foo(b)
    return c
"""
    return boa.loads(source_code, external_contract.address, name="TestContract")


def test_sub_computations(source_contract):
    boa.env._coverage_enabled = True
    source_contract.bar(10)


# --- in-process branch coverage helper ---


def _check_branch_coverage(vyper_source, calls_fn):
    """Run branch coverage in-process and return missing_branch_arcs.

    Args:
        vyper_source: Vyper source code string
        calls_fn: callable(contract) that exercises the contract

    Returns:
        dict of {line: [target_lines]} for missing branch arcs
    """
    saved_coverage = Env._coverage_enabled
    fd, vy_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(vyper_source)

        cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(vy_path)
            calls_fn(c)
        finally:
            cov.stop()

        analysis = cov._analyze(vy_path)
        return dict(analysis.missing_branch_arcs())
    finally:
        Env._coverage_enabled = saved_coverage
        os.unlink(vy_path)


# --- branch coverage tests ---


def test_branch_simple_if_else():
    """Both branches of a simple if/else are hit."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_without_else():
    """Both branches of an if without explicit else are hit."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        self.x = val
    self.x = 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if():
    """Both branches of nested if statements are fully covered."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
        else:
            return 2
    else:
        return 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_in_for_loop():
    """Branch inside a for loop is fully covered across iterations."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
    return total
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([1, 10, 3, 20]))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_in_for_loop_partial():
    """Only true branch taken in for loop — false branch must be missing."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
    return total
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([10]))
    # Derive expected lines from AST so the assertion survives source edits
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    for_node = if_node.get_ancestor(vy_ast.For)
    assert missing == {
        if_node.lineno: [for_node.lineno]
    }, f"Unexpected missing arcs: {missing}"


def test_branch_multiline_condition():
    """Multi-line if condition: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10, 20), c.foo(1, 1)))
    assert missing == {}, f"Missing branch arcs: {missing}"
