import io
import re
import tokenize
from typing import Any, Optional, Tuple


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
def reason_at(source_code: str, lineno: int) -> Optional[Tuple[str, str]]:
    line = get_line(source_code, lineno)
    c = _get_comment(line)
    if c is not None:
        return _extract_reason(c)
    return None
