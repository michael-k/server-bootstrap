# Incus VM Integration Testing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automated integration testing using Incus VMs so the full bootstrap playbook and individual roles can be tested against real Debian virtual machines.

**Architecture:** A Python `tests/infra/` module wraps the `incus` CLI for VM lifecycle management. Pytest fixtures create/destroy VMs automatically. Make targets provide manual VM management. The same code serves both automated test flows and interactive debugging.

**Tech Stack:** Python 3.14, pytest, subprocess (wrapping `incus` CLI), ssh-keygen, Ansible (via `uv run ansible-playbook`)

**Spec:** `docs/superpowers/specs/2026-03-13-incus-integration-testing-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `tests/infra/__init__.py` | Package init, re-exports `IncusVM`, `SSHKeyPair` |
| `tests/infra/constants.py` | Defaults: image prefix, VM name prefix, timeouts, `DEFAULT_TEST_VARS` |
| `tests/infra/ssh.py` | `SSHKeyPair` class — ephemeral ed25519 keypair create/cleanup |
| `tests/infra/vm.py` | `IncusVM` class — create/destroy/exec/ssh/file ops via `incus` CLI |
| `tests/infra/ansible.py` | `run_bootstrap_playbook()`, `run_verify_playbook()` — inventory/playbook generation and execution |
| `tests/infra/fixtures.py` | Pytest fixtures: `bootstrap_vm`, `clean_vm`, Incus availability check |
| `tests/infra/__main__.py` | CLI entry point: `python -m tests.infra {create,list,destroy,ssh}` |
| `tests/integration/conftest.py` | New file — registers `--debian-version` option, imports fixtures from `tests/infra/fixtures.py` |
| `tests/integration/test_bootstrap_integration.py` | Existing file — rewritten to use Incus VM fixtures, covers full bootstrap + verification + idempotency |
| `tests/integration/test_single_role.py` | Individual role integration tests |
| `Makefile` | Modified — add `vm-create`, `vm-list`, `vm-destroy`, `vm-ssh` targets |

---

## Chunk 1: Infrastructure Foundation

### Task 1: Constants Module

**Files:**
- Create: `tests/infra/__init__.py`
- Create: `tests/infra/constants.py`

- [ ] **Step 1: Create the infra package with constants**

Create `tests/infra/__init__.py` (empty for now) and `tests/infra/constants.py`:

```python
"""Default constants for Incus VM integration testing."""


VM_NAME_PREFIX = "bootstrap-test-"

IMAGE_PREFIX = "images:debian/"

DEFAULT_DEBIAN_VERSION = "13"

VM_READY_TIMEOUT_SECONDS = 120

SSH_CONNECT_TIMEOUT_SECONDS = 10

SSH_POLL_INTERVAL_SECONDS = 2

DEFAULT_TEST_VARS: dict[str, str | int | bool] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    "manual_user_password": "$6$rounds=656000$testsalt$KiWOExmGav5tkvgH6hLZmBGbrNMmGrinaOwrUUmXFcQmBxJmBLXdMOFwlVYpXqBERvMOmflOBxVGHfnYBvFYX.",
    "manual_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "ansible_user_name": "ansible",
    "ansible_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "ssh_port": 22,
    "target_hostname": "bootstrap-test",
    "tailscale_enabled": False,
    "swap_enabled": False,
}
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS (no errors)

- [ ] **Step 3: Commit**

```bash
git add tests/infra/__init__.py tests/infra/constants.py
git commit -m "feat(test): add infra package with constants for Incus VM testing"
```

---

### Task 2: SSH Key Management

**Files:**
- Create: `tests/infra/ssh.py`

- [ ] **Step 1: Write the test for SSHKeyPair**

Add tests to a new file `tests/unit/test_ssh_keypair.py`:

```python
"""Unit tests for ephemeral SSH keypair management."""


import stat

import pytest

from tests.infra.ssh import SSHKeyPair


pytestmark = pytest.mark.unit


class TestSSHKeyPairCreate:
    def test_creates_private_key_file(self):
        kp = SSHKeyPair.create("test-vm")
        try:
            assert kp.private_key_path.exists()
        finally:
            kp.cleanup()

    def test_private_key_has_restricted_permissions(self):
        kp = SSHKeyPair.create("test-vm")
        try:
            mode = kp.private_key_path.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            kp.cleanup()

    def test_public_key_is_nonempty_string(self):
        kp = SSHKeyPair.create("test-vm")
        try:
            assert isinstance(kp.public_key, str)
            assert len(kp.public_key) > 0
            assert "ssh-ed25519" in kp.public_key
        finally:
            kp.cleanup()

    def test_private_key_in_unique_temp_directory(self):
        kp1 = SSHKeyPair.create("vm-a")
        kp2 = SSHKeyPair.create("vm-b")
        try:
            assert kp1.private_key_path.parent != kp2.private_key_path.parent
        finally:
            kp1.cleanup()
            kp2.cleanup()


class TestSSHKeyPairCleanup:
    def test_cleanup_removes_private_key(self):
        kp = SSHKeyPair.create("test-vm")
        key_path = kp.private_key_path
        kp.cleanup()
        assert not key_path.exists()

    def test_cleanup_removes_temp_directory(self):
        kp = SSHKeyPair.create("test-vm")
        temp_dir = kp.private_key_path.parent
        kp.cleanup()
        assert not temp_dir.exists()

    def test_cleanup_idempotent(self):
        kp = SSHKeyPair.create("test-vm")
        kp.cleanup()
        kp.cleanup()  # Should not raise
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `make test-unit`
Expected: FAIL — `ModuleNotFoundError` or `ImportError` for `tests.infra.ssh`

- [ ] **Step 3: Implement SSHKeyPair**

Create `tests/infra/ssh.py`:

```python
"""Ephemeral SSH keypair management for Incus VM testing."""


