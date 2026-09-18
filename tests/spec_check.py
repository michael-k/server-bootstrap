"""Spec traceability checks.

`specs/` is authoritative: a mismatch between a spec and the implementation is a
bug.  This module makes the mechanical half of that claim enforceable — every
requirement is cited by the code that realises it, and every citation names a
requirement that exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = REPO_ROOT / "specs"

_PREFIX_ROW = re.compile(
    r"^\|\s*`(?P<prefix>[A-Z][A-Z0-9]*)`\s*\|\s*`(?P<spec>[a-z0-9./-]+)`\s*\|"
)
_REQ_HEADING = re.compile(
    r"^### (?P<id>(?P<prefix>[A-Z][A-Z0-9]*)-(?P<number>\d+)) — (?P<title>.+?)\s*$"
)
_WITHDRAWN_SUFFIX = " (withdrawn)"
_EXEMPT_MARKER = "**Traceability:** exempt"
_PENDING_MARKER = "**Traceability:** pending"


@dataclass(frozen=True)
class Requirement:
    """One numbered SHALL statement in a spec."""

    id: str
    prefix: str
    number: int
    title: str
    spec: str
    source: Path
    withdrawn: bool = False
    exempt: bool = False
    pending: bool = False


def load_prefixes(readme: Path) -> dict[str, str]:
    """Read the prefix registry table from `specs/README.md`."""
    prefixes: dict[str, str] = {}
    for line in readme.read_text().splitlines():
        match = _PREFIX_ROW.match(line)
        if match:
            prefixes[match["prefix"]] = match["spec"]
    return prefixes


def parse_requirements(path: Path, spec: str) -> list[Requirement]:
    """Extract every requirement heading and its body annotations from a spec."""
    found: list[Requirement] = []
    current: Requirement | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is not None:
            text = "\n".join(body)
            found.append(
                replace(
                    current,
                    exempt=_EXEMPT_MARKER in text,
                    pending=_PENDING_MARKER in text,
                )
            )
        current, body = None, []

    for line in path.read_text().splitlines():
        match = _REQ_HEADING.match(line)
        if match:
            flush()
            title = match["title"]
            withdrawn = title.endswith(_WITHDRAWN_SUFFIX)
            current = Requirement(
                id=match["id"],
                prefix=match["prefix"],
                number=int(match["number"]),
                title=title.removesuffix(_WITHDRAWN_SUFFIX).strip(),
                spec=spec,
                source=path,
                withdrawn=withdrawn,
            )
        elif current is not None:
            body.append(line)

    flush()
    return found


def load_all_requirements(
    specs_dir: Path, prefixes: dict[str, str]
) -> list[Requirement]:
    """Parse the requirements of every registered spec directory."""
    found: list[Requirement] = []
    for spec in sorted(set(prefixes.values())):
        path = specs_dir / spec / "requirements.md"
        if path.is_file():
            found.extend(parse_requirements(path, spec))
    return found
