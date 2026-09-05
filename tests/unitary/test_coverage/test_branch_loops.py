"""Branch coverage tests for if/else inside for loops.

Tests for break, continue, backedge detection, nested loops,
terminal iteration, and loop-body tail statements.
"""

import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from .conftest import _check_branch_coverage, _check_full_branch_coverage


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


@pytest.mark.parametrize("keyword", ["break", "continue"])
def test_branch_compound_condition_break_continue(keyword):
    """Compound condition (and) with break/continue — both arcs covered."""
    source = f"""\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if (x != 2) and (x >= 25):
            {keyword}
        s += x
    return s
"""
    missing = _check_branch_coverage(source, lambda c: (c.f([25]), c.f([0])))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_in_for_loop_single_false():
    """Single element, false only — the false arc must still be recorded.

    foo([1]) → single iteration, false branch only. The false arc on loop
    exit must be recorded.
    """
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

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo([1])
    )
    # False arc (if_line → for_line) should be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        for_node.lineno in executed[if_node.lineno]
    ), f"False arc to for-header {for_node.lineno} not executed: {executed}"
    # False arc must NOT appear in missing
    assert for_node.lineno not in missing.get(
        if_node.lineno, []
    ), f"False arc to {for_node.lineno} should not be missing: {missing}"


def test_branch_if_else_in_for_loop():
    """if/else inside a for loop — both branches hit, no missing arcs."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
        else:
            total += 1
    return total
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    false_target = if_node.orelse[0].lineno
    expected_possible = {(if_node.lineno, true_target), (if_node.lineno, false_target)}

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo([10, 1])
    )
    assert possible == expected_possible, f"Possible: {possible}"
    assert missing == {}, f"Missing: {missing}"
    # No extraneous executed targets beyond what the reporter declares
    executed_targets = set(executed.get(if_node.lineno, []))
    assert executed_targets == {
        true_target,
        false_target,
    }, f"Expected executed targets {{{true_target}, {false_target}}}, got {executed_targets}"


def test_branch_if_else_in_for_loop_partial():
    """if/else in for loop, only true branch hit — else arc missing."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
        else:
            total += 1
    return total
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    false_target = if_node.orelse[0].lineno

    missing = _check_branch_coverage(source, lambda c: c.foo([10]))
    assert missing == {
        if_node.lineno: [false_target]
    }, f"Unexpected missing arcs: {missing}"


SOURCE_NESTED_LOOP_IF = """\
@external
def foo(a: DynArray[DynArray[uint256,4],4]) -> uint256:
    s: uint256 = 0
    for row: DynArray[uint256,4] in a:
        for v: uint256 in row:
            if v > 3:
                s += v
    return s
"""


def test_correctness_nested_loop_if_false_then_true():
    """Nested-loop if (no else), false-then-true order — both branches hit."""
    missing = _check_branch_coverage(SOURCE_NESTED_LOOP_IF, lambda c: c.foo([[1, 5]]))
    assert missing == {}, f"false-then-true missing arcs: {missing}"


def test_branch_nested_if_in_for_body_with_tail():
    """Nested if (no else) inside for body, with tail — all branches covered."""
    source = """\
@external
def foo(arr: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in arr:
        if x > 10:
            if x > 20:
                s += 3
        s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([25, 15, 5]))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_true_branch_is_for_nonempty():
    """If true branch is a For loop with iterations — both branches hit."""
    source = """\
@external
def foo(flag: bool, data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    if flag:
        for v: uint256 in data:
            s += v
    else:
        s += 1
    return s
"""
    missing = _check_branch_coverage(
        source, lambda c: (c.foo(True, [1, 2, 3]), c.foo(False, []))
    )
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if_in_for_inner_false_only():
    """Nested if in for body, only false (loop-back) path taken.
    Must report true branch as missing, not false-positive full coverage."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 100:
            total += val
        total += 1
    return total
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([1, 2, 3]))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    # Only false path taken — true arc (if → body) must be missing
    assert (
        if_node.lineno in missing
    ), f"Expected if line {if_node.lineno} in missing: {missing}"
    assert (
        true_target in missing[if_node.lineno]
    ), f"Expected true target {true_target} missing from line {if_node.lineno}: {missing}"


# --- no-op body (pass / assert True) in loops ---


def test_branch_loop_else_pass_both():
    """In-loop if/else where else is pass — both branches hit."""
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            s += 2
        else:
            pass
        s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.f([10, 1]))
    assert missing == {}, f"Missing branch arcs: {missing}"
