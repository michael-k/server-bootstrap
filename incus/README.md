# incus — VM lifecycle management for integration testing

Launch, configure, and test against Incus VMs from Python.  Built for
the `server-bootstrap` project but usable by any downstream repo that
needs VM-based integration tests.

## Installation

```bash
# Local path (recommended during development)
uv add --dev --editable --path ../server-bootstrap/incus "incus[fixtures]"

# Or from git
uv add --dev "incus[fixtures] @ git+https://github.com/michael-k/server-bootstrap.git#subdirectory=incus"
```

The `[fixtures]` extra includes pytest for projects that use the test
fixtures.

## Quick start

```python
from incus.vm import IncusVM

vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, auto_launch=True)
vm.wait_ready()

result = vm.ssh("systemctl is-active nginx")
assert result.returncode == 0

vm.destroy()
```

## IncusVM

### Construction

```python
# Minimal — auto-generates name and SSH keypair
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, auto_launch=True)

# With name hint for identification
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, name_hint="webserver", auto_launch=True)

# Two-step: construct first, launch later
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222)
vm.launch()

# Port-knocking image
vm = IncusVM(
    image="bootstrap/knocking-13",
    ssh_port=2222,
    knock_sequence=[7000, 8500, 9100],
    auto_launch=True,
)

# Non-root SSH user
vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, ssh_user="admin", auto_launch=True)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `image` | `str` | `"images:debian/13"` | Incus image to launch |
| `name` | `str` | auto-generated | VM name (`bootstrap-test-` + random suffix) |
| `ssh_key` | `SSHKeyPair \| None` | auto-generated | Ephemeral SSH keypair |
| `ip_address` | `str` | `""` | Set by `wait_ready()` |
| `ssh_port` | `int` | `22` | SSH port used by `ssh()` |
| `ssh_user` | `str` | `"root"` | User for `ssh()` connections |
| `knock_sequence` | `list[int] \| None` | `None` | Port-knock ports; enables auto-knock in `ssh()` |
| `name_hint` | `str` | `""` | Inserted into the generated name |
| `auto_launch` | `bool` | `False` | Call `launch()` after construction |

### Lifecycle

```python
vm.launch()       # Launch the VM in Incus
vm.wait_ready()   # Wait for boot + SSH ready (installs sshd, injects key)
vm.destroy()      # Force-delete VM and clean up keypair
```

### Running commands

```python
# Via SSH (uses ssh_user, ssh_port, handles port-knocking)
result = vm.ssh("systemctl is-active nginx")

# Via incus exec (bypasses SSH, runs as root)
result = vm.exec("cat /etc/hostname")

# Both return subprocess.CompletedProcess
```

### Port knocking

```python
vm.knock()                            # Uses knock_sequence or default [7000, 8500, 9100]
vm.knock(ports=[7000, 8500, 9100])    # Explicit sequence

# Or set knock_sequence and let ssh() handle it automatically
vm.knock_sequence = [7000, 8500, 9100]
vm.ssh("whoami")                      # Auto-knocks if last knock was >20s ago
```

### File transfer

```python
vm.put_file("local/config.toml", "/etc/myapp/config.toml")
vm.get_file("/var/log/myapp.log", "test-output/myapp.log")
```

### Properties

```python
vm.name              # str — e.g. "bootstrap-test-webserver-a1b2c3d4"
vm.image             # str — Incus image used
vm.ip_address        # str — IPv4 address (after wait_ready())
vm.private_key_path  # Path — ephemeral SSH private key
vm.public_key        # str — ephemeral SSH public key
```

### Background services

```python
with vm.background_service("systemctl start myapp", "systemctl stop myapp"):
    result = vm.ssh("curl -s http://localhost:8080/health")
```

## run_playbook

Run an Ansible playbook against a VM:

```python
from incus.ansible import run_playbook

result = run_playbook(
    vm,
    playbook_path=Path("site.yml"),
    extra_vars={"ssh_port": 2222},
    user="root",
    cwd=Path("/path/to/repo"),
    timeout=600,
    check_mode=False,
    roles=["my_role"],
    roles_path=Path("roles/"),
)
```

## Pytest fixtures

Install with `incus[fixtures]` to get:

- **`clean_vm`** — session-scoped fixture providing a fresh Debian VM
  (no playbook applied).
- **`incus_available()`** — returns `False` when Incus is not installed
  or the daemon is not running; use with `pytest.skip()`.

```python
from incus.fixtures import incus_available

@pytest.fixture(scope="session")
def my_vm(request):
    if not incus_available():
        pytest.skip("Incus not available")

    vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, auto_launch=True)
    vm.wait_ready()
    yield vm
    vm.destroy()
```
