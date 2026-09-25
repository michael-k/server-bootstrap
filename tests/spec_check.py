"""Spec traceability checks.

`specs/` is authoritative: a mismatch between a spec and the implementation is a
bug.  This module makes the mechanical half of that claim enforceable — every
requirement is cited by the code that realises it, and every citation names a
requirement that exists.  This module's own test module is excluded from the
scan, since its requirement-ID-shaped literals are test fixtures rather than
real citations.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = REPO_ROOT / "specs"

_PREFIX_ROW = re.compile(
    r"^\|\s*`(?P<prefix>[A-Z][A-Z0-9]*)`\s*\|\s*`(?P<spec>[a-z0-9./-]+)`\s*\|"
)
_LEGACY_REF = re.compile(r"\bRequirements?:?\s+\d+\.\d+")
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
# literal requirement IDs used as test fixtures, which are not evidence that
# anything implements those requirements.
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


REQUIRED_REQUIREMENTS_SECTIONS: tuple[str, ...] = (
    "Purpose",
    "Scope",
    "Security invariants",
    "Requirements",
)
REQUIRED_DESIGN_SECTIONS: tuple[str, ...] = ("Approach", "Implementation map")

_ALLOWANCE_ROW = re.compile(
    r"^\|\s*(?P<id>ALW-\d+)\s*\|[^|]*\|(?P<claimed_by>[^|]*)\|"
)
_CLAIMS_LINE = re.compile(r"^\*\*Allowances claimed:\*\*\s*(?P<value>.+?)\s*$")
_REQ_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
_ALW_TOKEN = re.compile(r"\bALW-\d+\b")
_MAP_ROW = re.compile(r"^\|\s*`(?P<path>[^`]+)`\s*\|")


def _sections(text: str) -> set[str]:
    return {
        line.removeprefix("## ").strip()
        for line in text.splitlines()
        if line.startswith("## ")
    }


def check_structure(specs_dir: Path, prefixes: dict[str, str]) -> list[Finding]:
    """Flag specs missing a mandatory file or section."""
    findings: list[Finding] = []
    for spec in sorted(set(prefixes.values())):
        for filename, required in (
            ("requirements.md", REQUIRED_REQUIREMENTS_SECTIONS),
            ("design.md", REQUIRED_DESIGN_SECTIONS),
        ):
            path = specs_dir / spec / filename
            if not path.is_file():
                findings.append(
                    Finding("missing-spec-file", f"{spec}/{filename} does not exist")
                )
                continue
            present = _sections(path.read_text())
            findings.extend(
                Finding(
                    "missing-section",
                    f"{spec}/{filename} has no '## {section}' section",
                )
                for section in required
                if section not in present
            )
    return findings


def parse_allowance_register(path: Path) -> dict[str, set[str]]:
    """Read both allowance registers, mapping each ALW id to its claiming requirements."""
    register: dict[str, set[str]] = {}
    if not path.is_file():
        return register
    for line in path.read_text().splitlines():
        match = _ALLOWANCE_ROW.match(line)
        if match:
            register[match["id"]] = set(_REQ_TOKEN.findall(match["claimed_by"]))
    return register


def find_allowance_claims(
    specs_dir: Path, prefixes: dict[str, str]
) -> dict[str, set[str]]:
    """Read the `**Allowances claimed:**` line of every spec.

    Lines inside fenced code blocks are skipped, so a documentation example
    showing the claims-line syntax is not mistaken for a real claim.
    """
    claims: dict[str, set[str]] = {}
    for spec in sorted(set(prefixes.values())):
        path = specs_dir / spec / "requirements.md"
        if not path.is_file():
            continue
        in_fence = False
        for line in path.read_text().splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = _CLAIMS_LINE.match(line)
            if not match:
                continue
            for allowance in _ALW_TOKEN.findall(match["value"]):
                claims.setdefault(allowance, set()).add(spec)
    return claims


def check_spec_markdown(specs_dir: Path, prefixes: dict[str, str]) -> list[Finding]:
    """Flag malformed markdown that would make `find_allowance_claims` silently drop lines.

    An unclosed code fence in `requirements.md` causes every line after it to
    be treated as fenced, so a real `**Allowances claimed:**` line below it is
    silently dropped rather than counted — defeating the allowance registers
    with no finding anywhere. This makes that drop impossible to miss.
    """
    findings: list[Finding] = []
    for spec in sorted(set(prefixes.values())):
        path = specs_dir / spec / "requirements.md"
        if not path.is_file():
            continue
        in_fence = False
        for line in path.read_text().splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
        if in_fence:
            findings.append(
                Finding(
                    "unclosed-code-fence",
                    f"{spec}/requirements.md has an unclosed code fence",
                )
            )
    return findings


def check_allowances(
    register: dict[str, set[str]],
    claims: dict[str, set[str]],
    requirements: list[Requirement],
) -> list[Finding]:
    """Flag allowances claimed but unregistered, registered but unclaimed, or dangling.

    A register entry must also be internally consistent: it must name at least
    one claimant, that claimant must not be withdrawn, and it must belong to a
    spec that actually claims the allowance — otherwise a spec could invoke an
    allowance that was registered for someone else's requirement.
    """
    by_id = {req.id: req for req in requirements}
    findings: list[Finding] = []

    findings.extend(
        Finding(
            "unregistered-allowance",
            f"{allowance} is claimed by {', '.join(sorted(specs))} "
            "but is not in the allowance register",
        )
        for allowance, specs in sorted(claims.items())
        if allowance not in register
    )
    findings.extend(
        Finding(
            "unclaimed-allowance",
            f"{allowance} is registered but no spec claims it",
        )
        for allowance in sorted(register)
        if allowance not in claims
    )
    findings.extend(
        Finding(
            "allowance-without-claimant",
            f"{allowance} names no claimant requirement in the register",
        )
        for allowance, req_ids in sorted(register.items())
        if not req_ids
    )
    findings.extend(
        Finding(
            "dangling-citation",
            f"{allowance} names {req_id} as its claimant but no spec defines it",
        )
        for allowance, req_ids in sorted(register.items())
        for req_id in sorted(req_ids)
        if req_id not in by_id
    )

    for allowance, req_ids in sorted(register.items()):
        for req_id in sorted(req_ids):
            req = by_id.get(req_id)
            if req is None:
                continue  # already reported as dangling-citation
            if req.withdrawn:
                findings.append(
                    Finding(
                        "withdrawn-allowance-claimant",
                        f"{allowance} names withdrawn requirement {req_id} as its claimant",
                    )
                )
                continue
            if allowance not in claims:
                continue  # already reported as unclaimed-allowance
            if req.spec not in claims[allowance]:
                findings.append(
                    Finding(
                        "allowance-claimant-mismatch",
                        f"{allowance} names {req_id} ({req.spec}) as its claimant but is "
                        f"claimed by {', '.join(sorted(claims[allowance]))}",
                    )
                )
    return findings


def check_implementation_map(
    specs_dir: Path, prefixes: dict[str, str], repo_root: Path
) -> list[Finding]:
    """Flag paths in a design's implementation map that do not exist."""
    findings: list[Finding] = []
    for spec in sorted(set(prefixes.values())):
        path = specs_dir / spec / "design.md"
        if not path.is_file():
            continue
        in_map = False
        for line in path.read_text().splitlines():
            if line.startswith("## "):
                in_map = line.removeprefix("## ").strip() == "Implementation map"
                continue
            match = _MAP_ROW.match(line)
            if in_map and match and not (repo_root / match["path"]).exists():
                findings.append(
                    Finding(
                        "missing-implementation-path",
                        f"{spec}/design.md maps {match['path']}, which does not exist",
                    )
                )
    return findings


