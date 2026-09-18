"""Spec traceability checks.

`specs/` is authoritative: a mismatch between a spec and the implementation is a
bug.  This module makes the mechanical half of that claim enforceable — every
requirement is cited by the code that realises it, and every citation names a
requirement that exists.  This module's own test module is excluded from the
scan, since its requirement-ID-shaped literals are test fixtures rather than
real citations.
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


SCAN_GLOBS: tuple[str, ...] = (
    "site.yml",
    "Makefile",
    "README.md",
    "AGENTS.md",
    "roles/**/*.yml",
    "roles/**/*.j2",
    "tests/**/*.py",
    "tests/**/*.yml",
    "incus/src/**/*.py",
    "incus/README.md",
    "docs/*.md",
)

# This checker's own test module is excluded from scanning: it is full of
# literal requirement IDs used as test fixtures (SSH-9, EMRG-99, ...), which
# are not evidence that anything implements those requirements.
_SELF_TEST = Path("tests/unit/test_spec_check.py")


@dataclass(frozen=True)
class Finding:
    """One spec/implementation disagreement."""

    kind: str
    message: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.message}"


def citation_pattern(prefixes: dict[str, str]) -> re.Pattern[str]:
    """Build a pattern matching `PREFIX-N` for registered prefixes only."""
    alternatives = "|".join(sorted(prefixes, key=lambda prefix: len(prefix), reverse=True))
    return re.compile(rf"\b({alternatives})-(\d+)\b")


def find_citations(repo_root: Path, prefixes: dict[str, str]) -> dict[str, set[Path]]:
    """Map each cited requirement ID to the files citing it.

    The spec tree is deliberately excluded: a cross-reference between specs is
    not evidence that anything implements the requirement. This checker's own
    test module is excluded too, since its requirement-ID-shaped literals are
    test fixtures, not citations.
    """
    if not prefixes:
        return {}
    pattern = citation_pattern(prefixes)
    citations: dict[str, set[Path]] = {}
    for glob in SCAN_GLOBS:
        for path in sorted(repo_root.glob(glob)):
            if not path.is_file() or path.relative_to(repo_root) == _SELF_TEST:
                continue
            for match in pattern.finditer(path.read_text(errors="replace")):
                key = f"{match.group(1)}-{match.group(2)}"
                citations.setdefault(key, set()).add(path.relative_to(repo_root))
    return citations


def check_ids(requirements: list[Requirement]) -> list[Finding]:
    """Flag IDs used more than once."""
    seen: dict[str, Requirement] = {}
    findings: list[Finding] = []
    for req in requirements:
        if req.id in seen:
            findings.append(
                Finding(
                    "duplicate-id",
                    f"{req.id} is defined twice: {seen[req.id].source} and {req.source}",
                )
            )
        else:
            seen[req.id] = req
    return findings


def check_citations(
    requirements: list[Requirement], citations: dict[str, set[Path]]
) -> list[Finding]:
    """Flag citations without requirements, and requirements without citations."""
    by_id = {req.id: req for req in requirements}
    findings: list[Finding] = []

    for cited, paths in sorted(citations.items()):
        where = ", ".join(str(p) for p in sorted(paths))
        req = by_id.get(cited)
        if req is None:
            findings.append(
                Finding(
                    "dangling-citation",
                    f"{cited} is cited by {where} but no spec defines it",
                )
            )
        elif req.withdrawn:
            findings.append(
                Finding(
                    "cited-withdrawn-requirement",
                    f"{cited} is withdrawn but still cited by {where}",
                )
            )

    for req in requirements:
        if req.withdrawn or req.exempt or req.pending or citations.get(req.id):
            continue
        findings.append(
            Finding(
                "orphan-requirement",
                f"{req.id} ({req.title}) is defined in {req.source} but nothing cites it",
            )
        )

    return findings
