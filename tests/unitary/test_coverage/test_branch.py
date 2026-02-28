import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

import boa

from .conftest import (
    _check_branch_coverage,
    _check_full_branch_coverage,
    _coverage_session,
    _coverage_session_multi,
)


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


def test_branch_multiline_then_same_operator_no_missing_lines():
    """Regression: multi-line if followed by another if using the same operator.

    Operator AST nodes (Gt, Lt, etc.) carry stale linenos from the first
    occurrence in the file. Without filtering them out, the second if's Gt
    node (with stale lineno pointing to line 3) causes line 3 to disappear
    from the coverable set, creating phantom uncovered lines.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    if x > 20:
        return 2
    return 0
"""
    with _coverage_session(
        source,
        lambda c: (
            c.foo(10, 20),  # true branch of first if
            c.foo(1, 1),  # false branch of first if
            c.foo(25, 1),  # true branch of second if (false on first)
            c.foo(1, 1),  # false branch of second if
        ),
    ) as analysis:
        assert not analysis.missing, (
            f"No lines should be missing when all branches are hit, "
            f"got missing lines: {analysis.missing}"
        )


def test_branch_multiline_condition_no_missing_lines():
    """Multi-line if condition: continuation lines must not appear as uncovered.

    Regression test — the tracer collapses If.test nodes to the If line,
    so the reporter must exclude continuation lines from statements.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    with _coverage_session(source, lambda c: (c.foo(10, 20), c.foo(1, 1))) as analysis:
        assert not analysis.missing, (
            f"No lines should be missing when both branches are hit, "
            f"got missing lines: {analysis.missing}"
        )


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
    callee_source = """\
