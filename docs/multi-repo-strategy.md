# Working Across Repositories

This document is how-to material for repositories built on `server-bootstrap`: worked examples for extending a bootstrapped host, the pre-built VM images, the shared test toolkit, and the workflows they support. The guaranteed machine state is defined in `specs/project/bootstrap-contract.md`.

## Repository Layout

```
config/
  server-bootstrap/    # This repo — base hardening
  headscale/           # Purpose-specific: headscale server
  nameserver/          # Purpose-specific: nameserver
  mailserver/          # Purpose-specific: mailserver
```

Purpose repos are **not coupled** to bootstrap: what they build on is the **machine state**, not the code. `specs/project/bootstrap-contract.md` owns that statement — what a purpose repo may assume, and what coupling to the code would mean — and is the place to change it.

## Extending a Bootstrapped Host

Worked examples for the two things a purpose repo does most often: connecting to a bootstrapped host, and opening a port on it. What each one is allowed to assume — and what survives a bootstrap re-run — is stated in `specs/project/bootstrap-contract.md`; only the example lives here.

### Connecting

Purpose-specific playbooks connect as the automation user with `become: true`:

```yaml
- name: Configure headscale server
  hosts: headscale
  become: true
  remote_user: ansible  # or whatever deploy_user_name was set to

  roles:
    - role: headscale
```

The contract's **Ansible connection model** states why no `become_password` appears here, what the playbook runner must hold to authenticate, and which address the target answers on once Tailscale is enabled.

### Opening a Port

Drop a rule file into `/etc/nftables.d/`. Files **must** use `add rule` syntax, because the base table already exists by the time the include is read:

```
# /etc/nftables.d/webserver.nft
add rule inet filter input tcp dport { 80, 443 } accept
```

After deploying a drop-in file, reload nftables to apply it:

```yaml
- name: Reload nftables to apply firewall rules
  ansible.builtin.systemd:
    name: nftables
    state: reloaded
```

The contract's **Extension points** entry for `/etc/nftables.d/*.nft` says why the file survives a bootstrap re-run, and names the one case where an appended rule is never reached.

Record each hole the drop-in opens in your repository's own exposure registers, one for holes public traffic can reach and one for holes open to tailnet peers, with the same columns as the registers in `specs/project/security-invariants.md` (PRJ-28).

## Integration Testing

Bootstrap provides two things for purpose-repo integration tests: pre-built VM images and a shared test toolkit.

### Pre-Built VM Images

Two Incus VM images are available locally, built with `make images` in server-bootstrap:

| Image alias | Description |
|---|---|
| `bootstrap/knocking-13` | Fully bootstrapped Debian 13 with port-knocking enabled, Tailscale disabled |
| `bootstrap/open-13` | Fully bootstrapped Debian 13 with port-knocking and Tailscale both disabled (SSH directly accessible) |

These images are the bootstrapped machine state frozen into a reusable snapshot. Launching a VM from one of these images is equivalent to running the bootstrap playbook from scratch, but takes seconds instead of minutes.

`IMG-2` is why the bootstrapped part of that state is trustworthy: an image is brought to it by applying `site.yml` rather than any substitute for it, so there is no second description of a bootstrapped host that could drift from the playbook. The equivalence is not exact, though, and `IMG-2` says where it is not: the build machine is launched from a cached base image carrying `openssh-server` and `curl`, and the test toolkit's readiness wait configures SSH and leaves its throwaway public key in root's `authorized_keys` before the playbook runs. A VM you launch from one of these images therefore has a little more on it than a from-scratch bootstrap would leave, and it shares its SSH host keys with every other VM launched from the same image (`IMG-12`).

What each image guarantees is `IMG-13` — every build uses one fixed set of bootstrap variables, so the bootstrap's own requirements are what hold inside an image. That spec lists the ones the variables decide, marks the list a floor, and names what does not apply: Tailscale is disabled in both images, so no `TS` and no `EMRG` requirement describes anything that is there.

`IMG-6` and `IMG-14` are the alias scheme: `bootstrap/<variant>-<version>`, the variant so you can pick one by name and the version so images for two Debian releases coexist on one daemon. `IMG-7` is why both variants are listed above rather than built individually — every run rebuilds both, so the two never differ by more than the variant that names them.

Rebuild them after bootstrap playbook changes:

```bash
cd server-bootstrap
make images
```

### Shared Test Toolkit (`incus` package)

