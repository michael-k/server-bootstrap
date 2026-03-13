# Integration Testing with Incus VMs

Integration tests run the full bootstrap playbook (or individual roles) against real Debian virtual machines managed by [Incus](https://linuxcontainers.org/incus/).

## Prerequisites

Incus must be installed and its daemon running. Tests skip automatically if Incus is not available.

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

Integration tests use pytest fixtures that manage VM lifecycle automatically:

1. Launch a Debian VM via `incus launch`
2. Install `openssh-server` and inject an ephemeral SSH key
3. Run the bootstrap playbook (or individual roles) via `ansible-playbook`
4. Verify the resulting system state (users, SSH, firewall, etc.)
5. Destroy the VM on teardown

Two session-scoped fixtures provide VMs:

- **`bootstrap_vm`** — Debian VM with the full bootstrap playbook already applied. Used by most tests to verify post-bootstrap state.
- **`clean_vm`** — Debian VM with no bootstrap. Used by single-role tests that control exactly which roles run.

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
tests/
├── infra/                  # VM management infrastructure
│   ├── __init__.py         # Public exports (IncusVM, SSHKeyPair)
│   ├── __main__.py         # CLI: python -m tests.infra <command>
│   ├── ansible.py          # Ansible playbook execution helpers
│   ├── constants.py        # Defaults: image, timeouts, test variables
│   ├── fixtures.py         # Pytest fixtures (bootstrap_vm, clean_vm)
│   ├── ssh.py              # Ephemeral SSH keypair generation
│   └── vm.py               # IncusVM class (create/destroy/exec/ssh)
├── integration/
│   ├── conftest.py         # Registers fixtures and --debian-version
│   ├── test_bootstrap_integration.py  # Full bootstrap + verification
│   └── test_single_role.py           # Individual role tests
```

## Default Test Variables

The bootstrap playbook runs with these defaults (defined in `tests/infra/constants.py`):

| Variable | Value | Notes |
|----------|-------|-------|
| `manual_user_name` | `testuser` | |
| `deploy_user_name` | `ansible` | |
| `ssh_port` | `22` | |
| `tailscale_enabled` | `false` | Tailscale tests require multi-VM setup |
| `swap_enabled` | `false` | |

SSH key paths are injected automatically from the VM's ephemeral keypair.

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
