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


def test_branch_bare_return_in_if():
    """if with bare return (no value) — JUMPI is unmapped in ast_map.

    Regression: the null return compiles to a direct jump to function
    cleanup (FunctionDef), so the condition's JUMPI is not mapped to
    an If node.  Without the _find_if_jumpi fallback, both arcs are
    dropped.
    """
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        return
    self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_bare_return_in_if_partial():
    """Bare return if, only true branch hit — false arc must be missing."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        return
    self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


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
    """Internal function called twice with different inputs in one tx.

    Regression: the resolved guard suppressed If processing after first
    occurrence, so only the first branch direction was recorded.
    """
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


def test_branch_internal_call_three_times():
    """Internal function called three times: true, false, true."""
    source = """\
@internal
def _check(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def foo(a: uint256, b: uint256, c: uint256) -> uint256:
    return self._check(a) + self._check(b) + self._check(c)
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 1, 20))
    assert missing == {}, f"Missing branch arcs: {missing}"


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


# --- invariant and decision engine tests ---


def test_invariant_executed_subset_of_possible():
    """For every scenario, executed branch arcs must be a subset of possible arcs."""
    scenarios = [
        # (source, calls_fn) covering various shapes
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
""",
            lambda c: (c.foo(10), c.foo(1)),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
""",
            lambda c: (c.foo(10), c.foo(1)),
        ),
        (
            """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
    return total
""",
            lambda c: c.foo([1, 10]),
        ),
        (
            """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
        else:
            total += 1
    return total
""",
            lambda c: c.foo([10, 1]),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    return 0
""",
            lambda c: (c.foo(25), c.foo(15), c.foo(5)),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
""",
            lambda c: (c.foo(25), c.foo(15), c.foo(5)),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        y += 1
    y += 2
    return y
""",
            lambda c: (c.foo(10), c.foo(1)),
        ),
        (
            """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 100:
            total += val
        total += 1
    return total
""",
            lambda c: c.foo([1, 2, 3]),
        ),
        # If branch target is a For (zero-iteration edge case)
        (
            """\
@external
def foo(flag: bool, data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    if flag:
        for v: uint256 in data:
            s += v
    else:
        s += 1
    return s
""",
            lambda c: (c.foo(True, []), c.foo(False, [])),
        ),
        (
            """\
@external
def foo(flag: bool, data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    if flag:
        s += 1
    else:
        for v: uint256 in data:
            s += v
    return s
""",
            lambda c: (c.foo(True, []), c.foo(False, [])),
        ),
    ]
    for source, calls_fn in scenarios:
        possible, executed, missing = _check_full_branch_coverage(source, calls_fn)
        for line, targets in executed.items():
            arc_set = {(line, t) for t in targets}
            assert (
                arc_set <= possible
            ), f"Executed arcs {arc_set} not subset of possible {possible}"


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
