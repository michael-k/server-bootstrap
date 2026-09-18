"""Unit tests for the spec traceability checker."""

from pathlib import Path

import pytest

from tests.spec_check import (
    Requirement,
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