@external
def bar(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    caller_source = """\
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

    def setup(paths):
        callee = boa.load(paths["callee"])
        caller = boa.load(paths["caller"], callee.address)
        caller.call_bar(10)
        caller.call_bar(1)

    with _coverage_session_multi(
        {"callee": callee_source, "caller": caller_source}, setup
    ) as (cov, paths):
        analysis = cov._analyze(paths["callee"])
        missing = dict(analysis.missing_branch_arcs())
        assert missing == {}, f"Callee missing branch arcs: {missing}"


# --- if-in-for terminal iteration false branch ---


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


# --- if-without-else at function end ---


def test_branch_if_without_else_at_function_end():
    """if-without-else with trailing return — both arcs covered.

    The false branch falls through to `return 0` (next sibling).
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_without_else_at_function_end_partial():
    """Only true branch hit — false arc (to next sibling) must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # The false arc should target `return 0` (the next sibling)
    return_0 = ast.get_descendants(vy_ast.Return)[-1]
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"
    assert (
        return_0.lineno in missing[if_node.lineno]
    ), f"Expected false arc to {return_0.lineno}, got {missing}"


def test_branch_void_function_if_last_statement():
    """Void function where if is the last statement — false arc is implicit return.

    Regression test for _false_arc using parent.body instead of
    get_children() which would pick up decorator nodes.
    """
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_void_function_if_last_statement_partial():
    """Only true branch hit in void function — false arc (implicit return) missing."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    # False arc targets fn_node.lineno (implicit return)
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"
    assert (
        fn_node.lineno in missing[if_node.lineno]
    ), f"Expected false arc to fn_line {fn_node.lineno}, got {missing}"


def test_branch_if_in_orelse_without_else():
    """if inside an else block with no else of its own — both arcs covered.

    Regression test for _false_arc sibling lookup: the inner if lives in
    parent.orelse, not parent.body, so the sibling search must check both.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 0:
        return 1
    else:
        if y > 0:
            return 2
        return 3
"""
    missing = _check_branch_coverage(
        source, lambda c: (c.foo(1, 0), c.foo(0, 1), c.foo(0, 0))
    )
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- if-else inside for loop ---


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


def test_untaken_branch_lines_are_missing():
    """Entering a function must not mark untaken branch body lines as covered.

    Regression: old boa's FunctionDef span inflation marked every line in a
    function as covered when the function was entered, regardless of which
    branches were actually taken.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _coverage_session(source, lambda c: c.foo(10)) as analysis:
        ast = parse_to_ast(source)
        if_node = ast.get_descendants(vy_ast.If)[0]
        else_line = if_node.orelse[0].lineno
        # Only true branch hit — else body must be in missing
        assert else_line in analysis.missing, (
            f"Untaken else-body line {else_line} should be missing. "
            f"Executed: {sorted(analysis.executed)}, Missing: {sorted(analysis.missing)}"
        )


def test_pass_only_function_lines():
    """A pass-only function: `pass` is coverable but never hit at runtime.

    Bytecode for `pass` maps to the FunctionDef node, which _collapse_cov_node
    filters out. So even after calling foo(), the pass line is never traced.
    """
    source = """\
@external
def foo():
    pass

@external
def bar(x: uint256) -> uint256:
    return x
"""
    with _coverage_session(source, lambda c: (c.foo(), c.bar(42))) as analysis:
        ast = parse_to_ast(source)
        fn_bar = next(
            f for f in ast.get_descendants(vy_ast.FunctionDef) if f.name == "bar"
        )
        bar_return_line = fn_bar.body[0].lineno
        # bar's return line should be executed
        assert bar_return_line in analysis.executed, (
            f"bar's return line {bar_return_line} should be executed. "
            f"Executed: {sorted(analysis.executed)}"
        )

        fn_foo = next(
            f for f in ast.get_descendants(vy_ast.FunctionDef) if f.name == "foo"
        )
        pass_line = fn_foo.body[0].lineno
        # pass compiles to FunctionDef bytecode which is filtered — it should be missing
        assert pass_line in analysis.missing, (
            f"pass line {pass_line} should be in missing (FunctionDef filtered). "
            f"Executed: {sorted(analysis.executed)}, Missing: {sorted(analysis.missing)}"
        )


def test_branch_multiline_body_statement():
    """Multiline assignment in if-body: both branches hit, no missing arcs.

    Regression: the reporter's arc target must match the line the tracer
    reports first. For multi-line statements the compiler generates expression
    bytecode before the store, so the first traced line is the value's line
    — not the keyword/variable line.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        y: uint256 = (
            x +
            1
        )
        return y
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_body_statement_partial():
    """Multiline assignment in if-body, only false branch hit."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        y: uint256 = (
            x +
            1
        )
        return y
    else:
        return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # True arc target is the statement line (AnnAssign line)
    stmt_line = if_node.body[0].lineno

    missing = _check_branch_coverage(source, lambda c: c.foo(1))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert (
        stmt_line in missing[if_node.lineno]
    ), f"Expected true arc to stmt line {stmt_line}, got {missing}"


def test_branch_multiline_return_in_body():
    """Multiline return in if-body: both branches hit, no missing arcs.

    Regression: `return (\\n    expr\\n)` — the return keyword line has no
    bytecode, the tracer reports the expression line. Arc target must match.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_return_in_else():
    """Multiline return in else-body: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return (
            x + 1
        )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_assert_in_body():
    """Multiline assert in if-body: both branches hit, no missing arcs.

    Assert has `.test` not `.value` — _bytecode_lineno must check both.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        assert (
            x < 100
        )
        return x
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_return_in_body_with_else():
    """Regression: multiline return in true branch with explicit else.

    The ghost-If heuristic in _normalize_if_arcs must not drop a
    legitimate If when preamble alias nodes precede the body.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


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


# --- correctness regression tests ---


SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH = """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        return (
            x + 1
        )
    else:
        y = x
    return y
"""


def test_correctness_multiline_return_else_fallthrough_both():
    """P1 regression: multiline return in true body + else fallthrough.

    The preamble stripping must not drop the true arc when the else arm
    falls through (doesn't return).
    """
    missing = _check_branch_coverage(
        SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH, lambda c: (c.foo(10), c.foo(1))
    )
    assert missing == {}, f"Both branches hit, expected no missing arcs: {missing}"


def test_correctness_multiline_return_else_fallthrough_true_only():
    """True-only: true arc must be executed, false arc must be missing."""
    ast = parse_to_ast(SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH, lambda c: c.foo(10)
    )
    # True arc should be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    # False arc should be missing
    assert (
        if_node.lineno in missing
    ), f"If-line {if_node.lineno} not in missing: {missing}"


def test_correctness_multiline_return_else_fallthrough_false_only():
    """False-only: false arc must be executed, true arc must be missing."""
    ast = parse_to_ast(SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH, lambda c: c.foo(1)
    )
    orelse_line = if_node.orelse[0].lineno
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        orelse_line in executed[if_node.lineno]
    ), f"False arc to {orelse_line} not in executed: {executed}"
    assert (
        if_node.lineno in missing
    ), f"If-line {if_node.lineno} not in missing: {missing}"


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


SOURCE_ELIF_NO_ELSE = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    return 0
"""


def test_correctness_elif_no_else_all_branches():
    """P1 regression: if/elif without explicit else, fallthrough tail.

    When all three paths are exercised (outer true, inner true, both false),
    no branches should be missing.  Previously the inner elif's false arc
    was dropped because the compiler's outer-If re-evaluation was not
    ghost-removed (ghost was restricted to For-loop parents).
    """
    missing = _check_branch_coverage(
        SOURCE_ELIF_NO_ELSE, lambda c: (c.foo(25), c.foo(15), c.foo(5))
    )
    assert missing == {}, f"All branches hit, expected no missing: {missing}"


def test_correctness_elif_no_else_inner_false():
    """Inner elif false branch alone must produce the fallthrough arc."""
    ast = parse_to_ast(SOURCE_ELIF_NO_ELSE)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # the elif

    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_ELIF_NO_ELSE, lambda c: c.foo(5)
    )
    # Inner elif must have its false arc (to return 0) executed
    inner_targets = set(executed.get(inner_if.lineno, []))
    # The false fallthrough target is `return 0` at inner_if.end_lineno + 1
    assert (
        len(inner_targets) > 0
    ), f"Inner elif@L{inner_if.lineno} should have executed arcs: {executed}"


def test_correctness_elif_no_else_multiline_tail():
    """elif fallthrough to multiline return must target the statement line.

    _false_arc uses stmt.lineno, and the tracer normalizes multiline entries
    to match, so the reporter's possible arc matches the tracer's executed arc.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    return (
        x + 1
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"All branches hit, expected no missing: {missing}"


def test_branch_multiline_augassign_in_else():
    """Multiline AugAssign in else-body: both branches hit, no missing arcs.

    Regression: AugAssign compiles with a target-variable load first,
    so the tracer reports stmt.lineno, not value.lineno.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    s: uint256 = 0
    if x > 5:
        s += 1
    else:
        s += (
            x +
            1
        )
    return s
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


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


# --- multiline no-else / elif-tail regression tests ---


def test_branch_no_else_multiline_true_return_multiline_tail():
    """If without else, multiline return in true body + multiline tail return.

    Regression: compiler emits tail-statement setup bytecode as alias
    nodes between the If condition evaluations.  The normalization must
    identify these as trailing aliases and not attribute them as the
    branch entry arc target.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    return (
        x + 2
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_no_else_multiline_true_return_multiline_tail_partial():
    """Partial: only true branch hit — false arc (to tail) must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    return (
        x + 2
    )
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    tail_return = ast.get_descendants(vy_ast.Return)[-1]

    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert (
        tail_return.lineno in missing[if_node.lineno]
    ), f"Expected false arc to tail return {tail_return.lineno}, got {missing}"


def test_branch_no_else_multiline_assign_multiline_tail():
    """If without else, multiline assign in true body + multiline tail return.

    Regression: similar to the return case but with Assign instead of Return.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    s: uint256 = 0
    if x > 5:
        s = (
            x + 1
        )
    return (
        s + 1
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_elif_no_else_multiline_body_multiline_tail():
    """if/elif without else, multiline elif body + multiline tail.

    Regression: the inner elif's false arc targets the tail statement
    after the outer block.  Both the elif true arc and the fallthrough
    false arc must match the reporter's declared targets.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return (
            x + 2
        )
    return (
        x + 1
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_elif_no_else_multiline_tail_partial():
    """Only outer-true hit — inner elif arcs must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return (
            x + 2
        )
    return (
        x + 1
    )
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # elif

    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    assert (
        inner_if.lineno in missing
    ), f"Expected elif {inner_if.lineno} in missing: {missing}"
    assert (
        len(missing[inner_if.lineno]) == 2
    ), f"Expected 2 missing arcs from elif, got {missing[inner_if.lineno]}"


# --- nested if without outer else ---


def test_branch_nested_if_no_outer_else():
    """Inner if (no else) last in outer if body (no outer else).

    Regression: compiler re-evaluates the outer If after the inner If's
    false branch, producing spurious arcs (inner → outer) and losing
    the inner false arc (inner → return 0).
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if_no_outer_else_exact_arcs():
    """Verify exact executed arcs for nested if without outer else."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: (c.foo(25), c.foo(15), c.foo(5))
    )
    assert missing == {}, f"Missing: {missing}"
    # Outer if: true → inner if line, false → return 0
    outer_targets = set(executed.get(outer_if.lineno, []))
    assert outer_targets == {
        inner_if.lineno,
        6,
    }, f"Outer executed targets: {outer_targets}"
    # Inner if: true → return 3, false → return 0
    inner_targets = set(executed.get(inner_if.lineno, []))
    assert inner_targets == {5, 6}, f"Inner executed targets: {inner_targets}"


def test_branch_nested_if_no_outer_else_partial():
    """Only inner-true hit — outer-false and inner-false must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    tail = ast.get_descendants(vy_ast.Return)[-1]

    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    # Outer false arc (to return 0) should be missing
    assert outer_if.lineno in missing, f"Outer if should be in missing: {missing}"
    assert (
        tail.lineno in missing[outer_if.lineno]
    ), f"Expected outer false arc to {tail.lineno}: {missing}"
    # Inner false arc (to return 0) should be missing
    assert inner_if.lineno in missing, f"Inner if should be in missing: {missing}"
    assert (
        tail.lineno in missing[inner_if.lineno]
    ), f"Expected inner false arc to {tail.lineno}: {missing}"


def test_branch_if_in_orelse_no_inner_else_exact_arcs():
    """If inside else block (orelse), no inner else — no extra synthetic arcs.

    Regression: executed_branch_arcs showed extra arc to outer if line
    (inner → outer) in addition to logical targets.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 0:
        return 1
    else:
        if y > 0:
            return 2
    return 3
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: (c.foo(1, 0), c.foo(0, 1), c.foo(0, 0))
    )
    assert missing == {}, f"Missing: {missing}"
    # Inner if should have exactly {return 2, return 3} — no extra arcs
    inner_targets = set(executed.get(inner_if.lineno, []))
    expected_inner = {inner_if.body[0].lineno, 8}  # return 2, return 3
    assert (
        inner_targets == expected_inner
    ), f"Inner if executed targets: {inner_targets}, expected {expected_inner}"


# --- nested if inside for body ---


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


# --- if without else + tail statement (post-body re-evaluation) ---


def test_branch_if_no_else_with_tail_true_only():
    """True-only: false arc (to tail) must be missing.

    Regression: compiler re-evaluates the If condition after the true
    body as a jump target, producing a spurious false arc when only the
    true branch was exercised.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        y += 1
    y += 2
    return y
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    # True arc should be executed, false arc should be missing
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert set(executed[if_node.lineno]) == {
        if_node.body[0].lineno
    }, f"Only true arc should be executed: {executed}"
    assert if_node.lineno in missing, f"If-line not in missing: {missing}"


def test_branch_if_no_else_with_tail_both():
    """Both branches hit — no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        y += 1
    y += 2
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


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
