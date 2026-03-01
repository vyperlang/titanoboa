"""Integration tests for coverage across contract boundaries.

These tests create real .vy files and exercise the full stack
(boa.load → EVM → coverage collector → coverage.py data).
"""

import coverage as coverage_lib
import pytest
import vyper.ast as vy_ast

import boa
from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node
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


def test_cross_module_if_else_in_loop(tmp_path):
    """Branch in loop calling imported module — segments split A→B→A.

    A single call exercises both branches, but the raw_trace_pos
    must persist across segments so the second main segment finds
    its JUMPI at the correct position.
    """
    module_src = """\
x: uint256

@internal
def bump(v: uint256):
    self.x += v
"""
    main_src = """\
import module_lib

initializes: module_lib

@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            module_lib.bump(x)
            total += x
        else:
            module_lib.bump(1)
            total += 1
    return total
"""
    main_path = tmp_path / "main.vy"
    lib_path = tmp_path / "module_lib.vy"
    main_path.write_text(main_src)
    lib_path.write_text(module_src)

    saved_coverage = Env._coverage_enabled
    try:
        cov = coverage_lib.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(str(main_path))
            c.foo([10, 1])
        finally:
            cov.stop()

        analysis = cov._analyze(str(main_path))
        executed = dict(analysis.executed_branch_arcs())
        missing = dict(analysis.missing_branch_arcs())

        # Derive expected lines from AST rather than hardcoding
        tree = vy_ast.parse_to_ast(main_path.read_text(), source_id=0)
        func = tree.body[-1]  # FunctionDef for foo
        for_node = None
        for stmt in func.body:
            if isinstance(stmt, vy_ast.For):
                for_node = stmt
                break
        assert for_node is not None
        if_node = for_node.body[0]
        assert isinstance(if_node, vy_ast.If)

        if_line = if_node.lineno
        true_line = if_node.body[0].lineno
        false_line = if_node.orelse[0].lineno

        # Both branches should have been executed
        assert (
            if_line in executed
        ), f"If line {if_line} not in executed arcs: {executed}"
        executed_targets = set(executed[if_line])
        assert true_line in executed_targets, (
            f"True branch line {true_line} not in executed targets "
            f"{executed_targets} for if@{if_line}"
        )
        assert false_line in executed_targets, (
            f"False branch line {false_line} not in executed targets "
            f"{executed_targets} for if@{if_line}"
        )
        assert missing == {}, f"Unexpected missing arcs: {missing}"
    finally:
        Env._coverage_enabled = saved_coverage


def test_self_call_parent_and_child_both_branch(tmp_path):
    """External self-call where both parent and child have If branches.

    The parent computation's If advances raw_trace_pos for this filename.
    The child computation has a different raw_trace but the same filename.
    If the cursor is keyed by filename only, the child's JUMPI search
    starts from the parent's advanced position, which is meaningless
    in the child's shorter trace, causing misclassification.
    """
    source = """\
interface I:
    def inner(x: uint256) -> uint256: nonpayable

@external
def inner(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def outer(x: uint256) -> uint256:
    if x > 100:
        return 99
    return extcall I(self).inner(x)
"""
    vy_path = tmp_path / "self_call.vy"
    vy_path.write_text(source)

    saved_coverage = Env._coverage_enabled
    try:
        cov = coverage_lib.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(str(vy_path))
            # outer(10): outer takes false branch (10 <= 100),
            #            inner takes true branch (10 > 5)
            c.outer(10)
            # outer(1): outer takes false branch (1 <= 100),
            #           inner takes false branch (1 <= 5)
            c.outer(1)
        finally:
            cov.stop()

        analysis = cov._analyze(str(vy_path))
        executed = dict(analysis.executed_branch_arcs())
        missing = dict(analysis.missing_branch_arcs())

        # Derive expected lines from AST
        tree = vy_ast.parse_to_ast(vy_path.read_text(), source_id=0)

        # Find all If nodes
        if_nodes = tree.get_descendants(vy_ast.If)
        # inner's If (x > 5) and outer's If (x > 100)
        inner_if = None
        outer_if = None
        for node in if_nodes:
            fn = get_fn_ancestor_from_node(node)
            if fn.name == "inner":
                inner_if = node
            elif fn.name == "outer":
                outer_if = node
        assert inner_if is not None
        assert outer_if is not None

        # inner's If should have both branches executed
        inner_if_line = inner_if.lineno
        inner_true_line = inner_if.body[0].lineno
        assert (
            inner_if_line in executed
        ), f"inner If line {inner_if_line} not in executed arcs: {executed}"
        inner_targets = set(executed[inner_if_line])
        assert inner_true_line in inner_targets, (
            f"inner true branch line {inner_true_line} not in executed targets "
            f"{inner_targets} for if@{inner_if_line}"
        )

        # outer's If should have only false branch (x > 100 never true)
        # so it should be in missing
        outer_if_line = outer_if.lineno
        assert outer_if_line in missing, (
            f"outer If line {outer_if_line} should have missing arcs "
            f"(true branch never taken)"
        )
    finally:
        Env._coverage_enabled = saved_coverage


