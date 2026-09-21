# incus — VM lifecycle management for integration testing

Launch, configure, and test against Incus VMs from Python.  Built for
the `server-bootstrap` project but usable by any downstream repo that
needs VM-based integration tests.

This package's requirements are `specs/incus-tooling/` in the
`server-bootstrap` repository. Where this file and that spec disagree, the
spec is authoritative and the disagreement is a bug.

## Installation

```bash
# Local path (recommended during development)
uv add --dev --editable --path ../server-bootstrap/incus "incus[fixtures]"

# Or from git
uv add --dev "incus[fixtures] @ git+https://github.com/michael-k/server-bootstrap.git#subdirectory=incus"
```

The `[fixtures]` extra includes pytest for projects that use the test
fixtures.

Both forms are explicit about where the package comes from, and that is not
optional: this package is **not published to any index**, so there is no
`uv add incus` that resolves to it. Worse, as of 2026-09-21 the name `incus`
on PyPI belongs to an unrelated project, so that command succeeds and
installs something else, failing later at import.

### What you inherit (INCUS-1)

The package is meant to be generic and currently is not. Installing it gives
you this project's defaults, with no parameter, environment variable or
configuration hook to change them:

| Inherited | Value | Consequence |
|---|---|---|
| VM name prefix | `bootstrap-test-` | your VMs are named like `server-bootstrap`'s, so `destroy --all` in either repo deletes the other's |
| Default image | `images:debian/13` | Debian only |
| Base image alias | `bootstrap/internal-base-{version}` | cached under this project's alias namespace |
| OS assumption | `apt-get`, `dpkg`, `sed` on `/etc/ssh/sshd_config`, `systemctl restart ssh`, `ansible_python_interpreter=/usr/bin/python3` | `wait_ready()` fails on a non-Debian image, and every generated inventory pins the interpreter path |
| Knock fallback | `[7000, 8500, 9100]` | `knock()` with no sequence uses this project's default |

This is recorded as a violation in `specs/incus-tooling/requirements.md`, not
as a feature — and the list there, like this one, is a floor rather than a
closed set.

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

One object per machine: it generates the name and the SSH keypair
(INCUS-14), launches (INCUS-2), waits for SSH (INCUS-12), and force-deletes
(INCUS-13).

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

`IncusVM` is **not** a context manager and has no finaliser, so `destroy()`
is the only thing that removes the ephemeral private key from your disk
(INCUS-8). Call it on the failure path too — every fixture in this project
wraps setup in `try`/`except` and destroys before re-raising.

### Running commands

```python
# Via SSH (uses ssh_user, ssh_port, handles port-knocking)
result = vm.ssh("systemctl is-active nginx")

# Via incus exec (bypasses SSH, runs as root)
result = vm.exec("cat /etc/hostname")

# Both return subprocess.CompletedProcess
```

Two paths on purpose (INCUS-3): `exec()` goes through the Incus agent rather
than the network, so it still works on a machine whose SSH has just been
narrowed, firewalled or knock-gated — which is what makes it the right way to
inspect the result of the thing under test.

### Port knocking

```python
vm.knock()                            # Uses knock_sequence or default [7000, 8500, 9100]
vm.knock(ports=[7000, 8500, 9100])    # Explicit sequence

# Or set knock_sequence and let ssh() handle it automatically
vm.knock_sequence = [7000, 8500, 9100]
vm.ssh("whoami")                      # Auto-knocks if last knock was >20s ago
```

INCUS-5: the 20-second threshold leaves margin inside the 30-second pass
window `KNOCK-7` grants, and the inter-knock delay stays inside its 5-second
stage window. The fallback sequence is a copy of `KNOCK-10`'s default, not a
read of it.

### File transfer

```python
vm.put_file("local/config.toml", "/etc/myapp/config.toml")
vm.get_file("/var/log/myapp.log", "test-output/myapp.log")
```

Push is INCUS-4, pull is INCUS-15. The remote path is concatenated onto the
VM name in both directions, so it must be absolute: a relative destination
addresses a different instance rather than failing.

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

INCUS-6: the stop command runs in a `finally`, so it runs even when the block
raises. Its own exit status is discarded — a stop command that fails leaves
the service running and reports nothing.

### SSH keypair

Each VM gets a fresh passphrase-less ed25519 keypair of its own, generated
into a private temp directory with the key at mode `0600` (INCUS-7). Nothing
is reused between VMs or between runs, and `destroy()` removes the directory.
Passing your own `ssh_key=` overrides that — and if you pass the same one to
two VMs, the first `destroy()` deletes the key the other is still using.

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

INCUS-9: your playbook, your variables, your working directory — they are
passed through as given, and nothing on the `IncusVM` is mutated. The
generated inventory is not opinion-free, though: it sets
`ansible_python_interpreter` to `/usr/bin/python3` and forces four SSH
options you cannot reach. `run_playbook` invokes `ansible-playbook` from your
`PATH`, not through `uv`, so the environment is yours to arrange.

## Pytest fixtures

Install with `incus[fixtures]` to get:

- **`clean_vm`** — session-scoped fixture providing a fresh Debian VM
  (no playbook applied).
- **`incus_available()`** — returns `False` when Incus is not installed
  or the daemon is not running; use with `pytest.skip()`.

INCUS-10: `incus_available()` is defined once so that your own fixtures ask
the same question `clean_vm` asks. `clean_vm` reads a `--debian-version`
option if your conftest declares one and falls back to the package default
otherwise.

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

## Command line

```bash
uv run python -m incus create [--debian VERSION]   # Create a bare Debian VM
uv run python -m incus list                        # List VMs whose name carries the prefix
uv run python -m incus destroy <name> | --all      # Destroy one, or every prefixed VM
uv run python -m incus ssh <name>                  # SSH in, falling back to incus exec
```

INCUS-16: those four are available wherever you run the command line.
INCUS-11: the `server-bootstrap`-specific
commands (`publish`, `images-clean`) are registered only when the **current
working directory** holds a `site.yml` — the guard reads the process's
working directory, not this package's location and not a repository root, so
running the same installation from a different directory offers a different
set of commands.

`list` and `destroy --all` select every Incus instance whose name starts with
`bootstrap-test-`. Since that prefix comes from the package, every repo using
this toolkit names its VMs the same way: a `destroy --all` here force-deletes
`server-bootstrap`'s running test VMs too, and vice versa. That is the
INCUS-1 finding above, with a concrete consequence.

## Internal base image

When a VM is launched from a raw upstream image (`images:debian/…`), `launch()`
automatically builds and caches a `bootstrap/internal-base-{version}` image with
openssh-server, curl, and `PermitRootLogin yes` pre-configured. This avoids the
slow `apt-get install` on every VM boot.

The base image is rebuilt automatically when the upstream Debian image fingerprint
changes. It is not intended for direct use by other projects — use
`bootstrap/open-{version}` or `bootstrap/knocking-{version}` instead.
