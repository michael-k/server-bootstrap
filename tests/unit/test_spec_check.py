"""Unit tests for the spec traceability checker."""

from pathlib import Path

import pytest

from tests.spec_check import (
    Finding,
    Requirement,
    check_citations,
    check_ids,
    citation_pattern,
    find_citations,
    load_all_requirements,
    load_prefixes,
    parse_requirements,
)

pytestmark = pytest.mark.unit


def test_load_prefixes_reads_the_registry_table(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "| Prefix | Spec directory | Implemented by |\n"
        "|---|---|---|\n"
        "| `SSH` | `ssh-hardening` | `roles/ssh_hardening/` |\n"
        "| `FW` | `firewall` | `roles/firewall/` |\n"
    )

    assert load_prefixes(readme) == {"SSH": "ssh-hardening", "FW": "firewall"}


def test_load_prefixes_ignores_prose_pipes(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Use `a | b` in a shell.\n| `SSH` | `ssh-hardening` | x |\n")

    assert load_prefixes(readme) == {"SSH": "ssh-hardening"}


def test_load_prefixes_accepts_a_prefix_containing_a_digit(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("| `F2B` | `fail2ban` | `roles/fail2ban/` |\n")

    assert load_prefixes(readme) == {"F2B": "fail2ban"}


def test_parse_requirements_extracts_id_number_and_title(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text(
        "# SSH — Requirements\n\n"
        "## Requirements\n\n"
        "### SSH-1 — Password authentication\n\n"
        "THE Bootstrap SHALL disable password authentication.\n\n"
        "### SSH-12 — Listen address\n\n"
        "THE Bootstrap SHALL bind sshd to the configured addresses.\n"
    )

    reqs = parse_requirements(path, "ssh-hardening")

    assert [r.id for r in reqs] == ["SSH-1", "SSH-12"]
    assert [r.number for r in reqs] == [1, 12]
    assert reqs[0].title == "Password authentication"
    assert reqs[0].prefix == "SSH"
    assert reqs[0].spec == "ssh-hardening"
    assert reqs[0].source == path


def test_parse_requirements_marks_withdrawn(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text("### SSH-4 — Old rule (withdrawn)\n\nSuperseded by SSH-9.\n")

    (req,) = parse_requirements(path, "ssh-hardening")

    assert req.withdrawn is True
    assert req.title == "Old rule"


def test_parse_requirements_marks_exempt(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text(
        "### PRJ-9 — README documents the variables\n\n"
        "THE README SHALL document every configurable variable.\n\n"
        "**Traceability:** exempt — prose requirement with no code site.\n"
    )

    (req,) = parse_requirements(path, "project")

    assert req.exempt is True
    assert req.withdrawn is False


def test_parse_requirements_marks_pending(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text(
        "### CTR-3 — Contract asserted before deploy\n\n"
        "THE Playbook SHALL assert the bootstrap contract before any change.\n\n"
        "**Traceability:** pending — no pre-flight assertion exists yet.\n"
    )

    (req,) = parse_requirements(path, "bootstrap-contract")

    assert req.pending is True
    assert req.exempt is False


def test_parse_requirements_accepts_a_prefix_containing_a_digit(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text("### F2B-1 — SSH jail\n\nTHE Bootstrap SHALL enable the SSH jail.\n")

    (req,) = parse_requirements(path, "fail2ban")

    assert req.id == "F2B-1"
    assert req.prefix == "F2B"
    assert req.number == 1


def test_parse_requirements_ignores_headings_that_are_not_requirements(
    tmp_path: Path,
) -> None:
    path = tmp_path / "requirements.md"
    path.write_text("### In scope\n\nStuff.\n\n### SSH-1 — Real one\n\nSHALL do it.\n")

    assert [r.id for r in parse_requirements(path, "ssh-hardening")] == ["SSH-1"]


def test_load_all_requirements_walks_registered_spec_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "ssh-hardening").mkdir()
    (tmp_path / "ssh-hardening" / "requirements.md").write_text(
        "### SSH-1 — A\n\nSHALL a.\n"
    )
    (tmp_path / "firewall").mkdir()
    (tmp_path / "firewall" / "requirements.md").write_text("### FW-1 — B\n\nSHALL b.\n")

    reqs = load_all_requirements(
        tmp_path, {"SSH": "ssh-hardening", "FW": "firewall"}
    )

    assert sorted(r.id for r in reqs) == ["FW-1", "SSH-1"]
    assert isinstance(reqs[0], Requirement)


def _req(req_id: str, **kwargs: object) -> Requirement:
    prefix, number = req_id.split("-")
    defaults: dict[str, object] = {
        "id": req_id,
        "prefix": prefix,
        "number": int(number),
        "title": "T",
        "spec": "s",
        "source": Path("specs/s/requirements.md"),
    }
    return Requirement(**(defaults | kwargs))  # type: ignore[arg-type]


def test_citation_pattern_matches_registered_prefixes_only() -> None:
    pattern = citation_pattern({"SSH": "ssh-hardening", "FW": "firewall"})

    assert pattern.findall("see SSH-3 and FW-12") == [("SSH", "3"), ("FW", "12")]


def test_citation_pattern_ignores_lookalike_tokens() -> None:
    pattern = citation_pattern({"SSH": "ssh-hardening", "FS": "filesystem-hardening"})

    assert pattern.findall("SHA-512 AES-256 CVE-2024-1234 sntrup761x25519") == []


def test_citation_pattern_prefers_the_longest_prefix() -> None:
    pattern = citation_pattern({"F2B": "fail2ban", "FW": "firewall"})

    assert pattern.findall("F2B-1") == [("F2B", "1")]


def test_find_citations_maps_ids_to_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "roles" / "ssh_hardening" / "tasks").mkdir(parents=True)
    (tmp_path / "roles" / "ssh_hardening" / "tasks" / "main.yml").write_text(
        "# SSH-1: disable password auth\n"
    )
    (tmp_path / "site.yml").write_text("# SSH-1 and SSH-2\n")

    citations = find_citations(tmp_path, {"SSH": "ssh-hardening"})

    assert citations["SSH-1"] == {
        Path("roles/ssh_hardening/tasks/main.yml"),
        Path("site.yml"),
    }
    assert citations["SSH-2"] == {Path("site.yml")}


def test_find_citations_does_not_scan_the_spec_tree(tmp_path: Path) -> None:
    (tmp_path / "specs" / "ssh-hardening").mkdir(parents=True)
    (tmp_path / "specs" / "ssh-hardening" / "requirements.md").write_text(
        "### SSH-1 — A\n\nRelated: SSH-2.\n"
    )

    assert find_citations(tmp_path, {"SSH": "ssh-hardening"}) == {}


def test_find_citations_does_not_scan_its_own_test_module(tmp_path: Path) -> None:
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_spec_check.py").write_text("# SSH-99\n")
    (tmp_path / "tests" / "unit" / "test_users.py").write_text("# SSH-1\n")

    citations = find_citations(tmp_path, {"SSH": "ssh-hardening"})

    assert "SSH-99" not in citations
    assert citations["SSH-1"] == {Path("tests/unit/test_users.py")}


def test_check_ids_flags_duplicates() -> None:
    findings = check_ids([_req("SSH-1"), _req("SSH-1")])

    assert [f.kind for f in findings] == ["duplicate-id"]
    assert "SSH-1" in findings[0].message


def test_check_ids_flags_a_gap_free_sequence_is_not_required() -> None:
    assert check_ids([_req("SSH-1"), _req("SSH-7")]) == []


def test_check_citations_flags_dangling_references() -> None:
    findings = check_citations([_req("SSH-1")], {"SSH-9": {Path("site.yml")}})

    kinds = {f.kind for f in findings}
    assert "dangling-citation" in kinds
    assert any("SSH-9" in f.message and "site.yml" in f.message for f in findings)


def test_check_citations_flags_orphan_requirements() -> None:
    findings = check_citations([_req("SSH-1")], {})

    assert [f.kind for f in findings] == ["orphan-requirement"]


def test_check_citations_accepts_a_cited_requirement() -> None:
    assert check_citations([_req("SSH-1")], {"SSH-1": {Path("site.yml")}}) == []


def test_check_citations_exempts_annotated_requirements() -> None:
    assert check_citations([_req("PRJ-9", exempt=True)], {}) == []


def test_check_citations_does_not_require_pending_requirements() -> None:
    assert check_citations([_req("CTR-3", pending=True)], {}) == []


def test_check_citations_does_not_require_withdrawn_requirements() -> None:
    assert check_citations([_req("SSH-4", withdrawn=True)], {}) == []


def test_check_citations_flags_a_cited_withdrawn_requirement() -> None:
    findings = check_citations(
        [_req("SSH-4", withdrawn=True)], {"SSH-4": {Path("site.yml")}}
    )

    assert [f.kind for f in findings] == ["cited-withdrawn-requirement"]

    assert all(isinstance(f, Finding) for f in findings)
