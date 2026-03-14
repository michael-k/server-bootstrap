# Tailscale Integration Test Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an end-to-end integration test that verifies SSH is restricted to the tailnet, port knocking cannot bypass it, and the emergency script toggles public access without breaking tailnet connectivity.

**Architecture:** Three Incus VMs — a headscale server, a tailnet peer, and the bootstrap target. A `HeadscaleServer` helper in `tests/infra/headscale.py` manages the headscale lifecycle. A session-scoped pytest fixture wires all three VMs together. Six test methods verify SSH access from inside and outside the tailnet.

**Tech Stack:** Python, pytest, Incus VMs, headscale (latest release), tailscale, Ansible

**Spec:** `docs/superpowers/specs/2026-03-14-tailscale-integration-test-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `tests/infra/headscale.py` | New — `HeadscaleServer` class: download latest headscale binary, write config, start/stop server, create users and pre-auth keys |
| `tests/infra/__init__.py` | Modify — export `HeadscaleServer` |
| `tests/integration/test_tailscale_integration.py` | New — `TailscaleEnv` dataclass, `tailscale_env` fixture, `TestTailscaleIntegration` class with 6 test methods |

---

## Chunk 1: HeadscaleServer Helper

### Task 1: Create `tests/infra/headscale.py` with `HeadscaleServer` class

**Files:**
- Create: `tests/infra/headscale.py`

- [ ] **Step 1: Create the module with the HeadscaleServer class**

The class manages the full headscale lifecycle on an IncusVM. It needs these methods:

```python
"""Headscale server lifecycle management for integration testing."""

import json
import time
from dataclasses import dataclass, field

from tests.infra.vm import IncusVM

# Headscale GitHub API endpoint for latest release
_GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/juanfont/headscale/releases/latest"
)

_HEADSCALE_CONFIG = """\
server_url: http://{server_ip}:8080
listen_addr: 0.0.0.0:8080
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
database:
  type: sqlite
"""


