import io
import re
import tokenize
from typing import Any, Optional, Tuple

from vyper.codegen.core import getpos


def get_line(source_code: str, lineno: int) -> str:
    source_lines = source_code.splitlines(keepends=True)
    return source_lines[lineno - 1]


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
def extract_reason(source_code) -> Optional[Tuple[str, str]]:
    c = _get_comment(source_code)
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
