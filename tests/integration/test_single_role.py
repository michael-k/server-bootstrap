"""Integration tests: individual role execution against clean VMs."""


import pytest

from tests.infra.ansible import run_bootstrap_playbook

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestUsersRole:
    """Test the users role in isolation."""

    def test_creates_manual_user(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="users")
        assert result.returncode == 0, (
            f"Users role failed.\nstdout: {result.stdout[-3000:]}\nstderr: {result.stderr[-1000:]}"
        )

        check = clean_vm.exec("id testuser")
        assert check.returncode == 0
        assert "uid=1000" in check.stdout

    def test_creates_ansible_user(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="users")
        assert result.returncode == 0, (
            f"Users role failed.\nstdout: {result.stdout[-3000:]}\nstderr: {result.stderr[-1000:]}"
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
            f"SSH hardening role failed.\nstdout: {result.stdout[-3000:]}\nstderr: {result.stderr[-1000:]}"
        )

        check = clean_vm.exec("sshd -T | grep passwordauthentication")
        assert "passwordauthentication no" in check.stdout.lower()


class TestFirewallRole:
    """Test firewall role in isolation."""

    def test_nftables_configured(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="firewall")
        assert result.returncode == 0, (
            f"Firewall role failed.\nstdout: {result.stdout[-3000:]}\nstderr: {result.stderr[-1000:]}"
        )

        check = clean_vm.exec("systemctl is-active nftables")
        assert "active" in check.stdout


class TestLoggingRole:
    """Test logging role in isolation."""

    def test_journald_persistent(self, clean_vm):
        result = run_bootstrap_playbook(clean_vm, limit_to_role="logging")
        assert result.returncode == 0, (
            f"Logging role failed.\nstdout: {result.stdout[-3000:]}\nstderr: {result.stderr[-1000:]}"
        )

        check = clean_vm.exec("test -d /var/log/journal && echo EXISTS")
        assert "EXISTS" in check.stdout
