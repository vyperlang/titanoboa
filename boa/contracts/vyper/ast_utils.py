import io
import re
import tokenize
from functools import lru_cache
from typing import Any, Optional

import vyper.ast as vy_ast


@lru_cache(maxsize=128)
def _get_tokens_for_file(source_code: str):
    """Tokenize entire file and cache the result with line number index."""
    tokens = list(tokenize.generate_tokens(io.StringIO(source_code).readline))

    # Create an index from line number to tokens on that line
    line_to_tokens: dict[int, list] = {}
    for token in tokens:
        line_num = token.start[0]
        if line_num not in line_to_tokens:
            line_to_tokens[line_num] = []
        line_to_tokens[line_num].append(token)

    return line_to_tokens


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
) -> Optional[tuple[str, str]]:
    line_to_tokens = _get_tokens_for_file(source_code)

    # Only check tokens in the specified line range
    for line_num in range(lineno, end_lineno + 1):
        for token in line_to_tokens.get(line_num, []):
            if token.type == tokenize.COMMENT:
                reason = _extract_reason(token.string)
                if reason:
                    return reason
    return None


# TODO: maybe move this into boa/profiling.py
def get_fn_name_from_lineno(ast_map: dict, path: str, lineno: int) -> str:
    for node in ast_map.values():
        if node.lineno == lineno and node.module_node.resolved_path == path:
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
