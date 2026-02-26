import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

import boa
from boa.environment import Env

from .conftest import _check_branch_coverage, _check_full_branch_coverage


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


# --- branch negative controls (partial coverage) ---


def test_branch_simple_if_else_partial():
    """Only true branch hit — false arc must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    else_first = if_node.orelse[0]
    assert missing == {
        if_node.lineno: [else_first.lineno]
    }, f"Unexpected missing arcs: {missing}"


def test_branch_if_without_else_partial():
    """Only true branch hit — fallthrough (false) arc must be missing."""
    source = """\
@external
def foo(val: uint256) -> uint256:
    if val > 5:
        return val
    return 0
"""
    # Only call with val=10 → true branch returns, fallthrough not taken
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # The false arc for if-without-else: next sibling is `return 0`
    return_0 = ast.get_descendants(vy_ast.Return)[-1]
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"
    assert (
        return_0.lineno in missing[if_node.lineno]
    ), f"Expected false arc to {return_0.lineno}, got {missing}"


def test_branch_nested_if_partial():
    """Only outer-true + inner-true hit — outer-false and inner-false missing."""
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
    # Only call with x=25 → outer true, inner true
    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    # outer-false arc should target the else body line (`return 1`)
    outer_else_line = outer_if.orelse[0].lineno
    assert outer_if.lineno in missing, f"Expected outer if {outer_if.lineno} in missing"
    assert (
        outer_else_line in missing[outer_if.lineno]
    ), f"Expected outer false target {outer_else_line} in {missing[outer_if.lineno]}"
    # inner-false arc should target the inner else body line (`return 2`)
    inner_else_line = inner_if.orelse[0].lineno
    assert inner_if.lineno in missing, f"Expected inner if {inner_if.lineno} in missing"
    assert (
        inner_else_line in missing[inner_if.lineno]
    ), f"Expected inner false target {inner_else_line} in {missing[inner_if.lineno]}"


def test_branch_multiline_condition_partial():
    """Only true branch hit for multi-line condition — false arc missing."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 20))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    else_first = if_node.orelse[0]
    assert missing == {
        if_node.lineno: [else_first.lineno]
    }, f"Unexpected missing arcs: {missing}"


# --- full arc assertion (possible + executed + missing) ---


def test_full_arcs_simple_if_else():
    """Assert exact possible, executed, and missing arcs for simple if/else."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    false_target = if_node.orelse[0].lineno
    expected_possible = {(if_node.lineno, true_target), (if_node.lineno, false_target)}

    # Exercise both branches
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: (c.foo(10), c.foo(1))
    )
    assert possible == expected_possible, f"Possible: {possible}"
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert set(executed[if_node.lineno]) == {
        true_target,
        false_target,
    }, f"Executed: {executed}"
    assert missing == {}, f"Missing: {missing}"


def test_full_arcs_for_loop_if():
    """Assert all three arc sets for an if inside a for loop."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
    return total
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    for_node = if_node.get_ancestor(vy_ast.For)
    true_target = if_node.body[0].lineno
    false_target = for_node.lineno  # last in for body → loop back

    expected_possible = {(if_node.lineno, true_target), (if_node.lineno, false_target)}

    # Only true branch → false arc missing
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo([10])
    )
    assert possible == expected_possible, f"Possible: {possible}"
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert set(executed[if_node.lineno]) == {true_target}, f"Executed: {executed}"
    assert if_node.lineno in missing, f"If-line not in missing: {missing}"
    assert set(missing[if_node.lineno]) == {false_target}, f"Missing: {missing}"


# --- elif coverage ---


def test_branch_elif_full():
    """if/elif/else — all three paths hit → no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    else:
        return 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_elif_only_first():
    """Only if-true path hit — elif-true and elif-false (else) arcs missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    else:
        return 1
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # elif is a nested If in orelse
    # When only the outer-if-true is hit, the elif condition is never evaluated
    # so both elif arcs (true → return 2, false → return 1) should be missing
    assert (
        inner_if.lineno in missing
    ), f"Expected elif {inner_if.lineno} in missing: {missing}"
    assert (
        len(missing[inner_if.lineno]) == 2
    ), f"Expected 2 missing arcs from elif, got {missing[inner_if.lineno]}"