The `incus/` directory in server-bootstrap is an installable Python package that provides VM lifecycle management for integration tests. Purpose repos install it as a dev dependency:

```bash
# Local path (recommended during development)
uv add --dev --editable --path ../server-bootstrap/incus "incus[fixtures]"

# Or from git
uv add --dev "incus[fixtures] @ git+https://github.com/michael-k/server-bootstrap.git#subdirectory=incus"
```

The `[fixtures]` extra includes pytest as a dependency for projects that use the test fixtures.

### What the Package Provides

| Import | Purpose |
|---|---|
| `incus.vm.IncusVM` | VM lifecycle: launch, destroy, exec, SSH, port-knock, file transfer |
| `incus.ansible.run_playbook` | Run any Ansible playbook against a VM |
| `incus.fixtures.clean_vm` | Pytest fixture: fresh VM (no playbook applied) |
| `incus.fixtures.incus_available` | Check if Incus is available (for skipping tests) |

### IncusVM Reference

#### Construction

```python
from incus.vm import IncusVM

# Minimal — auto-generates name and SSH keypair, defaults to images:debian/13
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, auto_launch=True)

# With name hint (appears in the generated VM name for easier identification)
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, name_hint="webserver", auto_launch=True)

# Two-step: construct first, launch later
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222)
vm.launch()

# Port-knocking image — set knock_sequence so ssh() auto-knocks
vm = IncusVM(
    image="bootstrap/knocking-13",
    ssh_port=2222,
    knock_sequence=[7000, 8500, 9100],
    auto_launch=True,
)

# Non-root SSH user (for testing against hardened images)
vm = IncusVM(
    image="bootstrap/open-13",
    ssh_port=2222,
    ssh_user="admin",
    auto_launch=True,
)
```

Constructor parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `image` | `str` | `"images:debian/13"` | Incus image to launch |
| `name` | `str` | auto-generated | VM name (prefix `bootstrap-test-` + random suffix) |
| `ssh_key` | `SSHKeyPair \| None` | auto-generated | Ephemeral SSH keypair; created automatically if not provided |
| `ip_address` | `str` | `""` | Set automatically by `wait_ready()` |
| `ssh_port` | `int` | `22` | SSH port used by `ssh()` |
| `ssh_user` | `str` | `"root"` | User for `ssh()` connections |
| `knock_sequence` | `list[int] \| None` | `None` | Port-knock sequence; when set, `ssh()` auto-knocks if last knock was >20s ago |
| `name_hint` | `str` | `""` | Inserted into the generated name for identification |
| `auto_launch` | `bool` | `False` | Call `launch()` immediately after construction |

#### Lifecycle

```python
vm.launch()                  # Launch the VM in Incus
vm.wait_ready()              # Wait for VM + SSH to be reachable (installs sshd, injects key)
vm.destroy()                 # Force-delete VM and clean up SSH keypair
```

`wait_ready()` handles everything needed to get from a freshly launched VM to a working SSH connection: waits for the VM to boot, waits for the Incus agent, obtains the IP address, installs openssh-server if needed, injects the ephemeral SSH key, and polls until SSH accepts connections.

#### Running Commands

```python
# Via SSH (uses ssh_user, ssh_port, handles port-knocking)
result = vm.ssh("systemctl is-active nginx")
assert result.returncode == 0
assert "active" in result.stdout

# Via incus exec (bypasses SSH, runs as root, always works)
result = vm.exec("cat /etc/hostname")
print(result.stdout)

# Both return subprocess.CompletedProcess with stdout, stderr, returncode
```

`ssh()` connects as `ssh_user` on `ssh_port`. If `knock_sequence` is set, it automatically port-knocks when the last knock was more than 20 seconds ago.

`exec()` runs commands via `incus exec` (no SSH needed). Useful for setup steps before SSH is available, or for inspecting state that the SSH user cannot access.

#### Port Knocking

```python
# Manual knock
vm.knock()                              # Uses knock_sequence, or default [7000, 8500, 9100]
vm.knock(ports=[7000, 8500, 9100])      # Explicit sequence

# Automatic — set knock_sequence and ssh() handles it
vm.knock_sequence = [7000, 8500, 9100]
vm.ssh("whoami")                        # Knocks automatically if needed
```

#### File Transfer

```python
# Push a local file into the VM
vm.put_file("local/config.toml", "/etc/myapp/config.toml")

# Pull a file from the VM
vm.get_file("/var/log/myapp.log", "test-output/myapp.log")
```

