# Bootstrap Contract

This document defines the machine state that `server-bootstrap` produces. Purpose-specific repos (headscale, nameserver, mailserver, etc.) build on top of this state.

## Repository Layout

```
config/
  server-bootstrap/    # This repo — base hardening
  headscale/           # Purpose-specific: headscale server
  nameserver/          # Purpose-specific: nameserver
  mailserver/          # Purpose-specific: mailserver
```

Purpose repos are **not coupled** to bootstrap. They don't import, depend on, or reference bootstrap roles. The contract is the **machine state** described below, not the code.

## Guaranteed Machine State

After a successful bootstrap run, a coding agent working on a purpose-specific repo can assume everything in this section.

### Operating System

- Debian 13 (trixie) or newer, fully patched (`dist-upgrade` applied)
- Hostname configured (if `system_hostname` was set)

### Time Synchronization

- NTP-based time sync is active via either chrony or systemd-timesyncd (configurable, default: chrony)
- NTP servers: Debian pool (`0-3.debian.pool.ntp.org`)

### Logging

- Persistent journald logging
- Retention: 1 month, max 500 MB disk usage
- Purpose repos should log to journald (via systemd units) — logs will be retained and queryable with `journalctl`

### User Accounts

| Property | Manual user | Automation user |
|---|---|---|
| Default name | `admin` | `ansible` |
| UID | 1000 | 1999 |
| Shell | `/bin/bash` | `/bin/bash` |
| SSH auth | Key-only | Key-only |
| Password login | Has password (for sudo) | Disabled (`!`) |
| Sudo | Password-required (`ALL=(ALL:ALL) ALL`) | Passwordless (`NOPASSWD:ALL`) |

- Root SSH access is disabled
- `su` is restricted to `wheel` group members (manual user is in `wheel`)

### Login Hardening

- Shell idle timeout: 600 seconds (via `/etc/profile.d/shell-timeout.sh`)
- Console root login restricted to `tty1`–`tty6` only (via `securetty` + `pam_securetty`)
- Hardened `login.defs` (umask `027`, 3 retries, 30s timeout)
- PAM faillock: account locked after 5 failures within 15 minutes, unlocked after 10 minutes
- PAM resource limits: nproc 1024 (root 2048), nofile 4096 (root 8192)
- Sudo hardening: environment sanitization, logging, 5-minute credential timeout

### SSH

- Key-only authentication (passwords disabled)
- Port: 22 (configurable via `ssh_port`)
- Max 3 auth attempts, 30s login grace time
- Client alive interval: 300s, max 2 missed keepalives
- X11/TCP/agent forwarding: disabled
- `AllowGroups ssh-users` — only members of the `ssh-users` group can log in
- Strong algorithms only:
  - **KEX**: curve25519-sha256, diffie-hellman-group16-sha512, diffie-hellman-group18-sha512
  - **Ciphers**: chacha20-poly1305, aes256-gcm, aes128-gcm
  - **MACs**: hmac-sha2-512-etm, hmac-sha2-256-etm
- When Tailscale is enabled: SSH listens only on the Tailscale interface IPs

### Firewall (nftables)

- **Default-deny** inbound policy (input chain policy: `drop`)
- **Default-deny** forwarding (forward chain policy: `drop`)
- **Allow-all** outbound (output chain policy: `accept`)
- Loopback, established/related, and ICMP/ICMPv6 traffic allowed
- SSH access is governed by one of three modes:
  - **Tailscale-restricted** (default when Tailscale enabled): SSH accepted only on `tailscale0` interface, plus UDP 41641 (WireGuard) open on all interfaces
  - **Port knocking** (default when Tailscale disabled): SSH hidden behind a 3-port TCP knock sequence (default: 7000, 8500, 9100) with configurable timeouts
  - **Open** (when both Tailscale and port knocking disabled): SSH accepted on all interfaces

**Extension point:** `/etc/nftables.d/*.nft` — bootstrap creates this directory and includes it at the end of `/etc/nftables.conf`. Purpose repos drop rule files here. Files **must** use `add rule` syntax since the base table already exists. Example:

```
# /etc/nftables.d/webserver.nft
add rule inet filter input tcp dport { 80, 443 } accept
```

Bootstrap owns `/etc/nftables.conf` and regenerates it on re-run, but the `include` directive and `/etc/nftables.d/` directory are preserved. Drop-in files survive bootstrap re-runs. After deploying a drop-in file, reload nftables to apply:

```yaml
- name: Reload nftables to apply firewall rules
  ansible.builtin.systemd:
    name: nftables
    state: reloaded
```

### Intrusion Prevention (fail2ban)

- Monitors SSH via systemd journal
- Bans IPs after 5 failures within 10 minutes (10-minute ban)
- Uses `nftables-multiport` ban action
- Purpose repos can add additional fail2ban jails by dropping config into `/etc/fail2ban/jail.d/`

### Filesystem Hardening

