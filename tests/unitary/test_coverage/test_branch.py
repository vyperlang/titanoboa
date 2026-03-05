"""Core branch coverage tests.

Basic if/else, if-without-else, early return, void functions,
cross-contract, statement-only coverage, pass-only functions,
untaken branch lines, invariant checks, and tail-statement tests.

Loop-specific tests are in test_branch_loops.py.
Nested/elif tests are in test_branch_nested.py.
Multiline tests are in test_branch_multiline.py.
"""

import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

import boa

from .conftest import (
    _analyze,
    _check_branch_coverage,
    _check_full_branch_coverage,
    _coverage_session,
    _coverage_session_lines,
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
    from boa.environment import Env

    saved = Env._coverage_enabled
    try:
        Env._coverage_enabled = True
        source_contract.bar(10)
    finally:
        Env._coverage_enabled = saved


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


# --- full arc assertion (possible + executed + missing) ---

# --- control flow exits in branches ---

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
        analysis = _analyze(cov, paths["callee"])
        missing = dict(analysis.missing_branch_arcs())
        assert missing == {}, f"Callee missing branch arcs: {missing}"


# --- internal function called multiple times in one transaction ---


def test_branch_internal_call_both_directions():
    """Internal function called twice with different inputs in one tx — both arcs covered."""
    source = """\
@internal
def _check(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def foo(a: uint256, b: uint256) -> uint256:
    return self._check(a) + self._check(b)
"""
    # a=10 hits true, b=1 hits false — single call covers both
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 1))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_internal_call_same_direction():
    """Internal function called twice, same direction — partial coverage."""
    source = """\
@internal
def _check(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def foo(a: uint256, b: uint256) -> uint256:
    return self._check(a) + self._check(b)
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # Both calls take true branch — false arc should be missing
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 20))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


# --- internal call in If.test (condition helpers) ---


def test_branch_helper_condition_break_false_only():
    """for + break + helper condition, false-only must not report full coverage."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5

@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if self.gt5(x):
            break
        s += x
    return s
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f([1]))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only), got: {missing}"


def test_branch_helper_condition_both_branches():
    """Helper condition with both branches hit — no missing arcs."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5

@external
def f(x: uint256) -> uint256:
    if self.gt5(x):
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- if-without-else at function end ---


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
    """Void function where if is the last statement — false arc is implicit return."""
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


def test_untaken_branch_lines_are_missing():
    """Entering a function must not mark untaken branch body lines as covered."""
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
    """A pass-only function: `pass` generates no distinct bytecode, so it appears as uncovered."""
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


# --- if without else + tail statement (post-body re-evaluation) ---


def test_branch_if_no_else_with_tail_true_only():
    """if without else + tail statement, true-only: false arc must be missing."""
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


# --- invariant and decision engine tests ---

# --- no-op body (pass / assert True) ---


def test_branch_if_pass_body_both():
    """if with pass body — both branches hit (degenerate: arcs collapse)."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    y += 1
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_assert_true_body_both():
    """if with assert True body (constant-folded to noop) — both branches hit."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        assert True
    y += 1
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_both():
    """if/else where else is pass — both branches hit."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        pass
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_partial_true_only():
    """if/else where else is pass — only true hit, false arc missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        pass
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(10))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


SOURCE_ELSE_PASS_COMPOUND_AND = """\
@external
def f(x: uint256) -> uint256:
    if (x > 5) and (x < 20):
        return 1
    else:
        pass
    return 0
"""

SOURCE_ELSE_PASS_COMPLEX_OR_AND = """\
@external
def f(x: uint256) -> uint256:
    if ((x == 2) and (x > 5)) or (x == 3):
        return 1
    else:
        pass
    return 0
"""

# --- noop true body (pass/assert True in if body, non-noop else) ---


def test_branch_noop_true_body_full():
    """Noop true body (pass) with non-noop else — all branches covered."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
        return y
    return 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_noop_true_body_true_only():
    """Noop true body — only true branch hit, false should be missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
        return y
    return 1
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # True arc should be executed
    assert if_node.lineno in executed, f"Expected true arc: {executed}"
    # False arc (else body) should be missing
    assert if_node.lineno in missing, f"Expected missing false arc: {missing}"
    false_target = if_node.orelse[0].lineno
    assert (
        false_target in missing[if_node.lineno]
    ), f"Expected false arc to L{false_target}: {missing}"


def test_branch_compound_and_skip_gate_false_only():
    """Compound `and` condition, false-only: only the false arc should be reported."""
    source = """\
