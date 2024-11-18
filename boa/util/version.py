import re
from typing import Optional

from packaging.specifiers import SpecifierSet

VERSION_RE = r"^(#\s*(@version|pragma\s+version)\s+(.*))"


def detect_version(source_code: str) -> Optional[SpecifierSet]:
    res = re.findall(VERSION_RE, source_code, re.MULTILINE)
    if len(res) < 1:
        return None

    # If there are multiple version pragmas, use the first one found and let Vyper fail compilation
    version_str = res[0][2]

    # X.Y.Z or vX.Y.Z => ==X.Y.Z, ==vX.Y.Z
    if re.match("[v0-9]", version_str):
        version_str = "==" + version_str
    # convert npm to pep440
    version_str = re.sub("^\\^", "~=", version_str)
    return SpecifierSet(version_str)
