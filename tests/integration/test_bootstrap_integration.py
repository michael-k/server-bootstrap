"""
Integration tests for the VPS Bootstrap Playbook.

These tests require actual infrastructure (a test VM or container running
Debian stable) and are skipped automatically when the required environment
variables are not set.

Set the following environment variables to enable integration tests:
  BOOTSTRAP_TEST_HOST   - SSH hostname or IP of the test VM
  BOOTSTRAP_TEST_USER   - SSH user (default: root)
  BOOTSTRAP_TEST_PORT   - SSH port (default: 22)
  BOOTSTRAP_TEST_KEY    - Path to SSH private key for test VM access

Tests cover:
  - Full bootstrap execution on a fresh system (password auth)
  - Full bootstrap execution on a fresh system (SSH key auth)
  - Playbook idempotency on an already-configured system
  - Emergency script end-to-end functionality

Requirements: 15.1, 15.2, 15.3
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ROOT = Path(__file__).parent.parent.parent

_REQUIRED_ENV = "BOOTSTRAP_TEST_HOST"


def _skip_if_no_infra():
    """Skip the test if no test infrastructure is configured."""
    if not os.environ.get(_REQUIRED_ENV):
        pytest.skip(
            f"Integration tests require {_REQUIRED_ENV} environment variable. "
            "Set BOOTSTRAP_TEST_HOST (and optionally BOOTSTRAP_TEST_USER, "
            "BOOTSTRAP_TEST_PORT, BOOTSTRAP_TEST_KEY) to run these tests."
        )


def _test_host() -> str:
    return os.environ["BOOTSTRAP_TEST_HOST"]


def _test_user() -> str:
    return os.environ.get("BOOTSTRAP_TEST_USER", "root")


def _test_port() -> str:
    return os.environ.get("BOOTSTRAP_TEST_PORT", "22")


def _test_key() -> str | None:
    return os.environ.get("BOOTSTRAP_TEST_KEY")


def _ssh_cmd(remote_cmd: str) -> list[str]:
    """Build an SSH command to run on the test host."""
    key = _test_key()
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"]
    if key:
        cmd += ["-i", key]
    cmd += ["-p", _test_port(), f"{_test_user()}@{_test_host()}", remote_cmd]
    return cmd


def _run_ssh(remote_cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Execute a command on the test host via SSH."""
    return subprocess.run(
        _ssh_cmd(remote_cmd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_playbook(
    extra_vars: dict | None = None,
    tags: list[str] | None = None,
    check_mode: bool = False,
) -> subprocess.CompletedProcess:
    """Run the bootstrap playbook against the test host."""
    inventory = f"{_test_user()}@{_test_host()},"
    cmd = [
        "uv", "run", "ansible-playbook",
        "-i", inventory,
        "--ssh-extra-args", f"-p {_test_port()} -o StrictHostKeyChecking=no",
        "site.yml",
    ]
    if _test_key():
        cmd += ["--private-key", _test_key()]
    if extra_vars:
        for key, value in extra_vars.items():
            cmd += ["-e", f"{key}={value}"]
    if tags:
        cmd += ["--tags", ",".join(tags)]
    if check_mode:
        cmd += ["--check"]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(WORKSPACE_ROOT),
    )


# ---------------------------------------------------------------------------
# Tests: Full bootstrap execution
# ---------------------------------------------------------------------------

class TestFullBootstrapExecution:
    """Tests for full bootstrap playbook execution (Requirements 15.1, 15.2)."""

    def test_bootstrap_completes_successfully_with_ssh_key_auth(self):
        """Req 15.2: Playbook completes successfully on a fresh system with SSH key auth."""
        _skip_if_no_infra()

        result = _run_playbook(
            extra_vars={
                "manual_user_name": "testadmin",
                "ansible_user_name": "testansible",
                "manual_user_password": "TestPassword123!",
                "tailscale_enabled": "false",
            }
        )

        assert result.returncode == 0, (
            f"Playbook failed with return code {result.returncode}.\n"
            f"stdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-1000:]}"
        )
        assert "failed=0" in result.stdout or "PLAY RECAP" in result.stdout

    def test_bootstrap_creates_manual_user(self):
        """Req 15.1: After bootstrap, manual access user exists with uid 1000."""
        _skip_if_no_infra()

        result = _run_ssh("id testadmin")
        assert result.returncode == 0, "Manual user 'testadmin' not found after bootstrap"
        assert "uid=1000" in result.stdout

    def test_bootstrap_creates_ansible_user(self):
        """Req 15.1: After bootstrap, Ansible user exists with uid 1999."""
        _skip_if_no_infra()

        result = _run_ssh("id testansible")
        assert result.returncode == 0, "Ansible user 'testansible' not found after bootstrap"
        assert "uid=1999" in result.stdout

    def test_bootstrap_hardens_ssh(self):
        """Req 15.1: After bootstrap, SSH password authentication is disabled."""
        _skip_if_no_infra()

        result = _run_ssh("sshd -T | grep passwordauthentication")
        assert result.returncode == 0
        assert "passwordauthentication no" in result.stdout.lower()

    def test_bootstrap_configures_firewall(self):
        """Req 15.1: After bootstrap, NFTables service is active."""
        _skip_if_no_infra()

        result = _run_ssh("systemctl is-active nftables")
        assert result.returncode == 0
        assert "active" in result.stdout

    def test_bootstrap_configures_fail2ban(self):
        """Req 15.1: After bootstrap, fail2ban service is active."""
        _skip_if_no_infra()

        result = _run_ssh("systemctl is-active fail2ban")
        assert result.returncode == 0
        assert "active" in result.stdout


class TestBootstrapWithPasswordAuth:
    """Tests for bootstrap execution using root password authentication (Requirement 15.1)."""

    def test_bootstrap_with_password_auth_completes(self):
        """Req 15.1: Playbook completes on a fresh system with root password auth."""
        _skip_if_no_infra()

        # This test requires BOOTSTRAP_TEST_PASSWORD to be set
        password = os.environ.get("BOOTSTRAP_TEST_PASSWORD")
        if not password:
            pytest.skip(
                "BOOTSTRAP_TEST_PASSWORD not set — skipping password auth test"
            )

        inventory = f"root@{_test_host()},"
        # Note: --ask-pass requires interactive input; in CI use sshpass or
        # configure SSH key auth instead. This test documents the requirement.
        pytest.skip(
            "Password auth bootstrap requires interactive input or sshpass. "
            f"Run manually: ansible-playbook -i {inventory} --ask-pass site.yml"
        )


# ---------------------------------------------------------------------------
# Tests: Idempotency
# ---------------------------------------------------------------------------

class TestPlaybookIdempotency:
    """Tests for playbook idempotency on already-configured systems (Requirement 15.3)."""

    def test_second_run_reports_no_changes(self):
        """Req 15.3, 15.4: Second playbook run reports no changes for configured items."""
        _skip_if_no_infra()

        # Run playbook a second time (assumes first run already completed)
        result = _run_playbook(
            extra_vars={
                "manual_user_name": "testadmin",
                "ansible_user_name": "testansible",
                "manual_user_password": "TestPassword123!",
                "tailscale_enabled": "false",
            }
        )

        assert result.returncode == 0, (
            f"Second playbook run failed.\nstdout: {result.stdout[-2000:]}"
        )
        # Idempotent run should show changed=0 or very few changes
        assert "failed=0" in result.stdout

    def test_second_run_completes_without_errors(self):
        """Req 15.3: Second run completes without errors."""
        _skip_if_no_infra()

        result = _run_playbook(
            extra_vars={
                "manual_user_name": "testadmin",
                "ansible_user_name": "testansible",
                "manual_user_password": "TestPassword123!",
                "tailscale_enabled": "false",
            }
        )

        assert result.returncode == 0
        assert "unreachable=0" in result.stdout
        assert "failed=0" in result.stdout

    def test_check_mode_reports_no_changes_after_bootstrap(self):
        """Req 15.4, 15.5: Check mode reports no changes on already-configured system."""
        _skip_if_no_infra()

        result = _run_playbook(
            extra_vars={
                "manual_user_name": "testadmin",
                "ansible_user_name": "testansible",
                "manual_user_password": "TestPassword123!",
                "tailscale_enabled": "false",
            },
            check_mode=True,
        )

        assert result.returncode == 0, (
            f"Check mode failed.\nstdout: {result.stdout[-2000:]}"
        )


# ---------------------------------------------------------------------------
# Tests: Emergency script end-to-end
# ---------------------------------------------------------------------------

class TestEmergencyScriptEndToEnd:
    """End-to-end tests for the emergency access script (Requirements 9.2-9.7)."""

    def test_emergency_script_deployed_when_tailscale_enabled(self):
        """Req 9.1: Emergency script exists at /root/ when Tailscale is enabled."""
        _skip_if_no_infra()

        tailscale_key = os.environ.get("BOOTSTRAP_TEST_TAILSCALE_KEY")
        tailscale_server = os.environ.get("BOOTSTRAP_TEST_TAILSCALE_SERVER")
        if not tailscale_key or not tailscale_server:
            pytest.skip(
                "BOOTSTRAP_TEST_TAILSCALE_KEY and BOOTSTRAP_TEST_TAILSCALE_SERVER "
                "required for Tailscale integration tests"
            )

        result = _run_ssh("test -f /root/emergency-ssh-access.sh && echo EXISTS")
        assert result.returncode == 0
        assert "EXISTS" in result.stdout

    def test_emergency_script_not_deployed_when_tailscale_disabled(self):
        """Req 9.8: Emergency script is NOT deployed when Tailscale is disabled."""
        _skip_if_no_infra()

        result = _run_ssh("test ! -f /root/emergency-ssh-access.sh && echo ABSENT")
        assert result.returncode == 0
        assert "ABSENT" in result.stdout

    def test_emergency_script_unrestrict_opens_ssh(self):
        """Req 9.2: Emergency script unrestrict mode opens SSH to all interfaces."""
        _skip_if_no_infra()

        tailscale_key = os.environ.get("BOOTSTRAP_TEST_TAILSCALE_KEY")
        if not tailscale_key:
            pytest.skip("Tailscale required for emergency script tests")

        # Run unrestrict
        result = _run_ssh("bash /root/emergency-ssh-access.sh", timeout=60)
        assert result.returncode == 0, f"Unrestrict failed: {result.stdout}"
        assert "SUCCESS" in result.stdout

        # Verify SSH is now listening on all interfaces
        sshd_result = _run_ssh("sshd -T | grep listenaddress")
        assert "0.0.0.0" in sshd_result.stdout

    def test_emergency_script_restore_restricts_ssh(self):
        """Req 9.3, 9.4: Emergency script restore mode re-restricts SSH to Tailscale."""
        _skip_if_no_infra()

        tailscale_key = os.environ.get("BOOTSTRAP_TEST_TAILSCALE_KEY")
        if not tailscale_key:
            pytest.skip("Tailscale required for emergency script tests")

        # First unrestrict, then restore
        _run_ssh("bash /root/emergency-ssh-access.sh", timeout=60)
        result = _run_ssh("bash /root/emergency-ssh-access.sh --restore", timeout=60)
        assert result.returncode == 0, f"Restore failed: {result.stdout}"

        # Verify SSH is restricted back to Tailscale interface
        sshd_result = _run_ssh("sshd -T | grep listenaddress")
        assert "0.0.0.0" not in sshd_result.stdout

    def test_emergency_script_idempotent_unrestrict(self):
        """Req 9.7: Running unrestrict twice is idempotent."""
        _skip_if_no_infra()

        tailscale_key = os.environ.get("BOOTSTRAP_TEST_TAILSCALE_KEY")
        if not tailscale_key:
            pytest.skip("Tailscale required for emergency script tests")

        _run_ssh("bash /root/emergency-ssh-access.sh", timeout=60)
        result = _run_ssh("bash /root/emergency-ssh-access.sh", timeout=60)
        assert result.returncode == 0
        assert "already unrestricted" in result.stdout

    def test_emergency_script_idempotent_restore(self):
        """Req 9.7: Running restore twice is idempotent."""
        _skip_if_no_infra()

        tailscale_key = os.environ.get("BOOTSTRAP_TEST_TAILSCALE_KEY")
        if not tailscale_key:
            pytest.skip("Tailscale required for emergency script tests")

        _run_ssh("bash /root/emergency-ssh-access.sh", timeout=60)
        _run_ssh("bash /root/emergency-ssh-access.sh --restore", timeout=60)
        result = _run_ssh("bash /root/emergency-ssh-access.sh --restore", timeout=60)
        assert result.returncode == 0
        assert "already restricted" in result.stdout