import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SSHKeyPair:
    """An ephemeral ed25519 SSH keypair for VM access."""

    private_key_path: Path
    public_key: str
    _temp_dir: Path

    @classmethod
    def create(cls, name: str) -> SSHKeyPair:
        """Generate a new ed25519 keypair in a unique temp directory.

        Args:
            name: Used in the key comment and temp directory name.
        """
        temp_dir = Path(tempfile.mkdtemp(prefix=f"bootstrap-test-{name}-"))
        key_path = temp_dir / "id_ed25519"

        subprocess.run(
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-f", str(key_path),
                "-N", "",
                "-C", f"bootstrap-test-{name}",
            ],
            capture_output=True,
            check=True,
        )

        key_path.chmod(0o600)
        public_key = key_path.with_suffix(".pub").read_text().strip()

        return cls(
            private_key_path=key_path,
            public_key=public_key,
            _temp_dir=temp_dir,
        )

    def cleanup(self) -> None:
        """Remove the keypair and its temp directory."""
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `make test-unit`
Expected: PASS — all SSHKeyPair tests green

- [ ] **Step 5: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/infra/ssh.py tests/unit/test_ssh_keypair.py
git commit -m "feat(test): add ephemeral SSH keypair management for VM testing"
```

---

### Task 3: IncusVM Class — Core Lifecycle

**Files:**
- Create: `tests/infra/vm.py`

- [ ] **Step 1: Write tests for IncusVM (mocked — no actual Incus needed)**

Create `tests/unit/test_incus_vm.py`. These test the command construction and parsing logic, not actual Incus calls:

```python
"""Unit tests for IncusVM command construction and parsing."""


import json
from unittest.mock import MagicMock, patch

import pytest

from tests.infra.vm import IncusVM


pytestmark = pytest.mark.unit