@external
def f(x: uint256, y: uint256) -> uint256:
    if (x > 5) and (y < 20):
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno

    # x=10, y=30 → x>5 True, y<20 False → false branch
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.f(10, 30)
    )
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only): {missing}"
    # The true arc must NOT be in executed arcs
    if if_node.lineno in executed:
        assert true_target not in executed[if_node.lineno], (
            f"True arc to L{true_target} should NOT be executed "
            f"(only false branch taken): {executed}"
        )


def test_branch_unknown_default_direction():
    """Both branches are bare returns (degenerate) — arcs still recorded."""
    source = """\
@external
def foo(x: uint256):
    if x > 5:
        return
    else:
        return
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]

    # Both arcs point to fn_line — this is the degenerate case.
    # Call with x=10 (true branch). The default fallback direction
    # determines if the recorded arc is from the "true" or "false"
    # classification.  Ensure at least one arc is executed.
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    # Both arcs are (if_line, fn_line), so both are always "covered"
    # regardless of direction, but the arc must actually be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        fn_node.lineno in executed[if_node.lineno]
    ), f"Expected arc to fn_line {fn_node.lineno} executed: {executed}"

    # Also verify with only the false branch (x=1)
    possible2, executed2, missing2 = _check_full_branch_coverage(
        source, lambda c: c.foo(1)
    )
    assert (
        if_node.lineno in executed2
    ), f"If-line {if_node.lineno} not in executed (false-only): {executed2}"


def test_branch_else_bare_return_both():
    """if ... else: return (bare return in void fn) — false branch targets fn entry."""
    source = """
result: public(uint256)

@external
def foo(x: uint256):
    if x > 5:
        self.result = x
    else:
        return
    self.result += 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}


def test_branch_compound_and_true_only_no_spurious_false():
    """Compound ``and`` condition — true-only must NOT report false arc."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5 and y > 10:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0]
    false_target = if_node._parent.body[-1]  # return 0

    # True-only: only the true arc should be executed
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10, 20)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        true_target.lineno in executed[if_node.lineno]
    ), f"True arc to L{true_target.lineno} not in executed: {executed}"
    # The false arc must NOT be in executed (only true-only was called)
    assert false_target.lineno not in executed.get(
        if_node.lineno, []
    ), f"Spurious false arc L{false_target.lineno} in executed: {executed}"
    # The false arc must be in missing
    assert (
        if_node.lineno in missing
    ), f"Expected false arc missing for true-only: {missing}"
    assert (
        false_target.lineno in missing[if_node.lineno]
    ), f"False arc to L{false_target.lineno} not in missing: {missing}"


def test_branch_compound_or_false_only_no_spurious_true():
    """Compound ``or`` condition — false-only must NOT report true arc."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5 or y > 10:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0]
    false_target = if_node._parent.body[-1]

    # False-only: only the false arc should be executed
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(1, 1)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        false_target.lineno in executed[if_node.lineno]
    ), f"False arc to L{false_target.lineno} not in executed: {executed}"
    # The true arc must NOT be in executed
    assert true_target.lineno not in executed.get(
        if_node.lineno, []
    ), f"Spurious true arc L{true_target.lineno} in executed: {executed}"


# --- statement-only coverage ---


def test_statement_only_coverage():
    """branch=False path: lines are recorded via add_lines, not add_arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _coverage_session_lines(source, lambda c: c.foo(10)) as (cov, vy_path):
        data = cov.get_data()
        measured = data.measured_files()
        assert vy_path in measured, f"{vy_path} not in measured files: {measured}"

        lines = data.lines(vy_path)
        assert lines is not None and len(lines) > 0, "No lines recorded"

        # No arcs should be stored in statement-only mode
        arcs = data.arcs(vy_path)
        assert not arcs, f"Expected no arcs in branch=False mode, got {arcs}"


# --- noop-branch / compound-condition regressions ---


def test_branch_noop_body_no_else_not_a_branch():
    """if cond: pass (no else) is not a branch — compiler eliminates it."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x == 2:
        pass
    y: uint256 = 1
    return y
"""
    # The if has no behavioral branch — both paths execute the same code.
    # The reporter should not declare arcs or exit_counts for it.
    for val in [0, 2, 10]:
        possible, executed, missing = _check_full_branch_coverage(
            source, lambda c, v=val: c.f(v)
        )
        assert (
            possible == set()
        ), f"x={val}: noop-body no-else should have no possible arcs, got {possible}"
