"""Branch coverage tests for if/else inside for loops.

Tests for break, continue, backedge detection, nested loops,
terminal iteration, and loop-body tail statements.
"""

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


def test_branch_compound_condition_break():
    """Compound condition (and) with break — decision JUMPI is unmapped.

    Regression: _find_if_jumpi picked up the short-circuit JUMPI from
    the `and` instead of the actual break-decision JUMPI.
    """
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if (x != 2) and (x >= 25):
            break
        s += x
    return s
"""
    missing = _check_branch_coverage(source, lambda c: (c.f([25]), c.f([0])))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_compound_condition_continue():
    """Compound condition (and) with continue — decision JUMPI is unmapped."""
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if (x != 2) and (x >= 25):
            continue
        s += x
    return s
"""
    missing = _check_branch_coverage(source, lambda c: (c.f([25]), c.f([0])))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_in_for_loop_terminal_false():
    """Terminal iteration false branch: true then false on last iteration.

    foo([10, 1]) → first iteration true (10 > 5), second iteration false
    (1 > 5). The false arc on the terminal iteration exits the loop to a
    different line, so standard backedge detection misses it.
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
    missing = _check_branch_coverage(source, lambda c: c.foo([10, 1]))
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
    """if/else inside a for loop — both branches hit, no missing arcs.

    Regression: ghost loop-exit If re-evaluations produced spurious arcs
    (e.g. if_line -> post-loop return) that made executed_branch_arcs
    inconsistent with reporter possibilities.
    """
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


def test_branch_for_loop_if_no_else_both_orders():
    """Regression: for-loop if (no else), false arc detected in both orders.

    false-then-true ([1, 10]) and true-then-false ([10, 1]) must both
    produce correct arcs. The backedge detection must handle both orderings.
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
    # Each order alone should report the untaken branch
    missing_ft = _check_branch_coverage(source, lambda c: c.foo([1, 10]))
    assert missing_ft == {}, f"false-then-true missing arcs: {missing_ft}"

    missing_tf = _check_branch_coverage(source, lambda c: c.foo([10, 1]))
    assert missing_tf == {}, f"true-then-false missing arcs: {missing_tf}"


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
    """P1 regression: nested-loop if (no else) order-independent coverage.

    foo([[1,5]]) exercises false-then-true. Both branches are hit, so
    no arcs should be missing.
    """
    missing = _check_branch_coverage(SOURCE_NESTED_LOOP_IF, lambda c: c.foo([[1, 5]]))
    assert missing == {}, f"false-then-true missing arcs: {missing}"


def test_correctness_nested_loop_if_true_then_false():
    """Same as above, true-then-false order. Must also have no missing arcs."""
    missing = _check_branch_coverage(SOURCE_NESTED_LOOP_IF, lambda c: c.foo([[5, 1]]))
    assert missing == {}, f"true-then-false missing arcs: {missing}"


def test_correctness_nested_loop_if_order_parity():
    """Both orderings must produce identical coverage results."""
    source = SOURCE_NESTED_LOOP_IF
    ft = _check_full_branch_coverage(source, lambda c: c.foo([[1, 5]]))
    tf = _check_full_branch_coverage(source, lambda c: c.foo([[5, 1]]))
    assert ft[0] == tf[0], f"Possible arcs differ: {ft[0]} vs {tf[0]}"
    assert ft[1] == tf[1], f"Executed arcs differ: {ft[1]} vs {tf[1]}"
    assert ft[2] == tf[2], f"Missing arcs differ: {ft[2]} vs {tf[2]}"


def test_correctness_if_else_in_for_both():
    """If/else in for loop, both branches hit — no spurious arcs.

    The new preamble stripping eliminates a spurious arc to the For header
    that the old implementation produced. Only true and false arcs should
    be in the executed set.
    """
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

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo([10, 1])
    )
    assert missing == {}, f"Both branches hit, expected no missing: {missing}"
    executed_targets = set(executed.get(if_node.lineno, []))
    assert executed_targets == {
        true_target,
        false_target,
    }, f"Expected only true/false targets, got {executed_targets}"


def test_branch_multiline_return_in_for_loop():
    """Multiline return in true-branch inside for loop: no missing arcs.

    Regression: Return inside a for loop compiles with cleanup bytecode
    first, so the tracer reports Return.lineno, not value.lineno.
    """
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for v: uint256 in data:
        if v > 5:
            return (
                v + 1
            )
        else:
            s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo([10, 1]), c.foo([1])))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if_in_for_body_with_tail():
    """Nested if (no else) inside for body, followed by a tail statement.

    Regression: _false_arc walked up to the function level, skipping the
    for-body sibling.  Inner false arc should target the tail (s += 1),
    not the function return.
    """
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