@dataclass
class HeadscaleServer:
    """Manages a headscale control server on an Incus VM."""

    vm: IncusVM
    _user_created: bool = field(default=False, repr=False)

    def setup(self, timeout: int = 120) -> None:
        """Download, configure, and start headscale.

        1. Fetch the latest release URL from GitHub API.
        2. Download the linux_amd64 binary onto the VM.
        3. Write a minimal config file.
        4. Start headscale via systemd-run.
        5. Wait for the CLI to respond.
        6. Create the test user.
        """
        deadline = time.monotonic() + timeout

        # 1. Fetch latest release download URL
        self.vm.exec("apt-get update -qq && apt-get install -y -qq curl jq", timeout=60)
        result = self.vm.exec(
            f"curl -sL {_GITHUB_RELEASES_URL}"
            " | jq -r '.assets[] | select(.name | test(\"linux_amd64\")) | .browser_download_url'"
            " | head -1",
            timeout=30,
        )
        download_url = result.stdout.strip()
        if not download_url or download_url == "null":
            raise RuntimeError(
                f"Failed to find headscale download URL.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

        # 2. Download binary
        self.vm.exec(
            f"curl -sL -o /usr/local/bin/headscale '{download_url}'"
            " && chmod +x /usr/local/bin/headscale",
            timeout=60,
        )

        # 3. Write config
        self.vm.exec("mkdir -p /etc/headscale")
        config = _HEADSCALE_CONFIG.format(server_ip=self.vm.ip_address)
        # Use heredoc via sh to avoid quoting issues
        self.vm.exec(
            f"cat > /etc/headscale/config.yaml << 'HEADSCALE_EOF'\n{config}HEADSCALE_EOF"
        )

        # 4. Start headscale
        self.vm.exec(
            "systemd-run --unit=headscale --property=Restart=no "
            "headscale serve"
        )

        # 5. Wait for CLI to respond
        while time.monotonic() < deadline:
            result = self.vm.exec("headscale users list -o json 2>/dev/null")
            if result.returncode == 0:
                break
            time.sleep(2)
        else:
            status = self.vm.exec("systemctl status headscale")
            journal = self.vm.exec("journalctl -u headscale --no-pager -n 30")
            raise TimeoutError(
                f"Headscale did not become ready within {timeout}s.\n"
                f"status: {status.stdout}\n"
                f"journal: {journal.stdout}"
            )

        # 6. Create test user
        result = self.vm.exec("headscale users create testuser")
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create headscale user.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        self._user_created = True

    def create_preauth_key(self) -> str:
        """Generate a pre-authentication key for the test user.

        Returns the key string (e.g., 'tskey-auth-...').
        """
        if not self._user_created:
            raise RuntimeError("Call setup() before creating pre-auth keys")

        result = self.vm.exec(
            "headscale preauthkeys create --user testuser -o json"
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create pre-auth key.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        data = json.loads(result.stdout)
        # The JSON output format may vary by version; try common paths
        if isinstance(data, dict):
            key = data.get("key", data.get("preAuthKey", {}).get("key", ""))
        else:
            key = ""
        if not key:
            raise RuntimeError(
                f"Could not parse pre-auth key from output.\n"
                f"stdout: {result.stdout}"
            )
        return key

    def teardown(self) -> None:
        """Stop the headscale server."""
        self.vm.exec("systemctl stop headscale 2>/dev/null")
```

Key decisions:
- Uses `curl` + `jq` on the VM to fetch the GitHub release URL (avoids needing `requests` on the host).
- Config uses `database.type: sqlite` with default path — headscale creates it automatically.
- `systemd-run` for process management (cleaner than nohup, auto-cleanup).
- `create_preauth_key()` parses JSON output (`-o json` flag) for reliability.
- No pinned version — always latest release.

- [ ] **Step 2: Run linting to verify the module**

Run: `make python-lint`
Expected: PASS (no errors in new file)

- [ ] **Step 3: Run type checking**

Run: `make python-typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/infra/headscale.py
git commit -m "feat: add HeadscaleServer helper for integration testing"
```

### Task 2: Export HeadscaleServer from `tests/infra/__init__.py`

**Files:**
- Modify: `tests/infra/__init__.py`

- [ ] **Step 1: Add the export**

Change `tests/infra/__init__.py` to:

```python
"""Infrastructure module for Incus VM integration testing."""

from tests.infra.headscale import HeadscaleServer
from tests.infra.ssh import SSHKeyPair
from tests.infra.vm import IncusVM

__all__ = ["HeadscaleServer", "IncusVM", "SSHKeyPair"]
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/infra/__init__.py
git commit -m "feat: export HeadscaleServer from tests.infra"
```

---

## Chunk 2: Tailscale Integration Test File

### Task 3: Create test file with TailscaleEnv dataclass and helper functions

**Files:**
- Create: `tests/integration/test_tailscale_integration.py`

- [ ] **Step 1: Create the file with imports, dataclass, and SSH helper**

```python
"""
End-to-end integration tests for Tailscale + firewall + emergency access.

Three Incus VMs: a headscale control server, a tailnet peer, and the
bootstrap target. Verifies SSH is restricted to the tailnet, port
knocking cannot bypass it, and the emergency script toggles access.

Requirements: Tailscale integration, emergency access, firewall isolation
"""

import dataclasses
import os
import subprocess
import time

import pytest

from tests.infra.ansible import run_bootstrap_playbook
from tests.infra.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from tests.infra.fixtures import incus_available, print_debug_info
from tests.infra.headscale import HeadscaleServer
from tests.infra.vm import IncusVM

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Timeout for "should fail" SSH attempts — keep short
_SSH_FAIL_TIMEOUT = 5
# Timeout for "should succeed" SSH attempts
_SSH_OK_TIMEOUT = 10
# Timeout for tailscale peer connectivity
_PEER_TIMEOUT = 60

_MANUAL_USER = "testuser"
_PEER_KEY_PATH = "/root/.ssh/vm3_key"


@dataclasses.dataclass
class TailscaleEnv:
    """All three VMs and metadata needed by the test class."""

    headscale: IncusVM
    peer: IncusVM
    target: IncusVM
    target_ts_ipv4: str
    target_ts_ipv6: str
    manual_user: str


def _ssh_from_host(
    ip: str,
    port: int,
    user: str,
    key_path: str,
    timeout: int = _SSH_FAIL_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Attempt SSH from the host machine to an IP. Returns CompletedProcess."""
    return subprocess.run(
        [
            "ssh",
            "-p", str(port),
            "-o", "PubkeyAuthentication=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", f"ConnectTimeout={timeout}",
            "-i", key_path,
            f"{user}@{ip}",
            "echo SUCCESS",
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
        check=False,
    )


def _ssh_from_peer(
    peer_vm: IncusVM,
    target_ip: str,
    port: int,
    user: str,
    timeout: int = _SSH_OK_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run SSH from the peer VM to the target via incus exec."""
    cmd = (
        f"ssh -i {_PEER_KEY_PATH}"
        f" -o PubkeyAuthentication=yes"
        f" -o StrictHostKeyChecking=no"
        f" -o UserKnownHostsFile=/dev/null"
        f" -o BatchMode=yes"
        f" -o IdentitiesOnly=yes"
        f" -o ConnectTimeout={timeout}"
        f" -p {port}"
        f" {user}@{target_ip}"
        f" echo SUCCESS"
    )
    return peer_vm.exec(cmd, timeout=timeout + 10)


def _install_tailscale_on_peer(vm: IncusVM, login_server: str, authkey: str) -> None:
    """Raw-install tailscale on a VM and join the tailnet."""
    # Add Tailscale apt repo
    vm.exec(
        "curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg"
        " | tee /usr/share/keyrings/tailscale-archive-keyring.gpg > /dev/null",
        timeout=30,
    )
    # Get the Debian codename for the correct repo
    codename = vm.exec("lsb_release -cs 2>/dev/null || echo bookworm").stdout.strip()
    vm.exec(
        f'echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg]'
        f' https://pkgs.tailscale.com/stable/debian {codename} main"'
        f" | tee /etc/apt/sources.list.d/tailscale.list",
    )
    vm.exec("apt-get update -qq && apt-get install -y -qq tailscale", timeout=120)

    # Join the tailnet
    result = vm.exec(
        f"tailscale up --login-server={login_server} --authkey={authkey}"
        " --accept-routes --accept-dns=false",
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"tailscale up failed on peer.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    # Wait for Running state
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = vm.exec("tailscale status --json 2>/dev/null")
        if result.returncode == 0 and '"BackendState":"Running"' in result.stdout:
            return
        time.sleep(2)

    raise TimeoutError(
        f"Tailscale on peer did not reach Running state.\n"
        f"tailscale status: {vm.exec('tailscale status').stdout}"
    )


def _wait_for_peer(
    peer_vm: IncusVM, target_ip: str, timeout: int = _PEER_TIMEOUT,
) -> None:
    """Wait until the peer can ping the target via the tailnet."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = peer_vm.exec(f"tailscale ping --timeout=5s {target_ip}")
        if result.returncode == 0 and "pong" in result.stdout:
            return
        time.sleep(2)

    raise TimeoutError(
        f"Peer cannot reach {target_ip} via tailnet within {timeout}s.\n"
        f"peer tailscale status: {peer_vm.exec('tailscale status').stdout}\n"
    )


def _collect_diagnostics(
    headscale_vm: IncusVM, peer_vm: IncusVM, target_vm: IncusVM,
) -> str:
    """Collect diagnostic info from all VMs for debugging failures."""
    lines = ["\n=== DIAGNOSTICS ==="]

    for label, vm, cmds in [
        ("headscale", headscale_vm, [
            "headscale nodes list",
            "systemctl status headscale",
            "journalctl -u headscale --no-pager -n 20",
        ]),
        ("peer", peer_vm, [
            "tailscale status",
            "systemctl status tailscaled",
        ]),
        ("target", target_vm, [
            "tailscale status",
            "systemctl status tailscaled",
            "nft list ruleset",
            "ss -tlnp",
            "cat /etc/ssh/sshd_config | grep -E 'ListenAddress|Port'",
        ]),
    ]:
        lines.append(f"\n--- {label} ({vm.name}) ---")
        for cmd in cmds:
            result = vm.exec(cmd, timeout=10)
            lines.append(f"$ {cmd}")
            lines.append(result.stdout[:500] if result.stdout else "(empty)")

    return "\n".join(lines)
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tailscale_integration.py
git commit -m "feat: add tailscale integration test scaffolding"
```

### Task 4: Add the `tailscale_env` session-scoped fixture

**Files:**
- Modify: `tests/integration/test_tailscale_integration.py`

- [ ] **Step 1: Add the fixture after the helper functions**

Append to the file, after `_collect_diagnostics`:

```python
@pytest.fixture(scope="session")
def tailscale_env(request):
    """Three-VM environment: headscale server, tailnet peer, bootstrap target.

    Session-scoped — all tests in TestTailscaleIntegration share this fixture.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    # Step 1: Create all three VMs
    headscale_vm = IncusVM.create(image=image, name_hint="headscale")
    peer_vm = IncusVM.create(image=image, name_hint="ts-peer")
    target_vm = IncusVM.create(image=image, name_hint="ts-target")
    all_vms = [headscale_vm, peer_vm, target_vm]

    def _cleanup(preserve: bool = False) -> None:
        if preserve:
            for vm in all_vms:
                print_debug_info(vm)
        else:
            for vm in all_vms:
                vm.destroy()

    headscale = HeadscaleServer(vm=headscale_vm)

    try:
        # Wait for all VMs to be ready
        for vm in all_vms:
            vm.wait_ready()

        # Step 2: Set up headscale and generate pre-auth keys
        headscale.setup()
        key1 = headscale.create_preauth_key()
        key2 = headscale.create_preauth_key()

        # Step 3: Install tailscale on peer and join tailnet
        login_server = f"http://{headscale_vm.ip_address}:8080"
        _install_tailscale_on_peer(peer_vm, login_server, key1)

        # Step 4: Run bootstrap playbook on target with tailscale enabled
        result = run_bootstrap_playbook(
            target_vm,
            extra_vars={
                "tailscale_enabled": True,
                "tailscale_control_server": login_server,
                "tailscale_pre_auth_key": key2,
                "port_knocking_sequence": [7000, 8500, 9100],
            },
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Bootstrap playbook failed on target.\n"
                f"stdout: {result.stdout[-3000:]}\n"
                f"stderr: {result.stderr[-1000:]}"
            )

        # Step 5: Discover target's Tailscale IPs
        ts_ipv4 = target_vm.exec("tailscale ip -4").stdout.strip()
        ts_ipv6 = target_vm.exec("tailscale ip -6").stdout.strip()
        if not ts_ipv4 or not ts_ipv6:
            raise RuntimeError(
                f"Failed to discover Tailscale IPs on target.\n"
                f"ipv4: {ts_ipv4!r}, ipv6: {ts_ipv6!r}\n"
                f"tailscale status: {target_vm.exec('tailscale status').stdout}"
            )

        # Step 6: Push target's SSH private key onto peer
        peer_vm.exec("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        peer_vm.put_file(
            target_vm.ssh_key.private_key_path, _PEER_KEY_PATH
        )
        peer_vm.exec(f"chmod 600 {_PEER_KEY_PATH}")

        # Step 7 & 8: Wait for peer connectivity (IPv4 and IPv6)
        _wait_for_peer(peer_vm, ts_ipv4)
        _wait_for_peer(peer_vm, ts_ipv6)

    except Exception:
        diag = _collect_diagnostics(headscale_vm, peer_vm, target_vm)
        print(diag)
        _cleanup(preserve=bool(os.environ.get("KEEP_VM_ON_FAIL")))
        raise

    env = TailscaleEnv(
        headscale=headscale_vm,
        peer=peer_vm,
        target=target_vm,
        target_ts_ipv4=ts_ipv4,
        target_ts_ipv6=ts_ipv6,
        manual_user=_MANUAL_USER,
    )

    yield env

    # Teardown
    headscale.teardown()
    keep = bool(os.environ.get("KEEP_VM_ON_FAIL"))
    failed = getattr(request.session, "testsfailed", 0)
    errored = getattr(request.session, "testserrors", 0)
    _cleanup(preserve=keep and (failed + errored) > 0)
```

Key decisions:
- `put_file` pushes the private key directly from the host to the peer VM — no relay needed since `incus file push` works from the host to any VM.
- Diagnostics are printed before cleanup on failure.
- The fixture return type is omitted (matching existing fixture pattern in `fixtures.py`) since it's a generator via `yield`.

**Prerequisite:** Before implementing this task, rename `_print_debug_info` to `print_debug_info` in `tests/infra/fixtures.py` and update the two existing callers in the same file. This makes it a public API since it's now imported by a second module.

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tailscale_integration.py
git commit -m "feat: add tailscale_env session fixture with 3-VM setup"
```

### Task 5: Add the six test methods

**Files:**
- Modify: `tests/integration/test_tailscale_integration.py`

- [ ] **Step 1: Add the TestTailscaleIntegration class**

Append to the file:

```python
class TestTailscaleIntegration:
    """End-to-end tests for Tailscale + firewall + emergency access.

    Tests run in definition order. Each test builds on the state left
    by the previous one (especially tests 4 and 5 which toggle the
    emergency script).
    """

    def test_ssh_closed_from_host(self, tailscale_env: TailscaleEnv) -> None:
        """SSH from host to target's bridge IP must fail (firewall blocks it)."""
        env = tailscale_env
        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=str(env.target.ssh_key.private_key_path),
            timeout=_SSH_FAIL_TIMEOUT,
        )
        assert result.returncode != 0, (
            "SSH from host to target bridge IP succeeded — "
            "firewall is not restricting SSH to Tailscale interface"
        )
        assert "SUCCESS" not in result.stdout

    def test_port_knocking_does_not_bypass_tailscale(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Port knocking must NOT open SSH when Tailscale restricts it."""
        env = tailscale_env
        env.target.knock(ports=[7000, 8500, 9100])

        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=str(env.target.ssh_key.private_key_path),
            timeout=_SSH_FAIL_TIMEOUT,
        )
        assert result.returncode != 0, (
            "SSH from host succeeded after port knocking — "
            "knock sequence bypasses Tailscale restriction"
        )
        assert "SUCCESS" not in result.stdout

    def test_ssh_open_from_tailnet_peer(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """SSH from the tailnet peer to the target must succeed (IPv4 and IPv6)."""
        env = tailscale_env

        # IPv4
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv4, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer to target via Tailscale IPv4 failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # IPv6
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv6, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer to target via Tailscale IPv6 failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

    def test_emergency_script_unrestricts_ssh(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Emergency script opens SSH to all interfaces without breaking tailnet."""
        env = tailscale_env

        result = env.target.exec("/root/emergency-ssh-access.sh")
        assert result.returncode == 0, (
            f"Emergency script failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # SSH from host must now succeed
        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=str(env.target.ssh_key.private_key_path),
            timeout=_SSH_OK_TIMEOUT,
        )
        assert result.returncode == 0, (
            f"SSH from host failed after emergency unrestrict.\n"
            f"stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # SSH via tailnet IPv4 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv4, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv4 broke after emergency unrestrict.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # SSH via tailnet IPv6 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv6, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv6 broke after emergency unrestrict.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

    def test_emergency_script_restore(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Emergency --restore re-restricts SSH; tailnet access still works."""
        env = tailscale_env

        result = env.target.exec("/root/emergency-ssh-access.sh --restore")
        assert result.returncode == 0, (
            f"Emergency restore failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # SSH from host must fail again
        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=str(env.target.ssh_key.private_key_path),
            timeout=_SSH_FAIL_TIMEOUT,
        )
        assert result.returncode != 0, (
            "SSH from host still works after emergency restore — "
            "script did not re-restrict access"
        )
        assert "SUCCESS" not in result.stdout

        # SSH via tailnet IPv4 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv4, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv4 broke after emergency restore.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # SSH via tailnet IPv6 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv6, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv6 broke after emergency restore.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

    def test_tailscale_services_running(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Tailscaled service is enabled and running on the target."""
        env = tailscale_env

        result = env.target.exec("systemctl is-active tailscaled")
        assert result.returncode == 0, (
            f"tailscaled not active.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "active" in result.stdout

        result = env.target.exec("systemctl is-enabled tailscaled")
        assert result.returncode == 0, (
            f"tailscaled not enabled.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 3: Run type checking**

Run: `make python-typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_tailscale_integration.py
git commit -m "feat: add 6 tailscale integration test methods"
```

---

## Chunk 3: Verify and Run

### Task 6: Run the integration test

**Files:** None (verification only)

- [ ] **Step 1: Verify test collection**

Run: `uv run pytest tests/integration/test_tailscale_integration.py --collect-only`
Expected: 6 tests collected under `TestTailscaleIntegration`

- [ ] **Step 2: Run linting across all changed files**

Run: `make python-lint && make python-typecheck`
Expected: PASS

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `make test-unit && make test-property`
Expected: PASS (new files don't affect existing tests)

- [ ] **Step 4: Run the tailscale integration test**

Run: `make test-integration ARGS="tests/integration/test_tailscale_integration.py -v"`

If Incus is not available, the test will skip. If Incus is available, expect the full 3-VM setup and 6 test methods to execute. Note: this will take several minutes due to VM creation, headscale download, and tailscale installation.

If tests fail due to playbook bugs (e.g., sshd ListenAddress not bound to Tailscale IP), document the failures — those are real bugs that the spec expects to surface.

- [ ] **Step 5: Final commit if any adjustments were needed**

```bash
git add -u
git commit -m "fix: address integration test feedback"
```