- `/tmp` — mounted with `noexec,nosuid,nodev` (drop-in override or bind-mount, depending on base system)
- `/dev/shm` — mounted with `noexec,nosuid,nodev` (drop-in override)
- `/var/tmp` — bind-mounted to `/tmp` (inherits restrictions)

Purpose repos should be aware that executables cannot run from `/tmp`, `/var/tmp`, or `/dev/shm`.

### Tailscale VPN (if enabled)

- Connected to a Headscale control server
- `tailscale0` interface up with assigned IPv4 and IPv6 addresses
- WireGuard port (UDP 41641) open in firewall
- DNS acceptance disabled, routes accepted
- Emergency SSH restore script at `/root/emergency-ssh-access.sh`

### Swap (if configured)

- **Zram** (if enabled): compressed RAM swap using LZ4, priority 100
- **Disk swap** (if configured): swapfile at `/swapfile`, priority 10 (used after zram is exhausted)

## Ansible Connection Model

Purpose-specific playbooks connect as the automation user with `become: true`:

```yaml
- name: Configure headscale server
  hosts: headscale
  become: true
  remote_user: ansible  # or whatever deploy_user_name was set to

  roles:
    - role: headscale
```

- The automation user has passwordless sudo — no `become_password` needed
- SSH key auth only — the playbook runner must have the matching private key
- If Tailscale is enabled, the target is only reachable via its Tailscale IP

## Bootstrap-Owned Files

Bootstrap overwrites these on every run. Purpose repos must not modify them.

- `/etc/nftables.conf`
- `/etc/ssh/sshd_config`
- `/etc/fail2ban/jail.local`
- `/etc/systemd/journald.conf`
- `/etc/hostname`
- `/etc/chrony/chrony.conf` (or `/etc/systemd/timesyncd.conf`)
- `/etc/login.defs`
- `/etc/securetty`
- `/etc/sudoers.d/00-sudo-security`
- `/etc/sudoers.d/<manual_user_name>`
- `/etc/sudoers.d/<deploy_user_name>`
- `/etc/profile.d/shell-timeout.sh`
- `/etc/security/faillock.conf`
- `/etc/security/limits.d/50-hardening.conf`
- `/usr/share/pam-configs/faillock`
- `/etc/systemd/system/tmp.mount` (or `tmp.mount.d/hardening.conf`)
- `/etc/systemd/system/dev-shm.mount.d/hardening.conf`
- `/etc/systemd/system/var-tmp.mount`
- `/root/emergency-ssh-access.sh` (if Tailscale enabled)

## What Purpose Repos Must Not Do

- Modify any file in the bootstrap-owned list above
- Import, reference, or depend on bootstrap roles or role internals
- Duplicate bootstrap functionality (don't re-configure SSH, don't re-create users)
- Depend on bootstrap-internal details (nftables chain names, systemd unit internals)

## Extension Points

These are the designated places where purpose repos integrate with the bootstrapped system:

| Extension point | How to use | Survives bootstrap re-run? |
|---|---|---|
| `ssh-users` group | Add users to this group to grant SSH access | Yes |
| `/etc/sudoers.d/<name>` | Drop sudoers rules for service users (don't overwrite `00-sudo-security`, `<manual_user>`, or `<deploy_user>`) | Yes |
| `/etc/nftables.d/*.nft` | Drop firewall rules using `add rule` syntax, then reload nftables | Yes |
| `/etc/fail2ban/jail.d/*.conf` | Drop jail configs for service-specific intrusion prevention | Yes |
| systemd units | Create new services — they log to journald automatically | Yes |
| apt packages | Install any package (bootstrap runs `dist-upgrade` on re-run, which may update them) | Yes |

Beyond the extension points above, purpose repos can also:
- Use the automation user (`ansible` by default) for Ansible-driven configuration
- Assume the Tailscale interface exists if `tailscale_enabled` was set

## Integration Testing

Bootstrap provides two things for purpose-repo integration tests: pre-built VM images and a shared test toolkit.

### Pre-Built VM Images

Two Incus VM images are available locally, built with `make images` in server-bootstrap:

| Image alias | Description |
|---|---|
| `bootstrap/knocking-13` | Fully bootstrapped Debian 13 with port-knocking enabled, Tailscale disabled |
| `bootstrap/open-13` | Fully bootstrapped Debian 13 with port-knocking and Tailscale both disabled (SSH directly accessible) |

These images are the bootstrapped machine state frozen into a reusable snapshot. Launching a VM from one of these images is equivalent to running the bootstrap playbook from scratch, but takes seconds instead of minutes.

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
vm = IncusVM(image="bootstrap/open-13", auto_launch=True)

# With name hint (appears in the generated VM name for easier identification)
vm = IncusVM(image="bootstrap/open-13", name_hint="webserver", auto_launch=True)

# Two-step: construct first, launch later
vm = IncusVM(image="bootstrap/open-13")
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

    vm = IncusVM(image="bootstrap/open-13", auto_launch=True)
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
2. Re-run bootstrap against affected hosts (idempotent)
3. Purpose-specific config is unaffected