class TestIncusVMCreate:
    @patch("tests.infra.vm.subprocess.run")
    @patch("tests.infra.vm.SSHKeyPair.create")
    def test_create_calls_incus_launch_with_vm_flag(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM.create(image="images:debian/13")

        launch_call = mock_run.call_args_list[0]
        cmd = launch_call[0][0]
        assert "incus" in cmd[0]
        assert "launch" in cmd
        assert "--vm" in cmd
        assert "images:debian/13" in cmd
        assert vm.name.startswith("bootstrap-test-")

    @patch("tests.infra.vm.subprocess.run")
    @patch("tests.infra.vm.SSHKeyPair.create")
    def test_create_uses_cloud_init_for_ssh_key(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        IncusVM.create(image="images:debian/13")

        launch_call = mock_run.call_args_list[0]
        cmd = launch_call[0][0]
        # Cloud-init config is passed via --config flags
        cmd_str = " ".join(str(c) for c in cmd)
        assert "cloud-init" in cmd_str or "user.user-data" in cmd_str


class TestIncusVMName:
    @patch("tests.infra.vm.subprocess.run")
    @patch("tests.infra.vm.SSHKeyPair.create")
    def test_name_uses_prefix_and_random_suffix(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM.create(image="images:debian/13")
        assert vm.name.startswith("bootstrap-test-")
        suffix = vm.name[len("bootstrap-test-"):]
        assert len(suffix) > 0

    @patch("tests.infra.vm.subprocess.run")
    @patch("tests.infra.vm.SSHKeyPair.create")
    def test_name_hint_is_incorporated(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM.create(image="images:debian/13", name_hint="myvm")
        assert "myvm" in vm.name


class TestIncusVMDestroy:
    def test_destroy_calls_incus_delete_force(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock()
        vm._image = "images:debian/13"

        with patch("tests.infra.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.destroy()

        cmd = mock_run.call_args[0][0]
        assert cmd == ["incus", "delete", "bootstrap-test-abc123", "--force"]
        vm.ssh_key.cleanup.assert_called_once()


class TestIncusVMGetIP:
    def test_get_ip_parses_json_output(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock()
        vm._image = "images:debian/13"

        mock_output = json.dumps([{
            "name": "bootstrap-test-abc123",
            "state": {
                "network": {
                    "enp5s0": {
                        "addresses": [
                            {"family": "inet", "address": "10.0.0.42", "scope": "global"},
                        ]
                    }
                }
            }
        }])

        with patch("tests.infra.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
            ip = vm.get_ip()

        assert ip == "10.0.0.42"


class TestIncusVMExec:
    def test_exec_builds_correct_command(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock()
        vm._image = "images:debian/13"

        with patch("tests.infra.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.exec("whoami")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["incus", "exec", "bootstrap-test-abc123", "--", "sh", "-c", "whoami"]


class TestIncusVMSSH:
    def test_ssh_builds_correct_command(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")
        vm.ip_address = "10.0.0.42"
        vm._image = "images:debian/13"

        with patch("tests.infra.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "-i" in cmd
        assert "/tmp/fake/id_ed25519" in cmd
        assert "root@10.0.0.42" in cmd
        assert "whoami" in cmd
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `make test-unit`
Expected: FAIL — `ImportError` for `tests.infra.vm`

- [ ] **Step 3: Implement IncusVM**

Create `tests/infra/vm.py`:

```python
"""Incus VM lifecycle management for integration testing."""


import json
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from tests.infra.constants import (
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_POLL_INTERVAL_SECONDS,
    VM_NAME_PREFIX,
    VM_READY_TIMEOUT_SECONDS,
)
from tests.infra.ssh import SSHKeyPair


@dataclass
class IncusVM:
    """Manages a single Incus VM for testing."""

    name: str
    ssh_key: SSHKeyPair
    ip_address: str = ""
    _image: str = ""

    @classmethod
    def create(cls, image: str, name_hint: str = "") -> IncusVM:
        """Launch a new Incus VM with SSH access via cloud-init.

        Args:
            image: Incus image name, e.g. "images:debian/13".
            name_hint: Optional hint included in the VM name.
        """
        suffix = secrets.token_hex(4)
        name = f"{VM_NAME_PREFIX}{name_hint + '-' if name_hint else ''}{suffix}"

        ssh_key = SSHKeyPair.create(name)

        cloud_init = (
            "#cloud-config\n"
            "ssh_authorized_keys:\n"
            f"  - {ssh_key.public_key}\n"
        )

        subprocess.run(
            [
                "incus", "launch", image, name,
                "--vm",
                f"--config=user.user-data={cloud_init}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        return cls(name=name, ssh_key=ssh_key, _image=image)

    def destroy(self) -> None:
        """Force-delete the VM and clean up SSH keys."""
        subprocess.run(
            ["incus", "delete", self.name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.ssh_key.cleanup()

    def wait_ready(self, timeout: int = VM_READY_TIMEOUT_SECONDS) -> None:
        """Wait until the VM is running and SSH is reachable.

        Raises:
            TimeoutError: If the VM doesn't become ready within the timeout.
        """
        deadline = time.monotonic() + timeout

        # Wait for VM to be running
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["incus", "list", self.name, "--format=json"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                vms = json.loads(result.stdout)
                if vms and vms[0].get("status") == "Running":
                    break
            time.sleep(SSH_POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError(f"VM '{self.name}' did not start within {timeout}s")

        # Get IP address
        self.ip_address = self.get_ip()
        if not self.ip_address:
            # Poll for IP assignment
            while time.monotonic() < deadline:
                self.ip_address = self.get_ip()
                if self.ip_address:
                    break
                time.sleep(SSH_POLL_INTERVAL_SECONDS)
            else:
                raise TimeoutError(f"VM '{self.name}' did not get an IP within {timeout}s")

        # Wait for SSH to be reachable
        while time.monotonic() < deadline:
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "BatchMode=yes",
                    "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-i", str(self.ssh_key.private_key_path),
                    f"root@{self.ip_address}",
                    "echo ready",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and "ready" in result.stdout:
                return
            time.sleep(SSH_POLL_INTERVAL_SECONDS)

        raise TimeoutError(
            f"SSH not reachable on VM '{self.name}' ({self.ip_address}) within {timeout}s"
        )

    def get_ip(self) -> str:
        """Get the VM's IPv4 address from Incus."""
        result = subprocess.run(
            ["incus", "list", self.name, "--format=json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""

        vms = json.loads(result.stdout)
        if not vms:
            return ""

        network = vms[0].get("state", {}).get("network", {})
        for iface_name, iface in network.items():
            if iface_name == "lo":
                continue
            for addr in iface.get("addresses", []):
                if addr.get("family") == "inet" and addr.get("scope") == "global":
                    return addr["address"]
        return ""

    def exec(self, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a command inside the VM via incus exec (no SSH).

        The command is passed to sh -c so pipes and shell syntax work.
        """
        return subprocess.run(
            ["incus", "exec", self.name, "--", "sh", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def ssh(self, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command on the VM via SSH using the ephemeral key."""
        return subprocess.run(
            [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                "-i", str(self.ssh_key.private_key_path),
                f"root@{self.ip_address}",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def put_file(self, src: str | Path, dst: str) -> None:
        """Push a local file into the VM."""
        subprocess.run(
            ["incus", "file", "push", str(src), f"{self.name}{dst}"],
            capture_output=True,
            text=True,
            check=True,
        )

    def get_file(self, src: str, dst: str | Path) -> None:
        """Pull a file from the VM to local path."""
        subprocess.run(
            ["incus", "file", "pull", f"{self.name}{src}", str(dst)],
            capture_output=True,
            text=True,
            check=True,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make test-unit`
Expected: PASS — all IncusVM and SSHKeyPair tests green

- [ ] **Step 5: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/infra/vm.py tests/unit/test_incus_vm.py
git commit -m "feat(test): add IncusVM class for Incus CLI lifecycle management"
```

---

### Task 4: Ansible Playbook Helpers

**Files:**
- Create: `tests/infra/ansible.py`

- [ ] **Step 1: Write tests for the Ansible helpers**

Create `tests/unit/test_ansible_helpers.py`:

```python
"""Unit tests for Ansible playbook execution helpers."""

import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.infra.ansible import (
    build_inventory,
    build_single_role_playbook,
    run_bootstrap_playbook,
)


pytestmark = pytest.mark.unit


class TestBuildInventory:
    def test_generates_valid_yaml_inventory(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm)
        inv = yaml.safe_load(content)

        assert "all" in inv
        host_vars = inv["all"]["hosts"]["testvm"]
        assert host_vars["ansible_host"] == "10.0.0.42"
        assert host_vars["ansible_ssh_private_key_file"] == "/tmp/fake/id_ed25519"
        assert host_vars["ansible_user"] == "root"

    def test_uses_custom_ssh_port(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm, ssh_port=2222)
        inv = yaml.safe_load(content)
        assert inv["all"]["hosts"]["testvm"]["ansible_port"] == 2222


class TestBuildSingleRolePlaybook:
    def test_generates_playbook_with_single_role(self):
        content = build_single_role_playbook("ssh_hardening")
        playbook = yaml.safe_load(content)

        assert len(playbook) == 1
        play = playbook[0]
        assert play["become"] is True
        assert {"role": "ssh_hardening"} in play["roles"]

    def test_generates_playbook_with_role_list(self):
        content = build_single_role_playbook(["users", "ssh_hardening"])
        playbook = yaml.safe_load(content)

        play = playbook[0]
        assert len(play["roles"]) == 2
        assert {"role": "users"} in play["roles"]
        assert {"role": "ssh_hardening"} in play["roles"]


class TestRunBootstrapPlaybook:
    @patch("tests.infra.ansible.subprocess.run")
    def test_uses_site_yml_by_default(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(
            private_key_path=Path("/tmp/fake/id_ed25519"),
            public_key="ssh-ed25519 AAAA test",
        )

        run_bootstrap_playbook(vm)

        cmd = mock_run.call_args[0][0]
        assert "site.yml" in cmd

    @patch("tests.infra.ansible.subprocess.run")
    def test_passes_extra_vars_via_json_file(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(
            private_key_path=Path("/tmp/fake/id_ed25519"),
            public_key="ssh-ed25519 AAAA test",
        )

        run_bootstrap_playbook(vm, extra_vars={"ssh_port": 2222})

        cmd = mock_run.call_args[0][0]
        # Extra vars are passed via @<json_file>
        extra_var_args = [c for c in cmd if str(c).startswith("@")]
        assert len(extra_var_args) == 1
        assert "-e" in cmd


class TestRunVerifyPlaybook:
    @patch("tests.infra.ansible.subprocess.run")
    def test_uses_verify_playbook(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(
            private_key_path=Path("/tmp/fake/id_ed25519"),
            public_key="ssh-ed25519 AAAA test",
        )

        from tests.infra.ansible import run_verify_playbook
        run_verify_playbook(vm)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "verify_bootstrap.yml" in cmd_str
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make test-unit`
Expected: FAIL — `ImportError` for `tests.infra.ansible`

- [ ] **Step 3: Implement the Ansible helpers**

Create `tests/infra/ansible.py`:

```python
"""Ansible playbook execution helpers for integration testing."""


import json
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from tests.infra.constants import DEFAULT_TEST_VARS

if TYPE_CHECKING:
    from tests.infra.vm import IncusVM

WORKSPACE_ROOT = Path(__file__).parent.parent.parent


def build_inventory(vm: IncusVM, ssh_port: int = 22) -> str:
    """Generate a YAML inventory string pointing at the VM."""
    inventory = {
        "all": {
            "hosts": {
                "testvm": {
                    "ansible_host": vm.ip_address,
                    "ansible_user": "root",
                    "ansible_port": ssh_port,
                    "ansible_ssh_private_key_file": str(vm.ssh_key.private_key_path),
                    "ansible_ssh_common_args": "-o StrictHostKeyChecking=no",
                }
            }
        }
    }
    return yaml.dump(inventory, default_flow_style=False)


def build_single_role_playbook(roles: str | list[str]) -> str:
    """Generate a minimal playbook YAML for testing specific roles."""
    if isinstance(roles, str):
        roles = [roles]

    playbook = [
        {
            "name": "Test single role",
            "hosts": "all",
            "become": True,
            "gather_facts": True,
            "roles": [{"role": r} for r in roles],
        }
    ]
    return yaml.dump(playbook, default_flow_style=False)


def _write_ssh_public_key_file(vm: IncusVM) -> Path:
    """Write the VM's SSH public key to a temp file for Ansible to read."""
    pub_key_path = vm.ssh_key.private_key_path.with_suffix(".pub")
    if not pub_key_path.exists():
        pub_key_path.write_text(vm.ssh_key.public_key + "\n")
    return pub_key_path


def run_bootstrap_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    limit_to_role: str | list[str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    """Run site.yml (or a single role) against the VM.

    Args:
        vm: Target IncusVM instance.
        extra_vars: Additional variables merged on top of DEFAULT_TEST_VARS.
        limit_to_role: If set, generate a temporary playbook for these role(s) only.
        timeout: Command timeout in seconds.

    Returns:
        CompletedProcess with stdout/stderr from ansible-playbook.
    """
    pub_key_path = _write_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["ansible_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    # Use a temp directory for all generated files so cleanup is easy
    tmp_dir = tempfile.mkdtemp(prefix="bootstrap-ansible-")
    tmp_path = Path(tmp_dir)

    # Write temporary inventory
    inv_path = tmp_path / "inventory.yml"
    inv_path.write_text(build_inventory(vm))

    # Write extra vars as JSON (preserves booleans/ints correctly)
    vars_path = tmp_path / "extra_vars.json"
    vars_path.write_text(json.dumps(merged_vars))

    # Determine playbook path
    if limit_to_role:
        pb_path = tmp_path / "playbook.yml"
        pb_path.write_text(build_single_role_playbook(limit_to_role))
        playbook_path = str(pb_path)
    else:
        playbook_path = str(WORKSPACE_ROOT / "site.yml")

    cmd = [
        "uv", "run", "ansible-playbook",
        "-i", str(inv_path),
        "-e", f"@{vars_path}",
        playbook_path,
    ]

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
            check=False,
        )
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_verify_playbook(
    vm: IncusVM,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run verify_bootstrap.yml against the VM.

    Args:
        vm: Target IncusVM instance with bootstrap already applied.
        timeout: Command timeout in seconds.

    Returns:
        CompletedProcess with stdout/stderr from ansible-playbook.
    """
    tmp_dir = tempfile.mkdtemp(prefix="bootstrap-verify-")
    inv_path = Path(tmp_dir) / "inventory.yml"
    inv_path.write_text(build_inventory(vm))

    cmd = [
        "uv", "run", "ansible-playbook",
        "-i", str(inv_path),
        str(WORKSPACE_ROOT / "tests" / "verify_bootstrap.yml"),
    ]

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
            check=False,
        )
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make test-unit`
Expected: PASS

- [ ] **Step 5: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/infra/ansible.py tests/unit/test_ansible_helpers.py
git commit -m "feat(test): add Ansible playbook helpers for VM integration testing"
```

---

### Task 5: Update `tests/infra/__init__.py` exports

**Files:**
- Modify: `tests/infra/__init__.py`

- [ ] **Step 1: Add public exports**

```python
"""Infrastructure module for Incus VM integration testing."""

from tests.infra.ssh import SSHKeyPair
from tests.infra.vm import IncusVM

__all__ = ["IncusVM", "SSHKeyPair"]
```

- [ ] **Step 2: Run all tests**

Run: `make test-unit`
Expected: PASS — all existing and new tests green

- [ ] **Step 3: Commit**

```bash
git add tests/infra/__init__.py
git commit -m "feat(test): add public exports to infra package"
```

---

## Chunk 2: Pytest Fixtures, Integration Tests, and CLI

### Task 6: Pytest Fixtures and conftest

**Files:**
- Create: `tests/infra/fixtures.py`
- Create: `tests/integration/conftest.py`

- [ ] **Step 1: Implement the Incus availability check**

Create `tests/infra/fixtures.py`:

```python
"""Pytest fixtures for Incus VM integration testing."""


import os
import shutil
import subprocess

import pytest

from tests.infra.ansible import run_bootstrap_playbook
from tests.infra.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from tests.infra.vm import IncusVM


def incus_available() -> bool:
    """Check if Incus CLI is available and daemon is running."""
    if not shutil.which("incus"):
        return False
    result = subprocess.run(
        ["incus", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _should_keep(request: pytest.FixtureRequest) -> bool:
    """Check if VMs should be preserved on failure."""
    if not os.environ.get("KEEP_VM_ON_FAIL"):
        return False
    # Check if any test in the session failed
    if hasattr(request.session, "testsfailed"):
        return request.session.testsfailed > 0
    return False


def _print_debug_info(vm: IncusVM) -> None:
    """Print connection info for a preserved VM."""
    print(
        f"\nVM '{vm.name}' preserved for debugging.\n"
        f"  SSH: ssh -i {vm.ssh_key.private_key_path} root@{vm.ip_address}\n"
        f"  Cleanup: make vm-destroy VM={vm.name}\n"
    )


skip_no_incus = pytest.mark.skipif(
    not incus_available(),
    reason="Incus not available (not installed or daemon not running)",
)


@pytest.fixture(scope="session")
def bootstrap_vm(request):
    """Fresh Debian VM with bootstrap playbook already applied.

    Session-scoped: shared across all tests that use this fixture.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM.create(image=image)
    try:
        vm.wait_ready()
        result = run_bootstrap_playbook(vm)
        if result.returncode != 0:
            raise RuntimeError(
                f"Bootstrap playbook failed on VM '{vm.name}'.\n"
                f"stdout: {result.stdout[-3000:]}\n"
                f"stderr: {result.stderr[-1000:]}"
            )
    except Exception:
        if os.environ.get("KEEP_VM_ON_FAIL"):
            _print_debug_info(vm)
        else:
            vm.destroy()
        raise

    yield vm

    if _should_keep(request):
        _print_debug_info(vm)
    else:
        vm.destroy()


@pytest.fixture(scope="session")
def clean_vm(request):
    """Fresh Debian VM without bootstrap applied.

    Session-scoped: shared across tests that need to control which roles run.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM.create(image=image)
    try:
        vm.wait_ready()
    except Exception:
        if os.environ.get("KEEP_VM_ON_FAIL"):
            _print_debug_info(vm)
        else:
            vm.destroy()
        raise

    yield vm

    if _should_keep(request):
        _print_debug_info(vm)
    else:
        vm.destroy()
```

- [ ] **Step 2: Create the integration conftest**

Create `tests/integration/conftest.py`:

```python
"""Pytest configuration for integration tests."""


import pytest

# Import fixtures so pytest discovers them
from tests.infra.fixtures import bootstrap_vm, clean_vm  # noqa: F401


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --debian-version CLI option."""
    parser.addoption(
        "--debian-version",
        action="store",
        default="13",
        help="Debian version for Incus VMs (default: 13, also: trixie, testing, sid)",
    )
```

- [ ] **Step 3: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/infra/fixtures.py tests/integration/conftest.py
git commit -m "feat(test): add pytest fixtures and conftest for Incus VM integration"
```

---

### Task 7: Rewrite Integration Tests to Use Incus VM Fixtures

**Files:**
- Modify: `tests/integration/test_bootstrap_integration.py`
- Modify: `tests/infra/ansible.py`

This task replaces the existing env-var-based integration tests with the new Incus VM fixture-based tests. No separate `test_full_bootstrap.py` — this single file covers everything.

**Migrated:** full bootstrap execution, idempotency, check mode, emergency script not-deployed check.

**Intentionally dropped:** `TestBootstrapWithPasswordAuth` (was already a permanent `pytest.skip` — documented requirement, not a real test), and Tailscale-dependent emergency script tests (`test_emergency_script_unrestrict_opens_ssh`, `test_emergency_script_restore_restricts_ssh`, `test_emergency_script_idempotent_unrestrict`, `test_emergency_script_idempotent_restore`). These require a Tailscale/Headscale infrastructure that is part of the deferred multi-VM scenario spec.

- [ ] **Step 1: Add check_mode parameter to run_bootstrap_playbook**

In `tests/infra/ansible.py`, update the function signature to:

```python
def run_bootstrap_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    limit_to_role: str | list[str] | None = None,
    check_mode: bool = False,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
```

Then after the line `playbook_path,` and `]` that closes the `cmd` list, add:

```python
    if check_mode:
        cmd.append("--check")
```

- [ ] **Step 2: Rewrite test_bootstrap_integration.py**

Replace the entire file:

```python
"""
Integration tests for the VPS Bootstrap Playbook.

These tests use Incus VMs managed by pytest fixtures. Incus must be
installed and running. Tests are skipped automatically if Incus is
not available.

Tests cover:
  - Full bootstrap execution and post-bootstrap state verification
  - Ansible verification playbook pass-through
  - Playbook idempotency (second run + check mode)
  - Emergency script deployment (Tailscale-dependent tests skipped by default)

Requirements: 9.1-9.8, 15.1, 15.2, 15.3, 15.4, 15.5
"""

import pytest

from tests.infra.ansible import run_bootstrap_playbook, run_verify_playbook

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestFullBootstrapExecution:
    """Tests for full bootstrap playbook execution (Requirements 15.1, 15.2)."""

    def test_bootstrap_creates_manual_user(self, bootstrap_vm):
        """Req 15.1: After bootstrap, manual access user exists with uid 1000."""
        result = bootstrap_vm.ssh("id testuser")
        assert result.returncode == 0, "Manual user 'testuser' not found after bootstrap"
        assert "uid=1000" in result.stdout

    def test_bootstrap_creates_ansible_user(self, bootstrap_vm):
        """Req 15.1: After bootstrap, Ansible user exists with uid 1999."""
        result = bootstrap_vm.ssh("id ansible")
        assert result.returncode == 0, "Ansible user 'ansible' not found after bootstrap"
        assert "uid=1999" in result.stdout

    def test_bootstrap_hardens_ssh(self, bootstrap_vm):
        """Req 15.1: After bootstrap, SSH password authentication is disabled."""
        result = bootstrap_vm.exec("sshd -T | grep passwordauthentication")
        assert result.returncode == 0
        assert "passwordauthentication no" in result.stdout.lower()

    def test_bootstrap_configures_firewall(self, bootstrap_vm):
        """Req 15.1: After bootstrap, NFTables service is active."""
        result = bootstrap_vm.exec("systemctl is-active nftables")
        assert result.returncode == 0
        assert "active" in result.stdout

    def test_bootstrap_configures_fail2ban(self, bootstrap_vm):
        """Req 15.1: After bootstrap, fail2ban service is active."""
        result = bootstrap_vm.exec("systemctl is-active fail2ban")
        assert result.returncode == 0
        assert "active" in result.stdout

    def test_bootstrap_configures_journald(self, bootstrap_vm):
        """After bootstrap, journald has persistent logging."""
        result = bootstrap_vm.exec("test -d /var/log/journal && echo EXISTS")
        assert "EXISTS" in result.stdout


class TestBootstrapVerification:
    """Run the Ansible verification playbook against the bootstrapped VM."""

    def test_verify_playbook_passes(self, bootstrap_vm):
        """Run verify_bootstrap.yml and confirm all checks pass."""
        result = run_verify_playbook(bootstrap_vm)
        assert result.returncode == 0, (
            f"Verification playbook failed.\n"
            f"stdout: {result.stdout[-3000:]}\n"
            f"stderr: {result.stderr[-1000:]}"
        )
        assert "failed=0" in result.stdout


class TestPlaybookIdempotency:
    """Tests for playbook idempotency (Requirement 15.3)."""

    def test_second_run_reports_no_failures(self, bootstrap_vm):
        """Req 15.3, 15.4: Second playbook run completes without errors."""
        result = run_bootstrap_playbook(bootstrap_vm)
        assert result.returncode == 0, (
            f"Second playbook run failed.\nstdout: {result.stdout[-2000:]}"
        )
        assert "failed=0" in result.stdout
        assert "unreachable=0" in result.stdout

    def test_check_mode_reports_no_changes(self, bootstrap_vm):
        """Req 15.4, 15.5: Check mode reports no changes on configured system."""
        result = run_bootstrap_playbook(bootstrap_vm, check_mode=True)
        assert result.returncode == 0, (
            f"Check mode failed.\nstdout: {result.stdout[-2000:]}"
        )


class TestEmergencyScriptEndToEnd:
    """End-to-end tests for the emergency access script (Requirements 9.1-9.8).

    Most tests require Tailscale to be enabled, which is not the default
    test configuration. They are skipped unless a Tailscale-enabled
    bootstrap_vm is provided.
    """

    def test_emergency_script_not_deployed_when_tailscale_disabled(self, bootstrap_vm):
        """Req 9.8: Emergency script is NOT deployed when Tailscale is disabled."""
        result = bootstrap_vm.exec(
            "test ! -f /root/emergency-ssh-access.sh && echo ABSENT"
        )
        assert "ABSENT" in result.stdout
```

- [ ] **Step 3: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_bootstrap_integration.py tests/infra/ansible.py
git commit -m "refactor(test): rewrite integration tests to use Incus VM fixtures"
```

---

### Task 8: Single-Role Integration Tests

**Files:**
- Create: `tests/integration/test_single_role.py`

- [ ] **Step 1: Write single-role test file**

```python
"""Integration tests: individual role execution against clean VMs."""


import pytest

from tests.infra.ansible import run_bootstrap_playbook

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestUsersRole:
    """Test the users role in isolation."""

    def test_creates_manual_user(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="users")
        assert result.returncode == 0, (
            f"Users role failed.\nstdout: {result.stdout[-3000:]}"
        )

        check = clean_vm.exec("id testuser")
        assert check.returncode == 0
        assert "uid=1000" in check.stdout

    def test_creates_ansible_user(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="users")
        assert result.returncode == 0, (
            f"Users role failed.\nstdout: {result.stdout[-3000:]}"
        )

        check = clean_vm.exec("id ansible")
        assert check.returncode == 0
        assert "uid=1999" in check.stdout


class TestSSHHardeningRole:
    """Test SSH hardening role (requires users role first)."""

    def test_disables_password_auth(self, clean_vm):
        result = run_bootstrap_playbook(
            clean_vm,
            limit_to_role=["users", "ssh_hardening"],
        )
        assert result.returncode == 0, (
            f"SSH hardening role failed.\nstdout: {result.stdout[-3000:]}"
        )

        check = clean_vm.exec("sshd -T | grep passwordauthentication")
        assert "passwordauthentication no" in check.stdout.lower()


class TestFirewallRole:
    """Test firewall role in isolation."""

    def test_nftables_configured(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="firewall")
        assert result.returncode == 0, (
            f"Firewall role failed.\nstdout: {result.stdout[-3000:]}"
        )

        check = clean_vm.exec("systemctl is-active nftables")
        assert "active" in check.stdout


class TestLoggingRole:
    """Test logging role in isolation."""

    def test_journald_persistent(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="logging")
        assert result.returncode == 0, (
            f"Logging role failed.\nstdout: {result.stdout[-3000:]}"
        )

        check = clean_vm.exec("test -d /var/log/journal && echo EXISTS")
        assert "EXISTS" in check.stdout
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_single_role.py
git commit -m "feat(test): add single-role integration tests using Incus VMs"
```

---

### Task 9: CLI Entry Point

**Files:**
- Create: `tests/infra/__main__.py`

- [ ] **Step 1: Implement CLI entry point**

```python
"""CLI entry point for manual Incus VM management.

Usage:
    uv run python -m tests.infra create [--debian VERSION]
    uv run python -m tests.infra list
    uv run python -m tests.infra destroy <name>
    uv run python -m tests.infra destroy --all
    uv run python -m tests.infra ssh <name>
"""


import argparse
import json
import os
import subprocess
import sys

from tests.infra.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX, VM_NAME_PREFIX
from tests.infra.vm import IncusVM


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new test VM."""
    image = f"{IMAGE_PREFIX}{args.debian}"
    print(f"Creating VM with image {image}...")
    vm = IncusVM.create(image=image)
    print(f"VM '{vm.name}' launched. Waiting for SSH...")
    vm.wait_ready()
    print(f"VM '{vm.name}' ready.")
    print(f"  IP: {vm.ip_address}")
    print(f"  SSH: ssh -i {vm.ssh_key.private_key_path} root@{vm.ip_address}")
    print(f"  Destroy: make vm-destroy VM={vm.name}")

    # Save VM info for vm-ssh to find later
    info_path = vm.ssh_key.private_key_path.parent / "vm-info.json"
    info_path.write_text(json.dumps({
        "name": vm.name,
        "ip_address": vm.ip_address,
        "ssh_key": str(vm.ssh_key.private_key_path),
    }))


def cmd_list(args: argparse.Namespace) -> None:
    """List running test VMs."""
    result = subprocess.run(
        ["incus", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    vms = json.loads(result.stdout)
    test_vms = [v for v in vms if v["name"].startswith(VM_NAME_PREFIX)]

    if not test_vms:
        print("No test VMs running.")
        return

    for vm in test_vms:
        status = vm.get("status", "Unknown")
        ip = ""
        network = vm.get("state", {}).get("network", {})
        for iface_name, iface in network.items():
            if iface_name == "lo":
                continue
            for addr in iface.get("addresses", []):
                if addr.get("family") == "inet" and addr.get("scope") == "global":
                    ip = addr["address"]
                    break
        print(f"  {vm['name']}  {status}  {ip}")


def cmd_destroy(args: argparse.Namespace) -> None:
    """Destroy test VM(s)."""
    if args.all:
        result = subprocess.run(
            ["incus", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
        )
        vms = json.loads(result.stdout)
        test_vms = [v for v in vms if v["name"].startswith(VM_NAME_PREFIX)]

        if not test_vms:
            print("No test VMs to destroy.")
            return

        for vm in test_vms:
            name = vm["name"]
            print(f"Destroying {name}...")
            subprocess.run(
                ["incus", "delete", name, "--force"],
                capture_output=True,
                text=True,
                check=False,
            )
        print(f"Destroyed {len(test_vms)} test VM(s).")
    else:
        if not args.name:
            print("Error: specify a VM name or use --all", file=sys.stderr)
            sys.exit(1)
        print(f"Destroying {args.name}...")
        subprocess.run(
            ["incus", "delete", args.name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"Destroyed {args.name}.")


def cmd_ssh(args: argparse.Namespace) -> None:
    """SSH into a test VM."""
    import glob
    import tempfile

    patterns = [
        os.path.join(tempfile.gettempdir(), f"bootstrap-test-{args.name}*", "vm-info.json"),
        os.path.join(tempfile.gettempdir(), f"bootstrap-test-*{args.name}*", "vm-info.json"),
    ]

    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            with open(matches[0]) as f:
                info = json.loads(f.read())
            os.execvp("ssh", [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-i", info["ssh_key"],
                f"root@{info['ip_address']}",
            ])

    # Fallback: use incus exec (works even without saved SSH key)
    print(f"No saved SSH key found for '{args.name}'. Using incus exec instead.")
    os.execvp("incus", ["incus", "exec", args.name, "--", "/bin/bash"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Incus VMs for integration testing",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new test VM")
    p_create.add_argument(
        "--debian", default=DEFAULT_DEBIAN_VERSION,
        help=f"Debian version (default: {DEFAULT_DEBIAN_VERSION})",
    )

    # list
    subparsers.add_parser("list", help="List running test VMs")

    # destroy
    p_destroy = subparsers.add_parser("destroy", help="Destroy test VM(s)")
    p_destroy.add_argument("name", nargs="?", help="VM name to destroy")
    p_destroy.add_argument("--all", action="store_true", help="Destroy all test VMs")

    # ssh
    p_ssh = subparsers.add_parser("ssh", help="SSH into a test VM")
    p_ssh.add_argument("name", help="VM name")

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "destroy": cmd_destroy,
        "ssh": cmd_ssh,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/infra/__main__.py
git commit -m "feat(test): add CLI entry point for manual Incus VM management"
```

---

### Task 10: Make Targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add VM management and update Make targets**

Update the `.PHONY` line to:
```makefile
.PHONY: help bootstrap verify test test-unit test-property test-integration clean python-lint python-lint-fix ansible-lint ansible-lint-fix vm-create vm-list vm-destroy vm-ssh
```

Update the existing `test-integration` target to accept `$(ARGS)`:
```makefile
test-integration:
	@echo "Running integration tests..."
	uv run pytest -m integration $(ARGS)
```

Add to the help target output:
```
@echo "  vm-create          Create a test VM (DEBIAN=13|testing)"
@echo "  vm-list            List running test VMs"
@echo "  vm-destroy         Destroy test VM(s) (VM=name or all)"
@echo "  vm-ssh             SSH into a test VM (VM=name)"
```

Add the new targets after the `clean` target:

```makefile
vm-create:
	@echo "Creating test VM..."
	uv run python -m tests.infra create --debian $(or $(DEBIAN),13)

vm-list:
	@echo "Test VMs:"
	uv run python -m tests.infra list

vm-destroy:
	uv run python -m tests.infra destroy $(if $(VM),$(VM),--all)

vm-ssh:
	@test -n "$(VM)" || (echo "Usage: make vm-ssh VM=<name>" && exit 1)
	uv run python -m tests.infra ssh $(VM)
```

- [ ] **Step 2: Verify make targets parse correctly**

Run: `make help`
Expected: All new targets listed in help output

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(test): add Make targets for Incus VM management"
```

---

### Task 11: Smoke Test the Full Flow

This task verifies everything works end-to-end. It requires Incus to be installed.

- [ ] **Step 1: Create a VM manually**

Run: `make vm-create`
Expected: VM created, IP and SSH connection info printed

- [ ] **Step 2: List VMs**

Run: `make vm-list`
Expected: The created VM shown with status and IP

- [ ] **Step 3: SSH into the VM**

Run: `make vm-ssh VM=<name-from-step-1>`
Expected: Drops into a root shell on the VM

- [ ] **Step 4: Destroy the VM**

Run: `make vm-destroy`
Expected: VM destroyed, clean output

- [ ] **Step 5: Run integration tests**

Run: `make test-integration`
Expected: Tests run against auto-created Incus VMs. All pass (or skip if Incus not available).

- [ ] **Step 6: Run the full test suite**

Run: `make test`
Expected: Unit and property tests pass. Integration tests either pass or skip.

- [ ] **Step 7: Final commit if any fixes were needed**

Stage only the specific files that were modified during smoke testing, then commit:

```bash
git commit -m "fix(test): address issues found during integration test smoke testing"
```