def check_legacy_references(repo_root: Path) -> list[Finding]:
    """Flag surviving `Requirement N.M` citations from the superseded numbering.

    This checker's own test module is excluded, for the same reason
    `find_citations` excludes it: its requirement-ID-shaped literals are test
    fixtures, not real citations.
    """
    findings: list[Finding] = []
    for glob in SCAN_GLOBS:
        for path in sorted(repo_root.glob(glob)):
            if not path.is_file() or path.relative_to(repo_root) == _SELF_TEST:
                continue
            for number, line in enumerate(
                path.read_text(errors="replace").splitlines(), start=1
            ):
                if _LEGACY_REF.search(line):
                    findings.append(
                        Finding(
                            "legacy-reference",
                            f"{path.relative_to(repo_root)}:{number} still cites the "
                            f"superseded numbering: {line.strip()}",
                        )
                    )
    return findings


TRACEABILITY_PATH = SPECS_DIR / "_traceability.md"


def render_traceability(
    requirements: list[Requirement], citations: dict[str, set[Path]]
) -> str:
    """Render the generated requirement-to-implementation index."""
    lines = [
        "# Requirement traceability",
        "",
        "Generated by `make spec-check`. Do not edit by hand.",
        "",
    ]
    for spec in sorted({req.spec for req in requirements}):
        lines += [f"## {spec}", "", "| Requirement | Title | Cited by |", "|---|---|---|"]
        for req in sorted(
            (r for r in requirements if r.spec == spec), key=lambda r: r.number
        ):
            cited = ", ".join(f"`{p}`" for p in sorted(citations.get(req.id, ()))) or "—"
            title = req.title
            if req.withdrawn:
                title = f"{title} (withdrawn)"
            elif req.pending:
                title = f"{title} (pending)"
            lines.append(f"| `{req.id}` | {title} | {cited} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def run_checks(
    repo_root: Path,
    specs_dir: Path,
    prefixes: dict[str, str],
    all_prefixes: dict[str, str] | None = None,
) -> list[Finding]:
    """Run every check and return the combined findings.

    `prefixes` may be narrowed to a single spec (see `--spec`), and every check
    is evaluated against that narrower scope except the allowance registers:
    whether an allowance is claimed by the right requirement is a whole-tree
    property, since the claimant can live in a spec outside the current scope.
    Scoping that check would make a `--spec` run flag allowances it has no
    business judging. `all_prefixes` supplies the unscoped registry for that
    one check; it defaults to `prefixes` for callers with no narrower scope.
    """
    if all_prefixes is None:
        all_prefixes = prefixes
    requirements = load_all_requirements(specs_dir, prefixes)
    citations = find_citations(repo_root, prefixes)
    full_requirements = load_all_requirements(specs_dir, all_prefixes)
    full_claims = find_allowance_claims(specs_dir, all_prefixes)
    return [
        *check_ids(requirements),
        *check_citations(requirements, citations),
        *check_structure(specs_dir, prefixes),
        *check_spec_markdown(specs_dir, prefixes),
        *check_implementation_map(specs_dir, prefixes, repo_root),
        *check_allowances(
            parse_allowance_register(specs_dir / "project" / "security-invariants.md"),
            full_claims,
            full_requirements,
        ),
        *check_legacy_references(repo_root),
    ]


