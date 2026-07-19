#!/usr/bin/env python3
"""Reject documentation patterns that describe removed or deprecated APIs."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
DOC_FILES = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
FORBIDDEN = {
    "stale versioned source link": re.compile(r"\bv0\.2\.4\b"),
    "obsolete Vyper class path": re.compile(r"\bboa\.vyper\.contract\b"),
    "deprecated direct environment fork call": re.compile(r"\bboa\.env\.fork\("),
    "fictional fuzz strategy helper": re.compile(
        r"\bboa_st\.(?:uint256|address|array)\s*\("
    ),
    "top-level compilation cache helper": re.compile(
        r"\bboa\.(?:set_cache_dir|disable_cache)\s*\("
    ),
    "obsolete environment eval helper": re.compile(r"\bboa\.env\.eval\s*\("),
    "obsolete public VM attribute": re.compile(r"\bboa\.env\.vm\b"),
    "obsolete JupyterLab extension command": re.compile(
        r"\bjupyter\s+lab\s+extension\s+enable\s+boa\b"
    ),
    "unsupported cache environment variable": re.compile(r"\bBOA_CACHE_DIR\b"),
}


def is_allowed(path: Path, line: str, description: str) -> bool:
    return (
        description == "deprecated direct environment fork call"
        and path == ROOT / "docs/api/index.md"
        and "not `boa.env.fork(...)`" in line
    )


def main() -> int:
    failures = []
    for path in DOC_FILES:
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            for description, pattern in FORBIDDEN.items():
                if pattern.search(line) and not is_allowed(path, line, description):
                    failures.append(
                        f"{path.relative_to(ROOT)}:{line_number}: {description}"
                    )

    if failures:
        print("Documentation drift check failed:")
        print("\n".join(f"  {failure}" for failure in failures))
        return 1

    print(f"Documentation drift check passed ({len(DOC_FILES)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