#### Properties

```python
vm.name              # str — VM name (e.g. "bootstrap-test-webserver-a1b2c3d4")
vm.image             # str — Incus image used
vm.ip_address        # str — IPv4 address (set after wait_ready())
vm.private_key_path  # Path — ephemeral SSH private key
vm.public_key        # str — ephemeral SSH public key
```

#### Background Services

```python
# Start a service for the duration of a test, guaranteed cleanup
with vm.background_service("systemctl start myapp", "systemctl stop myapp"):
    result = vm.ssh("curl -s http://localhost:8080/health")
    assert result.returncode == 0
```

### run_playbook Reference

```python
from incus.ansible import run_playbook

result = run_playbook(
    vm,                                    # IncusVM target
    playbook_path=Path("site.yml"),        # Playbook to run
    extra_vars={"ssh_port": 2222},         # Additional Ansible variables
    user="root",                           # SSH user for inventory
    cwd=Path("/path/to/repo"),             # Working directory
    timeout=600,                           # Subprocess timeout (seconds)
    check_mode=False,                      # --check mode
    roles=["my_role"],                     # Generate single-role playbook instead
    roles_path=Path("roles/"),             # ANSIBLE_ROLES_PATH for single-role runs
)
# Returns subprocess.CompletedProcess
```

### Writing Integration Tests

A purpose repo's integration test launches a VM from a pre-built bootstrap image, runs its own playbook on top, and verifies the result:

```python
# tests/integration/conftest.py
import pytest
from pathlib import Path
from incus.vm import IncusVM
from incus.ansible import run_playbook
from incus.fixtures import incus_available

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def server_vm(request):
    """VM with bootstrap + purpose-specific playbook applied."""
    if not incus_available():
        pytest.skip("Incus not available")

    vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, auto_launch=True)
    try:
        vm.wait_ready()
        result = run_playbook(
            vm,
            playbook_path=WORKSPACE_ROOT / "site.yml",
            extra_vars={"my_setting": "value"},
            cwd=WORKSPACE_ROOT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Playbook failed:\n{result.stderr[-1000:]}")
    except Exception:
        vm.destroy()
        raise

    yield vm
    vm.destroy()
```

```python
# tests/integration/test_my_service.py
def test_service_is_running(server_vm):
    result = server_vm.ssh("systemctl is-active my-service")
    assert result.returncode == 0

def test_port_is_listening(server_vm):
    result = server_vm.ssh("ss -tlnp | grep :8080")
    assert result.returncode == 0
```

#### Testing with Port Knocking

```python
@pytest.fixture(scope="session")
def knocking_vm(request):
    """VM with port-knocking enabled."""
    if not incus_available():
        pytest.skip("Incus not available")

    vm = IncusVM(
        image="bootstrap/knocking-13",
        ssh_port=2222,
        knock_sequence=[7000, 8500, 9100],
        auto_launch=True,
    )
    try:
        vm.wait_ready()
    except Exception:
        vm.destroy()
        raise

    yield vm
    vm.destroy()


def test_service_behind_knock(knocking_vm):
    # ssh() auto-knocks because knock_sequence is set
    result = knocking_vm.ssh("systemctl is-active my-service")
    assert result.returncode == 0
```

### Choosing an Image

- Use `bootstrap/open-13` when your tests need direct SSH access to the VM (most cases).
- Use `bootstrap/knocking-13` when your tests need to verify behavior behind port-knocking. Set `knock_sequence` on the VM so `ssh()` auto-knocks.

### CLI Tools

The package also provides VM management commands, useful for debugging:

```bash
uv run python -m incus create              # Create a bare Debian VM
uv run python -m incus create --debian 13  # Specify Debian version
uv run python -m incus list                # List test VMs
uv run python -m incus ssh <name>          # SSH into a VM
uv run python -m incus destroy --all       # Clean up all test VMs
```

## Workflows

### New VPS

1. Provision VPS (Debian 13+, root access)
2. Run bootstrap → hardened base
3. Run purpose-specific playbook → server ready

### Applying Bootstrap Updates

1. Make changes in `server-bootstrap`
2. Re-run bootstrap against affected hosts
3. Check that no purpose repository writes a file listed under "Bootstrap-owned files" in `specs/project/bootstrap-contract.md`: an edit to one of those files is lost on the re-run