def main(argv: list[str] | None = None) -> int:
    """Check the spec tree and refresh the traceability index."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec",
        action="append",
        default=[],
        metavar="NAME",
        help="limit the check to one spec directory (repeatable)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write the traceability index (a --spec run never writes it)",
    )
    args = parser.parse_args(argv)

    all_prefixes = load_prefixes(SPECS_DIR / "README.md")
    prefixes = all_prefixes
    if args.spec:
        prefixes = {p: s for p, s in all_prefixes.items() if s in set(args.spec)}
        if not prefixes:
            print(f"No registered spec matches {args.spec}", file=sys.stderr)
            return 2

    findings = run_checks(REPO_ROOT, SPECS_DIR, prefixes, all_prefixes)
    for finding in sorted(findings, key=lambda f: (f.kind, f.message)):
        print(finding)

    pending = [r.id for r in load_all_requirements(SPECS_DIR, prefixes) if r.pending]
    if pending:
        print(f"Pending (specified, not yet implemented): {', '.join(sorted(pending))}")

    if findings:
        print(f"\n{len(findings)} finding(s)")
        return 1

    print("Spec check: no findings")
    # The index covers the whole tree, so a run scoped by --spec must not
    # overwrite it with one spec's rows.
    if not args.check and not args.spec:
        requirements = load_all_requirements(SPECS_DIR, prefixes)
        citations = find_citations(REPO_ROOT, prefixes)
        TRACEABILITY_PATH.write_text(render_traceability(requirements, citations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
