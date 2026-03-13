# Incus VM Integration Testing Design

## Goal

Add automated integration testing using Incus VMs, so the full bootstrap playbook (and individual roles) can be tested against real Debian virtual machines with a single command.

## Scope

### In scope (this spec)

- Python module (`tests/infra/`) wrapping the `incus` CLI for VM lifecycle management
- Ephemeral ed25519 SSH keypair generation per VM
- Pytest fixtures for session-scoped VMs (bootstrapped and clean)
- `--debian-version` pytest CLI option (default: `13`, also supports `testing`)
- Full bootstrap + verification tests against a VM
- Single-role testing via generated temporary playbooks
- Make targets for manual VM management and automated test flow
- Configurable cleanup: destroy by default, `KEEP_VM_ON_FAIL=1` to preserve on failure
- Skip integration tests gracefully when Incus is not available

### Deferred (follow-up spec)

- Multi-VM scenarios (e.g., `vm_pair` fixture for Tailscale restriction testing)
- `make test-integration-all` for sequential multi-Debian-version runs
- Function-scoped `fresh_vm` fixture (one VM per test)

## Approach

Wrap the `incus` CLI via Python subprocess in a `tests/infra/` module. This module serves dual purpose: pytest fixtures for automated test flows, and a CLI entry point for manual VM management via Make targets. No external Incus SDK — the CLI is the primary supported interface.

## Project Structure

```
tests/
├── infra/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point: python -m tests.infra <action>
│   ├── vm.py              # IncusVM class — create/destroy/exec/ssh
│   ├── ssh.py             # Ephemeral SSH keypair generation
│   ├── fixtures.py        # Pytest fixtures
│   └── constants.py       # Defaults: image, naming prefix, timeouts
├── integration/
│   ├── conftest.py        # Registers fixtures and --debian-version option
│   ├── test_bootstrap_integration.py  # (existing file, updated to use fixtures)
│   ├── test_full_bootstrap.py         # Full playbook + verification
│   └── test_single_role.py           # Individual role testing
```

## IncusVM Class

Wraps the `incus` CLI to manage a single VM's lifecycle.

```
class IncusVM:
    name: str           # e.g., "bootstrap-test-a1b2c3"
    image: str          # e.g., "images:debian/13"
    ssh_key: SSHKeyPair # Ephemeral keypair for this VM
    ip_address: str     # Discovered after boot

    # Lifecycle
    create()            # incus launch <image> <name> --vm, inject SSH pubkey via cloud-init
    destroy()           # incus delete <name> --force
    wait_ready()        # Poll until VM is running + SSH is reachable

    # Interaction
    exec(cmd)           # incus exec <name> -- <cmd> (via Incus agent, no SSH)
    ssh(cmd)            # SSH using ephemeral key (tests real SSH path)
    put_file(src, dst)  # incus file push
    get_file(src, dst)  # incus file pull

    # Info
    get_ip()            # Parse from incus list --format json
```

### Naming

VMs are named `bootstrap-test-<random-suffix>` where the suffix is a short hex string. This prefix is used by `vm-destroy --all` to find and clean up test VMs.

### Cloud-init

The ephemeral SSH public key is injected via cloud-init user-data on VM creation. This is the standard mechanism for initial access to Incus VMs.

### Two Execution Paths

- `exec()` uses `incus exec` — goes through the Incus agent, no SSH required. Works even before SSH is configured. Used for pre-bootstrap setup steps.
- `ssh()` uses real SSH with the ephemeral key. Used for post-bootstrap verification, because the bootstrap playbook hardens SSH and we want to test that the hardened config actually works.

### `wait_ready()`

Polls for VM running state via `incus list`, then waits for SSH port to accept connections. Default timeout: 120 seconds. Raises a descriptive error on timeout.

## SSH Key Management

```
class SSHKeyPair:
    private_key_path: Path  # Temp file, e.g., /tmp/bootstrap-test-a1b2c3.key
    public_key: str         # In-memory, injected into cloud-init

    create()                # ssh-keygen -t ed25519, no passphrase
    cleanup()               # Delete private key file from disk
```

- Ed25519 keys, consistent with the project's SSH hardening requirements
- Private key stored in temp directory with `0600` permissions
- Each VM gets its own keypair
- `cleanup()` called during VM teardown (unless `KEEP_VM_ON_FAIL`)

## Pytest Fixtures

### Session-scoped: bootstrapped VM

