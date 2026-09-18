"""Unit tests for the spec traceability checker."""

from pathlib import Path

import pytest

from tests.spec_check import (
    Finding,
    Requirement,
    check_allowances,
    check_citations,
    check_ids,
    check_implementation_map,
    check_spec_markdown,
    check_structure,
    citation_pattern,
    find_allowance_claims,
    find_citations,
    load_all_requirements,
    load_prefixes,
    parse_allowance_register,
    parse_requirements,
    render_traceability,
    run_checks,
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


def _spec(specs_dir: Path, name: str, requirements: str, design: str) -> None:
    (specs_dir / name).mkdir(parents=True, exist_ok=True)
    (specs_dir / name / "requirements.md").write_text(requirements)
    (specs_dir / name / "design.md").write_text(design)


_FULL_REQUIREMENTS = (
    "# X — Requirements\n\n"
    "## Purpose\n\np\n\n"
    "## Scope\n\ns\n\n"
    "## Security invariants\n\n**Allowances claimed:** none\n\n"
    "## Requirements\n\n### SSH-1 — A\n\nSHALL a.\n"
)
_FULL_DESIGN = (
    "# X — Design\n\n## Approach\n\na\n\n## Implementation map\n\n"
    "| Path | Realises |\n|---|---|\n| `site.yml` | SSH-1 |\n"
)


def test_check_structure_accepts_a_complete_spec(tmp_path: Path) -> None:
    _spec(tmp_path, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)

    assert check_structure(tmp_path, {"SSH": "ssh-hardening"}) == []


def test_check_structure_flags_a_missing_section(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "ssh-hardening",
        _FULL_REQUIREMENTS.replace("## Security invariants", "## Notes"),
        _FULL_DESIGN,
    )

    findings = check_structure(tmp_path, {"SSH": "ssh-hardening"})

    assert [f.kind for f in findings] == ["missing-section"]
    assert "Security invariants" in findings[0].message


def test_check_structure_flags_a_missing_file(tmp_path: Path) -> None:
    (tmp_path / "firewall").mkdir()

    findings = check_structure(tmp_path, {"FW": "firewall"})

    assert {f.kind for f in findings} == {"missing-spec-file"}
    assert len(findings) == 2


def test_parse_allowance_register_reads_rows(tmp_path: Path) -> None:
    path = tmp_path / "security-invariants.md"
    path.write_text(
        "| Allowance | Invariant | Claimed by | Compensating control |\n"
        "|---|---|---|---|\n"
        "| ALW-1 | INV-1, INV-6 | EMRG-2, EMRG-3 | Console root only |\n"
    )

    assert parse_allowance_register(path) == {"ALW-1": {"EMRG-2", "EMRG-3"}}


def test_parse_allowance_register_accepts_a_prefix_containing_a_digit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "security-invariants.md"
    path.write_text(
        "| Allowance | Invariant | Claimed by | Compensating control |\n"
        "|---|---|---|---|\n"
        "| ALW-1 | INV-1 | F2B-1 | Console root only |\n"
    )

    assert parse_allowance_register(path) == {"ALW-1": {"F2B-1"}}


def test_find_allowance_claims_reads_the_claims_line(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "emergency-access",
        _FULL_REQUIREMENTS.replace(
            "**Allowances claimed:** none", "**Allowances claimed:** ALW-1"
        ),
        _FULL_DESIGN,
    )

    assert find_allowance_claims(tmp_path, {"EMRG": "emergency-access"}) == {
        "ALW-1": {"emergency-access"}
    }


def test_check_allowances_flags_a_claim_missing_from_the_register() -> None:
    findings = check_allowances({}, {"ALW-1": {"emergency-access"}}, [])

    assert [f.kind for f in findings] == ["unregistered-allowance"]


def test_check_allowances_flags_a_register_entry_nobody_claims() -> None:
    findings = check_allowances({"ALW-1": {"EMRG-2"}}, {}, [_req("EMRG-2")])

    assert [f.kind for f in findings] == ["unclaimed-allowance"]


def test_check_allowances_flags_an_unknown_claimed_by_requirement() -> None:
    findings = check_allowances(
        {"ALW-1": {"EMRG-99"}}, {"ALW-1": {"emergency-access"}}, [_req("EMRG-2")]
    )

    assert [f.kind for f in findings] == ["dangling-citation"]


def test_check_allowances_accepts_a_matched_pair() -> None:
    assert (
        check_allowances(
            {"ALW-1": {"EMRG-2"}},
            {"ALW-1": {"emergency-access"}},
            [_req("EMRG-2", spec="emergency-access")],
        )
        == []
    )


def test_check_allowances_flags_a_claimant_owned_by_a_different_spec() -> None:
    findings = check_allowances(
        {"ALW-1": {"EMRG-2"}}, {"ALW-1": {"firewall"}}, [_req("EMRG-2")]
    )

    assert [f.kind for f in findings] == ["allowance-claimant-mismatch"]


def test_check_allowances_flags_a_register_entry_with_no_claimant_id() -> None:
    findings = check_allowances({"ALW-1": set()}, {"ALW-1": {"firewall"}}, [])

    assert [f.kind for f in findings] == ["allowance-without-claimant"]


def test_check_allowances_flags_a_withdrawn_claimant() -> None:
    findings = check_allowances(
        {"ALW-1": {"EMRG-2"}},
        {"ALW-1": {"emergency-access"}},
        [_req("EMRG-2", spec="emergency-access", withdrawn=True)],
    )

    assert [f.kind for f in findings] == ["withdrawn-allowance-claimant"]


def test_find_allowance_claims_ignores_a_claims_line_inside_a_fenced_code_block(
    tmp_path: Path,
) -> None:
    requirements = _FULL_REQUIREMENTS.replace(
        "**Allowances claimed:** none",
        "**Allowances claimed:** none\n\n```\n**Allowances claimed:** ALW-9\n```\n",
    )
    _spec(tmp_path, "emergency-access", requirements, _FULL_DESIGN)

    assert find_allowance_claims(tmp_path, {"EMRG": "emergency-access"}) == {}


def test_check_spec_markdown_flags_an_unclosed_code_fence(tmp_path: Path) -> None:
    requirements = _FULL_REQUIREMENTS.replace(
        "**Allowances claimed:** none",
        "**Allowances claimed:** none\n\n```\nunterminated\n",
    )
    _spec(tmp_path, "emergency-access", requirements, _FULL_DESIGN)

    findings = check_spec_markdown(tmp_path, {"EMRG": "emergency-access"})

    assert [f.kind for f in findings] == ["unclosed-code-fence"]


def test_check_spec_markdown_accepts_balanced_fences(tmp_path: Path) -> None:
    requirements = _FULL_REQUIREMENTS.replace(
        "**Allowances claimed:** none",
        "**Allowances claimed:** none\n\n```\nexample\n```\n",
    )
    _spec(tmp_path, "emergency-access", requirements, _FULL_DESIGN)

    assert check_spec_markdown(tmp_path, {"EMRG": "emergency-access"}) == []


def test_check_implementation_map_flags_a_missing_path(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _spec(
        specs,
        "ssh-hardening",
        _FULL_REQUIREMENTS,
        _FULL_DESIGN.replace("`site.yml`", "`roles/gone/tasks/main.yml`"),
    )

    findings = check_implementation_map(specs, {"SSH": "ssh-hardening"}, tmp_path)

    assert [f.kind for f in findings] == ["missing-implementation-path"]


def test_check_implementation_map_accepts_an_existing_path(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _spec(specs, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)
    (tmp_path / "site.yml").write_text("---\n")

    assert check_implementation_map(specs, {"SSH": "ssh-hardening"}, tmp_path) == []


def test_render_traceability_lists_requirements_and_their_citers() -> None:
    rendered = render_traceability(
        [_req("SSH-1", spec="ssh-hardening", title="Password auth")],
        {"SSH-1": {Path("roles/ssh_hardening/tasks/main.yml")}},
    )

    assert "## ssh-hardening" in rendered
    assert "`SSH-1`" in rendered
    assert "`roles/ssh_hardening/tasks/main.yml`" in rendered
    assert rendered.endswith("\n")


def test_render_traceability_is_deterministic() -> None:
    requirements = [_req("SSH-2", spec="s"), _req("SSH-1", spec="s")]
    citations = {"SSH-1": {Path("b.yml"), Path("a.yml")}}

    first = render_traceability(requirements, citations)
    second = render_traceability(list(reversed(requirements)), citations)

    assert first == second
    assert first.index("`SSH-1`") < first.index("`SSH-2`")


def test_render_traceability_marks_uncited_requirements() -> None:
    rendered = render_traceability([_req("SSH-1", spec="s")], {})

    assert "—" in rendered


def test_run_checks_is_clean_for_a_consistent_tree(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _spec(specs, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)
    (tmp_path / "site.yml").write_text("# SSH-1\n")

    assert run_checks(tmp_path, specs, {"SSH": "ssh-hardening"}) == []


def test_run_checks_does_not_flag_allowances_outside_the_scoped_spec(
    tmp_path: Path,
) -> None:
    specs = tmp_path / "specs"
    _spec(specs, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)
    (tmp_path / "site.yml").write_text("# SSH-1\n")

    emergency_requirements = _FULL_REQUIREMENTS.replace(
        "### SSH-1 — A\n\nSHALL a.\n",
        "### EMRG-2 — Console access\n\nSHALL allow console root access.\n",
    ).replace("**Allowances claimed:** none", "**Allowances claimed:** ALW-1")
    _spec(specs, "emergency-access", emergency_requirements, _FULL_DESIGN)
    (tmp_path / "console.yml").write_text("# EMRG-2\n")

    (specs / "project").mkdir(parents=True, exist_ok=True)
    (specs / "project" / "security-invariants.md").write_text(
        "| Allowance | Invariant | Claimed by | Compensating control |\n"
        "|---|---|---|---|\n"
        "| ALW-1 | INV-1 | EMRG-2 | Console only |\n"
    )

    all_prefixes = {"SSH": "ssh-hardening", "EMRG": "emergency-access"}

    assert run_checks(tmp_path, specs, {"SSH": "ssh-hardening"}, all_prefixes) == []


def test_run_checks_collects_findings_from_every_check(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    requirements = _FULL_REQUIREMENTS.replace(
        "**Allowances claimed:** none",
        "**Allowances claimed:** none\n\n```\nunterminated\n",
    )
    _spec(specs, "ssh-hardening", requirements, _FULL_DESIGN)
    (tmp_path / "site.yml").write_text("# SSH-9\n")

    kinds = {f.kind for f in run_checks(tmp_path, specs, {"SSH": "ssh-hardening"})}

    assert kinds == {"dangling-citation", "orphan-requirement", "unclosed-code-fence"}


def test_main_returns_zero_when_clean(tmp_path: Path, monkeypatch, capsys) -> None:
    import tests.spec_check as spec_check

    specs = tmp_path / "specs"
    _spec(specs, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)
    (specs / "README.md").write_text(
        "| Prefix | Spec directory | Implemented by |\n"
        "|---|---|---|\n"
        "| `SSH` | `ssh-hardening` | `site.yml` |\n"
    )
    (tmp_path / "site.yml").write_text("# SSH-1\n")
    monkeypatch.setattr(spec_check, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(spec_check, "SPECS_DIR", specs)
    monkeypatch.setattr(spec_check, "TRACEABILITY_PATH", specs / "_traceability.md")

    assert spec_check.main([]) == 0
    assert (specs / "_traceability.md").is_file()
    assert "no findings" in capsys.readouterr().out.lower()


def test_main_does_not_write_the_index_on_a_scoped_run(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import tests.spec_check as spec_check

    specs = tmp_path / "specs"
    _spec(specs, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)
    (specs / "README.md").write_text(
        "| Prefix | Spec directory | Implemented by |\n"
        "|---|---|---|\n"
        "| `SSH` | `ssh-hardening` | `site.yml` |\n"
    )
    (tmp_path / "site.yml").write_text("# SSH-1\n")
    index = specs / "_traceability.md"
    index.write_text("sentinel\n")
    monkeypatch.setattr(spec_check, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(spec_check, "SPECS_DIR", specs)
    monkeypatch.setattr(spec_check, "TRACEABILITY_PATH", index)

    assert spec_check.main(["--spec", "ssh-hardening"]) == 0
    assert "no findings" in capsys.readouterr().out.lower()
    assert index.read_text() == "sentinel\n"


def test_main_returns_one_and_prints_findings(tmp_path: Path, monkeypatch, capsys) -> None:
    import tests.spec_check as spec_check

    specs = tmp_path / "specs"
    _spec(specs, "ssh-hardening", _FULL_REQUIREMENTS, _FULL_DESIGN)
    (specs / "README.md").write_text(
        "| Prefix | Spec directory | Implemented by |\n"
        "|---|---|---|\n"
        "| `SSH` | `ssh-hardening` | `site.yml` |\n"
    )
    (tmp_path / "site.yml").write_text("---\n")
    monkeypatch.setattr(spec_check, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(spec_check, "SPECS_DIR", specs)
    monkeypatch.setattr(spec_check, "TRACEABILITY_PATH", specs / "_traceability.md")

    assert spec_check.main(["--check"]) == 1
    assert "orphan-requirement" in capsys.readouterr().out
    assert not (specs / "_traceability.md").exists()