def test_internal_call_cross_function_branches(tmp_path):
    """External calls internal in same file — both have If branches.

    A single trace segment can contain events from both the external
    and internal functions.  The collector must derive fn_node per-If
    rather than using a single fn_node for the whole segment, otherwise
    the internal function's If gets wrong fallthrough targets (pointing
    at the external function's lines).
    """
    source = """\
result: uint256

@internal
def _set(x: uint256):
    if x > 10:
        self.result = x

@external
def foo(x: uint256) -> uint256:
    if x > 5:
        self._set(x)
    return self.result
"""
    vy_path = tmp_path / "internal_call.vy"
    vy_path.write_text(source)

    saved_coverage = Env._coverage_enabled
    try:
        cov = coverage_lib.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(str(vy_path))
            # foo(20): foo true (20 > 5), _set true (20 > 10)
            c.foo(20)
            # foo(7): foo true (7 > 5), _set false (7 <= 10)
            c.foo(7)
            # foo(1): foo false (1 <= 5)
            c.foo(1)
        finally:
            cov.stop()

        analysis = cov._analyze(str(vy_path))
        executed = dict(analysis.executed_branch_arcs())
        missing = dict(analysis.missing_branch_arcs())

        # Derive expected lines from AST
        tree = vy_ast.parse_to_ast(vy_path.read_text(), source_id=0)

        if_nodes = tree.get_descendants(vy_ast.If)
        set_if = None
        foo_if = None
        for node in if_nodes:
            fn = get_fn_ancestor_from_node(node)
            if fn.name == "_set":
                set_if = node
            elif fn.name == "foo":
                foo_if = node
        assert set_if is not None
        assert foo_if is not None

        # _set's If false branch → _set's FunctionDef line (implicit return)
        # NOT foo's FunctionDef line
        set_fn = get_fn_ancestor_from_node(set_if)
        set_false_target = set_fn.lineno
        foo_fn = get_fn_ancestor_from_node(foo_if)

        # Verify executed arcs for _set's If point at _set's fn line,
        # not foo's fn line
        set_if_line = set_if.lineno
        assert (
            set_if_line in executed
        ), f"_set If line {set_if_line} not in executed arcs: {executed}"
        set_targets = set(executed[set_if_line])
        assert set_false_target in set_targets, (
            f"_set false target {set_false_target} not in executed targets "
            f"{set_targets}; if wrong fn_node was used, it would target "
            f"foo's line {foo_fn.lineno} instead"
        )

        # Both functions' branches should be fully covered
        assert missing == {}, f"Unexpected missing arcs: {missing}"
    finally:
        Env._coverage_enabled = saved_coverage