def test_branch_nested_if_in_for_body_with_else_and_tail():
    """Nested if (no inner else) inside outer if/else in for body, with tail.

    Regression: same _false_arc walk-up issue — inner false should target
    the for-body tail statement (s += 1), not the function return.
    """
    source = """\
@external
def foo(arr: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in arr:
        if x > 10:
            if x > 20:
                s += 3
        else:
            s += 2
        s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([25, 15, 5]))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if_in_for_body_inner_false_arc_target():
    """Verify exact inner false arc target is the for-body tail, not fn return."""
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
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # if x > 20
    tail_stmt = ast.get_descendants(vy_ast.For)[0].body[-1]  # s += 1

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo([25, 15, 5])
    )
    assert missing == {}, f"Missing: {missing}"
    # Inner false arc should target tail_stmt (s += 1), not function return
    assert (inner_if.lineno, tail_stmt.lineno) in possible, (
        f"Expected possible arc ({inner_if.lineno}, {tail_stmt.lineno}), "
        f"possible: {possible}"
    )


def test_branch_if_no_else_in_for_with_tail_true_only():
    """True-only in loop: false arc must be missing.

    Regression: same post-body re-evaluation inside a for loop body.
    """
    source = """\
@external
def foo(arr: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in arr:
        if x > 10:
            s += 3
        s += 1
    return s
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo([25])
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert set(executed[if_node.lineno]) == {
        if_node.body[0].lineno
    }, f"Only true arc should be executed: {executed}"
    assert if_node.lineno in missing, f"If-line not in missing: {missing}"


def test_branch_if_no_else_in_for_with_tail_both():
    """Both branches hit in loop — no missing arcs."""
    source = """\
@external
def foo(arr: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in arr:
        if x > 10:
            s += 3
        s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([25, 1]))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_true_branch_is_for_empty():
    """If true branch is a For loop with zero iterations — both branches hit."""
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
        source, lambda c: (c.foo(True, []), c.foo(False, []))
    )
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_false_branch_is_for_empty():
    """If false (else) branch is a For loop with zero iterations — both branches hit."""
    source = """\
@external
def foo(flag: bool, data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    if flag:
        s += 1
    else:
        for v: uint256 in data:
            s += v
    return s
"""
    missing = _check_branch_coverage(
        source, lambda c: (c.foo(True, []), c.foo(False, []))
    )
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


def test_branch_if_true_branch_is_for_true_only():
    """If true branch is a For — only true path taken, false must be missing."""
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
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(True, [1, 2])
    )
    # Invariant: executed ⊆ possible
    for line, targets in executed.items():
        arc_set = {(line, t) for t in targets}
        assert (
            arc_set <= possible
        ), f"Executed arcs {arc_set} not subset of possible {possible}"
    # False branch must be missing
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    false_target = if_node.orelse[0].lineno
    assert if_node.lineno in missing, f"Expected if line {if_node.lineno} in missing"
    assert (
        false_target in missing[if_node.lineno]
    ), f"Expected false target {false_target} missing from line {if_node.lineno}"


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


def test_branch_nested_if_in_for_with_else_inner_false_only():
    """Nested if/else in for body, only else (false) path taken.
    Must report true branch as missing."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 100:
            total += val
        else:
            total += 1
    return total
"""
    missing = _check_branch_coverage(source, lambda c: c.foo([1, 2, 3]))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    # Only false (else) path taken — true arc must be missing
    assert (
        if_node.lineno in missing
    ), f"Expected if line {if_node.lineno} in missing: {missing}"
    assert (
        true_target in missing[if_node.lineno]
    ), f"Expected true target {true_target} missing from line {if_node.lineno}: {missing}"


# --- no-op body (pass / assert True) in loops ---


def test_branch_loop_else_pass_both():
    """In-loop if/else where else is pass — both branches hit.

    Regression: pass in else generated no bytecode, causing the
    decision JUMPI to be unmapped and no branch arcs recorded.
    """
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


def test_branch_loop_else_assert_true_both():
    """In-loop if/else where else is assert True — both branches hit."""
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            s += 2
        else:
            assert True
        s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.f([10, 1]))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_loop_else_pass_partial():
    """In-loop if/else where else is pass — one branch only."""
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
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f([10]))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


def test_branch_loop_if_pass_both():
    """In-loop if without else + pass body — both branches hit.

    Regression: pass body generates no bytecode, direction
    classifier could not find the true branch anchor.  Both arcs
    collapse to the same target (degenerate case).
    """
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            pass
        s += 1
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.f([10, 1]))
    assert missing == {}, f"Missing branch arcs: {missing}"
