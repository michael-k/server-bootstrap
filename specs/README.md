# Specs — Authoritative Source of Truth

## 1. Authority

The `specs/` tree is the authoritative source of truth for this project. A
mismatch between a spec and the implementation is a bug — it does not matter
which side is "more correct" in the moment, the spec wins by definition. A
change to behaviour starts by editing the spec, gets reviewed as a spec
change, and only then is the implementation brought to match it.

## 2. Audience

`specs/` is written for developers, reviewers and auditors: it states what
the system SHALL do and why, in requirement form, so a change to behaviour
can be reviewed against a fixed statement of intent. `docs/` is separate and
serves a different audience: it is how-to material for users who operate or
consume the bootstrap, not a restatement of the requirements.

## 3. Requirement ID scheme

Every requirement has an ID of the form `PREFIX-N`, where `PREFIX` identifies
the spec (see the registry below) and `N` is a plain integer. IDs are flat
per spec — there is no sub-numbering. Each ID states exactly one `SHALL`. IDs
are permanent: once assigned, an ID is never renumbered and never reused,
even after the requirement it named is retired. A retired requirement keeps
its heading, with ` (withdrawn)` appended to the title, so the ID remains
visible in the document rather than disappearing.

Two body annotations cover requirements that are not backed by an ordinary
code citation:

- `**Traceability:** exempt — <reason>` marks a prose requirement that has no
  code site to cite (for example, a statement of scope or an invariant that
  other specs uphold).
- `**Traceability:** pending — <reason>` marks a requirement that is intended
  but not yet realised in the implementation.

A `pending` requirement is not a one-time note: `make spec-check` lists every
pending requirement and marks it in the traceability index on every run, so
the gap stays visible on each run instead of being recorded once and
forgotten.

## 4. Reference direction

Code cites the spec: a comment, docstring or test name references a
requirement ID (e.g. `SSH-3`) so a reader can find the rule it implements.
Those IDs are what `make spec-check` reads and what the traceability index
is built from.

Specs may name code. `**Verified:**` notes and `design.md` files routinely
name files, tests and task names, because they record what the
implementation does and how that was checked, and other spec prose names
code where that is the clearest way to state a fact. A reference to the
current code names the file, not a line in it: line numbers go stale on any
edit above them, and nothing checks them. The `## Implementation map`
section of a `design.md` remains the place that maps code paths to the
requirements they realise.

## 5. Prefix registry

This table is the single source of truth for prefixes. `tests/spec_check.py`
parses it to know which prefixes and spec directories are valid; do not
hardcode prefixes anywhere else.

| Prefix | Spec directory | Implemented by |
|---|---|---|
| `PRJ` | `project` | `site.yml`, `Makefile`, `pyproject.toml`, `ansible.cfg`, `inventory/` |
| `UPD` | `system-updates` | `roles/system_updates/` |
| `NET` | `networking` | `roles/networking/` |
| `HOST` | `hostname` | `roles/system_config/tasks/hostname.yml` |
| `TIME` | `time-sync` | `roles/system_config/tasks/time_sync.yml` |
| `FS` | `filesystem-hardening` | `roles/filesystem_hardening/` |
| `SWAP` | `swap` | `roles/swap/` |
| `LOG` | `logging` | `roles/logging/` |
| `USR` | `user-accounts` | `roles/users/` |
| `SUDO` | `sudo-hardening` | `roles/users/` |
| `LOGIN` | `login-policy` | `roles/users/` |
| `PAM` | `pam-hardening` | `roles/users/` |
| `SSH` | `ssh-hardening` | `roles/ssh_hardening/` |
| `TS` | `tailscale` | `roles/tailscale/` |
| `FW` | `firewall` | `roles/firewall/` |
| `KNOCK` | `port-knocking` | `roles/firewall/`, `site.yml` |
| `EMRG` | `emergency-access` | `roles/emergency_access/` |
| `F2B` | `fail2ban` | `roles/fail2ban/` |
| `VRFY` | `verification` | `tests/verify_bootstrap.yml` |
| `TEST` | `testing` | `tests/unit/`, `tests/property/`, `tests/integration/` |
| `INCUS` | `incus-tooling` | `incus/` |
| `IMG` | `image-publishing` | `incus/src/incus/__main__.py` |

`INV` and `ALW` are reserved for `specs/project/security-invariants.md` and
are exempt from the orphan check — invariants are cited by specs, not by
code.

## 6. `requirements.md` template

Every feature spec's `requirements.md` starts from this template:

````markdown
# <Feature> — Requirements

**Prefix:** `SSH`

## Purpose

One paragraph: what this feature is for and what would be worse without it.

## Scope

### In scope
### Out of scope

## Security invariants

**Upholds:** INV-2, INV-3
**Relies on:** INV-4 — the firewall drops anything this spec does not open.
**Allowances claimed:** none

## Requirements

### SSH-3 — Key exchange algorithms

THE Bootstrap SHALL restrict sshd key exchange algorithms to the algorithms listed in
`ssh_kex_algorithms`.

**Why:** Debian's default `KexAlgorithms` includes SHA-1 and small-group Diffie-Hellman.
**Verified:** `sshd -T` reports `kexalgorithms` exactly equal to `ssh_kex_algorithms`.
````

## 7. `design.md` template

Every feature spec's `design.md` starts from this template:

````markdown
# <Feature> — Design

## Approach

## Implementation map

| Path | Realises |
|---|---|
| `roles/ssh_hardening/templates/sshd_config.j2` | SSH-1 … SSH-18 |

## Key decisions

## Failure modes

## Interactions

Named by requirement ID: what this spec assumes of others, and what others assume of it.
````

## 8. Change process

1. Edit the spec first — `requirements.md`, and `design.md` if the approach
   changes.
2. Get the spec change reviewed.
3. Bring the implementation to match the spec.
4. Run `make spec-check`.

## 9. Index of specs

**Project-level**

- `project` — Ansible entry point, tooling and inventory conventions shared by all specs.
- `project/security-invariants.md` — Cross-cutting security invariants (`INV`) and allowances (`ALW`) that other specs uphold or rely on.

**Host basics**

- `system-updates` — Automatic and manual package update policy.
- `networking` — Static IPv6 addressing and netplan configuration.
- `hostname` — Hostname assignment and validation.
- `time-sync` — Time synchronization configuration.
- `filesystem-hardening` — Mount options and filesystem-level hardening.
- `swap` — Swap provisioning.
- `logging` — System logging configuration and retention.

**Access**

- `user-accounts` — Account creation, SSH key provisioning and account lifecycle.
- `sudo-hardening` — Sudo privilege configuration and restrictions.
- `login-policy` — Login restriction and lockout policy.
- `pam-hardening` — PAM stack hardening.
- `ssh-hardening` — sshd configuration hardening (ciphers, key exchange, authentication methods).

**Network exposure**

- `tailscale` — Tailscale VPN enrollment and configuration.
- `firewall` — Firewall rules and default-deny posture.
- `port-knocking` — Port-knocking sequence gating access to firewall-closed ports.
- `emergency-access` — Break-glass access path independent of normal hardening.
- `fail2ban` — Fail2ban jail configuration for brute-force mitigation.

**Assurance**

- `verification` — Post-bootstrap verification playbook.
- `testing` — Unit, property and integration test suites.
- `incus-tooling` — Incus container/VM tooling used for local testing.
- `image-publishing` — Base image build and publishing tool.

## 10. Traceability index

`specs/_traceability.md` is generated by `make spec-check` and must not be
hand-edited. Any change to it should come from re-running `make spec-check`,
not from a manual patch.