def test_branch_elif_only_middle():
    """Only elif path hit — if-true and else arcs missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    else:
        return 1
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(15))
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    # outer-if true arc (to `return 3`) should be missing
    outer_true_line = outer_if.body[0].lineno
    assert outer_if.lineno in missing, f"Expected outer if {outer_if.lineno} in missing"
    assert (
        outer_true_line in missing[outer_if.lineno]
    ), f"Expected outer true target {outer_true_line} in {missing[outer_if.lineno]}"
    # elif false arc (to `return 1`) should be missing
    elif_else_line = inner_if.orelse[0].lineno
    assert inner_if.lineno in missing, f"Expected elif {inner_if.lineno} in missing"
    assert (
        elif_else_line in missing[inner_if.lineno]
    ), f"Expected elif false target {elif_else_line} in {missing[inner_if.lineno]}"


# --- control flow exits in branches ---


def test_branch_if_with_early_return():
    """if body returns early, else falls through; both paths hit → no missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    result: uint256 = 0
    if x > 5:
        return 1
    else:
        result = x + 1
    return result
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_with_break():
    """if with break: true branch (break) is covered when break is hit."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val == 0:
            break
        total += val
    return total
"""
    possible, executed, _ = _check_full_branch_coverage(
        source, lambda c: c.foo([1, 2, 0, 99])
    )
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    # The if-line must appear in possible arcs (reporter sees it)
    assert any(
        f == if_node.lineno for f, t in possible
    ), f"If-line {if_node.lineno} not in possible arcs: {possible}"
    # True arc (if → break) must be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        true_target in executed[if_node.lineno]
    ), f"True arc to {true_target} not executed: {executed}"


def test_branch_if_with_continue():
    """if with continue: true branch (continue) is covered when continue is hit."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            continue
        total += val
    return total
"""
    possible, executed, _ = _check_full_branch_coverage(
        source, lambda c: c.foo([1, 10, 3, 20])
    )
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    # The if-line must appear in possible arcs
    assert any(
        f == if_node.lineno for f, t in possible
    ), f"If-line {if_node.lineno} not in possible arcs: {possible}"
    # True arc (if → continue) must be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        true_target in executed[if_node.lineno]
    ), f"True arc to {true_target} not executed: {executed}"


def test_branch_break_partial():
    """Only break path taken — both arcs should be missing since
    the false-branch fallthrough isn't distinctly traced."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val == 0:
            break
        total += val
    return total
"""
    # Only pass [0] — break immediately, false branch never hit
    missing = _check_branch_coverage(source, lambda c: c.foo([0]))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"


# --- multi-contract / cross-contract coverage ---


def test_branch_cross_contract():
    """Arcs from a called contract are attributed to the callee's file."""
    import os
    import tempfile

    import coverage

    callee_source = """\
@external
def bar(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    caller_source_template = """\
interface Callee:
    def bar(x: uint256) -> uint256: nonpayable

CALLEE: immutable(address)

@deploy
def __init__(callee_addr: address):
    CALLEE = callee_addr

@external
def call_bar(x: uint256) -> uint256:
    return extcall Callee(CALLEE).bar(x)
"""
    saved_coverage = Env._coverage_enabled
    fd1, callee_path = tempfile.mkstemp(suffix=".vy")
    fd2, caller_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd1, "w") as f:
            f.write(callee_source)
        with os.fdopen(fd2, "w") as f:
            f.write(caller_source_template)

        cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            callee = boa.load(callee_path)
            caller = boa.load(caller_path, callee.address)
            # Exercise both branches of callee through caller
            caller.call_bar(10)
            caller.call_bar(1)
        finally:
            cov.stop()

        # Callee's arcs should be fully covered
        callee_analysis = cov._analyze(callee_path)
        callee_missing = dict(callee_analysis.missing_branch_arcs())
        assert callee_missing == {}, f"Callee missing branch arcs: {callee_missing}"
    finally:
        Env._coverage_enabled = saved_coverage
        os.unlink(callee_path)
        os.unlink(caller_path)
