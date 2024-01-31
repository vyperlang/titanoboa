import io
import re
import tokenize
from typing import Any, Optional, Tuple

import vyper.ast as vy_ast
from vyper.codegen.core import getpos


def get_block(source_code: str, lineno: int, end_lineno: int) -> str:
    source_lines = source_code.splitlines(keepends=True)
    return "".join(source_lines[lineno - 1 : end_lineno])


def get_line(source_code: str, lineno: int) -> str:
    return get_block(source_code, lineno, lineno)


def _get_comment(source_line: str) -> Optional[str]:
    tokens = tokenize.generate_tokens(io.StringIO(source_line).readline)
    return next((t.string for t in tokens if t.type == tokenize.COMMENT), None)


# loosely, match # `@dev asdf...` or `dev: asdf...`
REASON_PATTERN = re.compile(r"#\s*@?(\w+):?\s+(.*)")


def _extract_reason(comment: str) -> Any:
    m = REASON_PATTERN.match(comment)
    if m is not None:
        return m.group(1, 2)
    return None


# extract the dev revert reason at a given line.
# somewhat heuristic.
def reason_at(
    source_code: str, lineno: int, end_lineno: int
) -> Optional[Tuple[str, str]]:
    block = get_block(source_code, lineno, end_lineno)
    c = _get_comment(block)
    if c is not None:
        return _extract_reason(c)
    return None


# build a reverse map from the format we have in pc_pos_map to AST nodes
def ast_map_of(ast_node):
    ast_map = {}
    nodes = [ast_node] + ast_node.get_descendants(reverse=True)
    for node in nodes:
        ast_map[getpos(node)] = node
    return ast_map


def get_fn_name_from_lineno(ast_map: dict, lineno: int) -> str:
    # TODO: this could be a performance bottleneck
    for source_map, node in ast_map.items():
        if source_map[0] == lineno:
            fn_node = get_fn_ancestor_from_node(node)
            if fn_node:
                return fn_node.name
    return ""


def get_fn_ancestor_from_node(node):
    if node is None:
        return None

    if isinstance(node, vy_ast.FunctionDef):
        return node

    return node.get_ancestor(vy_ast.FunctionDef)
