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
        result = bootstrap_vm.exec("id testuser")
        assert result.returncode == 0, "Manual user 'testuser' not found after bootstrap"
        assert "uid=1000" in result.stdout

    def test_bootstrap_creates_ansible_user(self, bootstrap_vm):
        """Req 15.1: After bootstrap, Ansible user exists with uid 1999."""
        result = bootstrap_vm.exec("id ansible")
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


class TestPortKnocking:
    """Tests for port knocking firewall feature."""

    def test_ssh_blocked_without_knock(self, bootstrap_vm):
        """SSH should be unreachable without performing the knock sequence."""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((bootstrap_vm.ip_address, bootstrap_vm.ssh_port))
            # If connect succeeds, SSH is open without knocking — unexpected
            sock.close()
            pytest.fail("SSH port is open without port knocking")
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass  # Expected: port is filtered/blocked

    def test_ssh_accessible_after_knock(self, bootstrap_vm):
        """SSH should be reachable after performing the correct knock sequence."""
        import socket

        bootstrap_vm.knock()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((bootstrap_vm.ip_address, bootstrap_vm.ssh_port))
            sock.close()
        except (ConnectionRefusedError, TimeoutError, OSError):
            pytest.fail("SSH port not accessible after port knocking")

    def test_port_knocking_rules_in_nftables(self, bootstrap_vm):
        """NFTables ruleset should contain port knocking sets and rules."""
        result = bootstrap_vm.exec("nft list ruleset")
        assert result.returncode == 0
        assert "knock4_stage1" in result.stdout
        assert "knock4_passed" in result.stdout


class TestBootstrapVerification:
    """Run the Ansible verification playbook against the bootstrapped VM."""

    def test_verify_playbook_passes(self, bootstrap_vm):
        """Run verify_bootstrap.yml and confirm all checks pass."""
        bootstrap_vm.knock()
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
        bootstrap_vm.knock()
        result = run_bootstrap_playbook(bootstrap_vm)
        assert result.returncode == 0, (
            f"Second playbook run failed.\nstdout: {result.stdout[-2000:]}"
        )
        assert "failed=0" in result.stdout
        assert "unreachable=0" in result.stdout

    def test_check_mode_reports_no_changes(self, bootstrap_vm):
        """Req 15.4, 15.5: Check mode reports no changes on configured system."""
        bootstrap_vm.knock()
        result = run_bootstrap_playbook(bootstrap_vm, check_mode=True)
        assert result.returncode == 0, (
            f"Check mode failed.\nstdout: {result.stdout[-2000:]}"
        )
        assert "changed=0" in result.stdout


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
