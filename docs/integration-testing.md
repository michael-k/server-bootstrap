# Integration Testing with Incus VMs

Integration tests run the full bootstrap playbook against real Debian virtual machines managed by [Incus](https://linuxcontainers.org/incus/). `run_bootstrap_playbook` still accepts a `limit_to_role` argument for running a subset of roles, but no test currently passes one.

## Prerequisites

Incus must be installed and its daemon running. Tests skip automatically if Incus is not available (TEST-4).

```bash
# Debian/Ubuntu
sudo apt install incus
sudo systemctl enable --now incusd

# Add your user to the incus-admin group
sudo usermod -aG incus-admin $USER
newgrp incus-admin

# Verify
incus list
```

The Tailscale suite additionally needs the GitHub CLI (`gh`) on `PATH` and
authenticated: it downloads the latest headscale release to run a control
server on one of its VMs. Unlike the Incus check, a `gh` that is missing,
unauthenticated or unable to reach GitHub fails the fixture rather than
skipping it.

## Quick Start

```bash
# Run all integration tests
make test-integration

# Preserve VMs on failure for debugging
KEEP_VM_ON_FAIL=1 make test-integration

# Test against Debian testing instead of 13
make test-integration ARGS="--debian-version testing"
```

## What the Tests Do

Integration tests use pytest fixtures that manage VM lifecycle automatically (TEST-3):

1. Launch a Debian VM via `incus launch`
2. Install `openssh-server` and inject an ephemeral SSH key
3. Run the bootstrap playbook via `ansible-playbook`
4. Verify the resulting system state (users, SSH, firewall, etc.)
5. Destroy the VM on teardown

Session-scoped fixtures provide the VMs. Each one skips the tests that use it
when Incus is unavailable (TEST-4):

- **`bootstrap_vm`** — Debian VM with the full bootstrap playbook already applied. Used by most tests to verify post-bootstrap state.
- **`swap_vm`** — as `bootstrap_vm`, but bootstrapped with zram and a disk swap file enabled. Used by the swap behaviour tests.
- **`tailscale_env`** — three VMs (a headscale control server, a tailnet peer, and a bootstrap target enrolled in the tailnet). Used by the Tailscale suite; its tests run in definition order and depend on each other's state.
- **`clean_vm`** — Debian VM with no bootstrap, re-exported from the shared `incus` package. No test in this repository currently uses it.

## Manual VM Workflow

For interactive debugging, you can manage VMs directly:

```bash
# Create a VM and wait for SSH
make vm-create
make vm-create DEBIAN=testing

# List running test VMs
make vm-list

# SSH into a VM
make vm-ssh VM=bootstrap-test-a1b2c3d4

# Destroy a specific VM
make vm-destroy VM=bootstrap-test-a1b2c3d4

# Destroy all test VMs
make vm-destroy
```

`make vm-create` prints the SSH command and VM name. The VM persists until you explicitly destroy it.

## Debugging Failed Tests

Set `KEEP_VM_ON_FAIL=1` to preserve VMs when tests fail or error:

```bash
KEEP_VM_ON_FAIL=1 make test-integration
```

On failure, the test output prints connection info:

```
VM 'bootstrap-test-a1b2c3d4' preserved for debugging.
  SSH: ssh -i /tmp/bootstrap-test-bootstrap-test-a1b2c3d4-.../id_ed25519 root@10.x.x.x
  Cleanup: make vm-destroy VM=bootstrap-test-a1b2c3d4
```

You can also use `incus exec` to get a shell without SSH:

```bash
incus exec bootstrap-test-a1b2c3d4 -- /bin/bash
```

## Test Structure

```
incus/                             # Shared package (installable by other projects)
├── pyproject.toml                 # Package metadata
└── src/incus/
    ├── __init__.py                # Public API: IncusVM, SSHKeyPair
    ├── __main__.py                # CLI: python -m incus <command>
    ├── ansible.py                 # Generic run_playbook() helper
    ├── constants.py               # Defaults: image prefix, timeouts
    ├── fixtures.py                # Generic fixtures: clean_vm, incus_available()
    ├── ssh.py                     # Ephemeral SSH keypair generation
    └── vm.py                      # IncusVM class (create/destroy/exec/ssh)

tests/
├── integration/
│   ├── helpers.py          # Bootstrap-specific: run_bootstrap_playbook, DEFAULT_TEST_VARS
│   ├── conftest.py         # Bootstrap fixtures (bootstrap_vm, swap_vm) + --debian-version
│   ├── test_bootstrap_integration.py  # Full bootstrap, behaviour, idempotency, swap
│   └── test_tailscale_integration.py  # Three-VM tailnet: narrowing + emergency access
```

## Default Test Variables

The bootstrap playbook runs with these defaults (defined in `tests/integration/helpers.py`):

| Variable | Value | Notes |
|----------|-------|-------|
| `manual_user_name` | `testuser` | |
| `deploy_user_name` | `ansible` | |
| `ssh_port` | `2222` | Deliberately not the default, so that a configured port is exercised |
| `target_hostname` | `bootstrap-test` | |
| `port_knocking_sequence` | `[7000, 8500, 9100]` | |
| `tailscale_enabled` | `false` | Tailscale tests require multi-VM setup |
| `swap_enabled` | `false` | |

SSH key paths are injected automatically from the VM's ephemeral keypair. The
dictionary also restates four `users` role defaults (`login_policy_umask`,
`login_policy_retries`, `login_policy_timeout`, `pam_faillock_deny`); nothing
checks that those copies still match `roles/users/defaults/main.yml`.

## External Tools Are Not Pinned

TEST-8: everything this suite fetches from outside the `uv` environment is
fetched at its current upstream version, deliberately.

| Fetched | Version used |
|---|---|
| Base image | The `images:debian/13` stream; `ensure_base_image()` re-reads its fingerprint every run and rebuilds the local base image when it has moved |
| headscale | Whatever `gh release view` reports as the latest release, cached per tag under `/tmp` |
| Tailscale (on the peer VM) | The vendor's current `https://tailscale.com/install.sh` |

The hosts this playbook bootstraps track those same moving upstreams, so
pinning here would make the suite reproducible at the cost of no longer
testing what is deployed. The trade is that a breaking upstream change shows
up as a test failure, and that it shows up the next time somebody runs
`make test-integration` by hand — this repository has no CI.

The Python dependencies are the opposite: `pyproject.toml` declares a lower
bound on each one it names (bar the local `incus` package) and `uv.lock` is
checked in, so `uv run` resolves the same versions on every machine.

## Targeting Debian Versions

The `--debian-version` option accepts any version string that Incus supports:

```bash
make test-integration ARGS="--debian-version 13"
make test-integration ARGS="--debian-version trixie"
make test-integration ARGS="--debian-version testing"
make test-integration ARGS="--debian-version sid"
```

## Cleanup

Test VMs are named with a `bootstrap-test-` prefix. To clean up all of them:

```bash
make vm-destroy
```

This finds and force-deletes all VMs matching the prefix.