```python
@pytest.fixture(scope="session")
def bootstrap_vm(request):
    """Fresh Debian VM with bootstrap playbook already applied."""
    image = request.config.getoption("--debian-version", "13")
    vm = IncusVM.create(image=f"images:debian/{image}")
    vm.wait_ready()
    run_bootstrap_playbook(vm)
    yield vm
    if not _should_keep(request):
        vm.destroy()
```

The workhorse fixture. Most tests verify state after a full bootstrap. Expensive to create (~2-3 minutes) but shared across all tests in the session.

### Session-scoped: clean VM

```python
@pytest.fixture(scope="session")
def clean_vm(request):
    """Fresh Debian VM, no bootstrap. For testing the playbook run itself."""
    image = request.config.getoption("--debian-version", "13")
    vm = IncusVM.create(image=f"images:debian/{image}")
    vm.wait_ready()
    yield vm
    if not _should_keep(request):
        vm.destroy()
```

For tests that need to observe the playbook run itself — idempotency testing, single-role testing, failure mode testing.

### `--debian-version` option

Registered in `conftest.py` via `pytest_addoption`. Accepts `13`, `trixie`, `testing`, or `sid`. Defaults to `13`.

### `KEEP_VM_ON_FAIL`

Checked via `os.environ` in fixture teardown. When set and any test failed, the VM is preserved and a message is printed:

```
VM 'bootstrap-test-a1b2c3' preserved for debugging.
  SSH: ssh -i /tmp/bootstrap-test-a1b2c3.key root@<ip>
  Cleanup: make vm-destroy VM=bootstrap-test-a1b2c3
```

### Helper: `run_bootstrap_playbook`

```python
def run_bootstrap_playbook(vm, extra_vars=None, limit_to_role=None):
    """Runs site.yml (or a single role) against the VM via ansible-playbook."""
```

Generates a temporary Ansible inventory pointing at the VM's IP with its ephemeral SSH key. When `limit_to_role` is specified, generates a temporary playbook that includes only the requested role(s) (accepts a string or list for prerequisite chains like `["users", "ssh_hardening"]`).

### Helper: `run_verify_playbook`

```python
def run_verify_playbook(vm):
    """Runs verify_bootstrap.yml against the VM."""
```

## Single-Role Testing

`run_bootstrap_playbook` with `limit_to_role` generates a minimal temporary playbook:

```yaml
---
- name: Test single role
  hosts: all
  become: true
  vars: { ... }
  roles:
    - role: ssh_hardening
```

`limit_to_role` accepts a list for roles with prerequisites:

```python
run_bootstrap_playbook(clean_vm, limit_to_role=["users", "ssh_hardening"])
```

The `clean_vm` fixture is used for single-role tests since you want to control exactly which roles run.

## Make Targets

```makefile
# VM lifecycle (manual use)
vm-create:
	uv run python -m tests.infra create --debian $(or $(DEBIAN),13)

vm-list:
	uv run python -m tests.infra list

vm-destroy:
	uv run python -m tests.infra destroy $(or $(VM),--all)

vm-ssh:
	uv run python -m tests.infra ssh $(VM)

# Automated integration testing
test-integration:
	uv run pytest -m integration $(ARGS)
```

- `make test-integration` — single command: fixtures create VMs, run tests, tear down
- `make vm-create` / `make vm-ssh` — manual debugging workflow
- `KEEP_VM_ON_FAIL=1 make test-integration` — preserve VMs on failure
- `make vm-destroy` — clean up all test VMs (matches `bootstrap-test-` prefix)

## Error Handling

### Incus not available

Integration tests skip with `pytest.skip("Incus not available")` if `incus` is not on `PATH` or the daemon isn't running. Checked in fixture setup.

### VM boot timeout

`wait_ready()` raises a descriptive error after the configurable timeout (default 120s). The VM is cleaned up unless `KEEP_VM_ON_FAIL` is set.

### Ansible playbook failure

`run_bootstrap_playbook()` captures stdout/stderr from `ansible-playbook` and includes it in the test failure message. The VM is preserved if `KEEP_VM_ON_FAIL` is set.

### Stale VM cleanup

`make vm-destroy` without `VM=` destroys all VMs matching the `bootstrap-test-` prefix. `make vm-list` shows running test VMs for manual inspection.

## Existing Integration Tests

The existing `test_bootstrap_integration.py` uses env vars (`BOOTSTRAP_TEST_HOST`, etc.) for manual infrastructure. This file will be updated to use the new fixtures instead, with the env var path removed.
