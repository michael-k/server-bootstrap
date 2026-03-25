"""
Integration tests for the VPS Bootstrap Playbook.

These tests use Incus VMs managed by pytest fixtures. Incus must be
installed and running. Tests are skipped automatically if Incus is
not available.

Tests cover:
  - Full bootstrap execution and post-bootstrap state verification
  - Behavioral verification of each security control
  - Ansible verification playbook pass-through
  - Playbook idempotency (second run + check mode)
  - Emergency script deployment (Tailscale-dependent tests skipped by default)

Requirements: 9.1-9.8, 13.1-13.17, 15.1, 15.2, 15.3, 15.4, 15.5
"""

import contextlib
import socket
import subprocess
import time
from pathlib import Path

import pytest

from incus.constants import SSH_CONNECT_TIMEOUT_SECONDS
from tests.integration.helpers import run_bootstrap_playbook, run_verify_playbook

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ssh_attempt(
    vm,
    *,
    user: str = "root",
    key_path: str | Path | None = None,
    extra_opts: list[str] | None = None,
    timeout: int = 10,
) -> subprocess.CompletedProcess:
    """Attempt an SSH connection to the VM and return the result.

    Uses BatchMode and IdentitiesOnly so the connection never hangs and
    only the specified key is offered (prevents SSH agent from exhausting
    MaxAuthTries with unrelated keys).
    """
    cmd = [
        "ssh",
        "-p", str(vm.ssh_port),
        "-o", "PubkeyAuthentication=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
    ]
    if key_path:
        cmd += ["-i", str(key_path)]
    if extra_opts:
        cmd += extra_opts
    cmd += [f"{user}@{vm.ip_address}", "echo SUCCESS"]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False,
    )


def _reset_fail2ban(vm) -> None:
    """Unban all IPs and restart fail2ban to clear any accumulated failures."""
    vm.exec("fail2ban-client unban --all 2>/dev/null; systemctl restart fail2ban")
    time.sleep(2)


# ===========================================================================
# Smoke tests — quick checks that services are running
# ===========================================================================


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


# ===========================================================================
# Port knocking
# ===========================================================================


class TestPortKnocking:
    """Tests for port knocking firewall feature."""

    def test_ssh_blocked_without_knock(self, bootstrap_vm):
        """SSH should be unreachable without performing the knock sequence."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            with pytest.raises((ConnectionRefusedError, TimeoutError, OSError)):
                sock.connect((bootstrap_vm.ip_address, bootstrap_vm.ssh_port))

    def test_ssh_accessible_after_knock(self, bootstrap_vm):
        """SSH should be reachable after performing the correct knock sequence."""
        bootstrap_vm.knock()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            try:
                sock.connect((bootstrap_vm.ip_address, bootstrap_vm.ssh_port))
            except (ConnectionRefusedError, TimeoutError, OSError) as exc:
                pytest.fail(f"SSH port not accessible after port knocking: {exc}")

    def test_port_knocking_rules_in_nftables(self, bootstrap_vm):
        """NFTables ruleset should contain port knocking sets and rules."""
        result = bootstrap_vm.exec("nft list ruleset")
        assert result.returncode == 0
        assert "knock4_stage1" in result.stdout
        assert "knock4_passed" in result.stdout


# ===========================================================================
# Firewall behavioral tests
# ===========================================================================


class TestFirewallBehavior:
    """Verify the firewall actually blocks traffic, not just that nftables is running."""

    def test_non_ssh_port_blocked_despite_listening_service(self, bootstrap_vm):
        """Start a listener on port 8080 inside the VM and verify it's unreachable.

        This proves the firewall blocks traffic — a connection failure to a port
        with no service behind it doesn't prove anything.
        """
        with bootstrap_vm.background_service(
            start_cmd="nohup python3 -m http.server 8080 > /dev/null 2>&1 &",
            stop_cmd="pkill -f 'http.server 8080'",
        ):
            # Confirm the service is actually listening inside the VM
            result = bootstrap_vm.exec("ss -tln | grep :8080")
            assert ":8080" in result.stdout, "Listener failed to start inside VM"

            # Try to connect from outside — should be blocked by the firewall
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                with pytest.raises((ConnectionRefusedError, TimeoutError, OSError)):
                    sock.connect((bootstrap_vm.ip_address, 8080))

    def test_only_ssh_reachable_after_knock(self, bootstrap_vm):
        """After knocking, only the SSH port accepts connections."""
        bootstrap_vm.knock()

        # SSH port should be open
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            try:
                sock.connect((bootstrap_vm.ip_address, bootstrap_vm.ssh_port))
            except (ConnectionRefusedError, TimeoutError, OSError) as exc:
                pytest.fail(f"SSH port not reachable after knock: {exc}")

        # Other common ports should all be blocked
        for port in [21, 23, 25, 80, 443, 3306, 5432, 8080, 8443, 9090]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                with pytest.raises((ConnectionRefusedError, TimeoutError, OSError)):
                    sock.connect((bootstrap_vm.ip_address, port))


# ===========================================================================
# Filesystem hardening behavioral tests
# ===========================================================================


class TestFilesystemHardeningBehavior:
    """Verify mount options actually prevent dangerous operations."""

    @pytest.mark.parametrize("mount_point", ["/tmp", "/dev/shm", "/var/tmp"])
    def test_noexec_blocks_execution(self, bootstrap_vm, mount_point):
        """A script on a noexec mount should not be executable."""
        script = f"{mount_point}/test_noexec.sh"
        bootstrap_vm.exec(
            f"echo '#!/bin/sh\necho EXECUTED' > {script} && chmod +x {script}"
        )
        try:
            result = bootstrap_vm.exec(script)
            assert result.returncode != 0, (
                f"Script executed from {mount_point} — noexec is not working"
            )
            assert "EXECUTED" not in result.stdout
        finally:
            bootstrap_vm.exec(f"rm -f {script}")


# ===========================================================================
# SSH hardening behavioral tests
#
# These generate failed auth attempts that fail2ban counts, so we reset
# fail2ban at the end to prevent cascading failures in later tests.
# ===========================================================================


class TestSSHHardeningBehavior:
    """Verify SSH access controls actually reject unauthorized connections.

    These tests generate failed auth attempts that fail2ban (in aggressive
    mode) counts as failures. Two fixtures manage fail2ban state:
      - clean_fail2ban_before_class: resets once before all tests in the class
      - clean_fail2ban_after_test: resets after each individual test
    """

    @pytest.fixture(autouse=True, scope="class")
    def clean_fail2ban_before_class(self, bootstrap_vm):
        """Reset fail2ban once before SSH hardening tests begin."""
        _reset_fail2ban(bootstrap_vm)

    @pytest.fixture(autouse=True)
    def clean_fail2ban_after_test(self, bootstrap_vm):
        """Reset fail2ban after each test to clear accumulated failures."""
        yield
        _reset_fail2ban(bootstrap_vm)

    def test_root_login_rejected(self, bootstrap_vm):
        """PermitRootLogin no — root must not be able to SSH in."""
        bootstrap_vm.knock()
        result = _ssh_attempt(
            bootstrap_vm,
            user="root",
            key_path=bootstrap_vm.private_key_path,
        )
        assert result.returncode != 0, (
            "Root SSH login succeeded — PermitRootLogin is not effective"
        )
        assert "SUCCESS" not in result.stdout

    def test_password_auth_rejected(self, bootstrap_vm):
        """PasswordAuthentication no — server must refuse password auth entirely."""
        bootstrap_vm.knock()
        result = _ssh_attempt(
            bootstrap_vm,
            user="testuser",
            extra_opts=[
                "-o", "PubkeyAuthentication=no",
                "-o", "PreferredAuthentications=password",
            ],
        )
        assert result.returncode != 0, (
            "Password auth was not rejected by the server"
        )
        assert "SUCCESS" not in result.stdout

    def test_unknown_user_rejected(self, bootstrap_vm):
        """AllowGroups — a user not in the allowed group must be rejected."""
        bootstrap_vm.knock()
        result = _ssh_attempt(
            bootstrap_vm,
            user="nobody",
            key_path=bootstrap_vm.private_key_path,
        )
        assert result.returncode != 0, (
            "SSH login as 'nobody' succeeded — AllowGroups is not effective"
        )
        assert "SUCCESS" not in result.stdout

    def test_allowed_user_can_connect(self, bootstrap_vm):
        """An allowed user with the correct key can SSH in."""
        # Verify the key is actually in authorized_keys (diagnostic)
        ak = bootstrap_vm.exec("cat /home/testuser/.ssh/authorized_keys")
        pub = bootstrap_vm.public_key.split()[1]  # just the key data
        assert pub in ak.stdout, (
            f"Test SSH key not found in testuser's authorized_keys.\n"
            f"authorized_keys: {ak.stdout[:200]}\n"
            f"expected key fragment: {pub[:40]}..."
        )

        bootstrap_vm.knock()
        result = _ssh_attempt(
            bootstrap_vm,
            user="testuser",
            key_path=bootstrap_vm.private_key_path,
        )
        assert result.returncode == 0, (
            f"Allowed user 'testuser' cannot SSH in.\n"
            f"stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout


# ===========================================================================
# User and sudo behavioral tests
# ===========================================================================


class TestUsersBehavior:
    """Verify user permissions and sudo configuration actually work."""

    def test_ansible_user_has_passwordless_sudo(self, bootstrap_vm):
        """The deploy (ansible) user should sudo without a password."""
        result = bootstrap_vm.exec("su - ansible -c 'sudo -n whoami'")
        assert result.returncode == 0, (
            f"Ansible user passwordless sudo failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "root" in result.stdout

    def test_manual_user_sudo_requires_password(self, bootstrap_vm):
        """The manual (testuser) user needs a password for sudo."""
        result = bootstrap_vm.exec("su - testuser -c 'sudo -n whoami'")
        assert result.returncode != 0, (
            "Manual user ran sudo without password — should require one"
        )

    def test_manual_user_can_sudo_with_password(self, bootstrap_vm):
        """The manual user can sudo when providing the correct password."""
        # Deploy a helper script to /root (NOT /tmp which has noexec).
        # requiretty is set in sudoers, so we need a PTY via script(1).
        bootstrap_vm.exec(
            "cat > /root/test_sudo.sh << 'HEREDOC'\n"
            "#!/bin/bash\n"
            "echo 'TestPassword123!' | sudo -S whoami 2>&1\n"
            "HEREDOC"
        )
        bootstrap_vm.exec("chmod 0755 /root/test_sudo.sh")
        result = bootstrap_vm.exec(
            "su - testuser -c 'script -qc /root/test_sudo.sh /dev/null'"
        )
        bootstrap_vm.exec("rm -f /root/test_sudo.sh")
        assert "root" in result.stdout, (
            f"Manual user sudo with password failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_su_restricted_to_wheel_group(self, bootstrap_vm):
        """Users not in the wheel group cannot use su."""
        # ansible user is not in wheel — su should be denied
        result = bootstrap_vm.exec(
            "su - ansible -c 'su - testuser -c whoami' 2>&1"
        )
        assert result.returncode != 0, (
            "Non-wheel user used su — pam_wheel restriction not working"
        )


# ===========================================================================
# Logging behavioral tests
# ===========================================================================


class TestLoggingBehavior:
    """Verify journald actually persists log entries."""

    def test_log_entries_persist_in_journal(self, bootstrap_vm):
        """Write a log message and read it back from persistent journal."""
        tag = f"integration-test-{int(time.time())}"
        message = "behavioral-test-log-persistence"

        bootstrap_vm.exec(f"logger -t {tag} '{message}'")
        time.sleep(1)

        result = bootstrap_vm.exec(f"journalctl -t {tag} --no-pager -o cat")
        assert message in result.stdout, (
            f"Log message not found in journal.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ===========================================================================
# Time synchronization behavioral tests
# ===========================================================================


class TestTimeSyncBehavior:
    """Verify chrony actively corrects clock drift."""

    def test_chrony_sources_configured(self, bootstrap_vm):
        """Chrony has NTP sources configured and can reach at least one."""
        result = bootstrap_vm.exec("chronyc -n sources")
        # chronyc may return non-zero if a source is temporarily unreachable
        # ("503 No such source") while still showing valid sources, so we
        # check the output content rather than the return code.
        lines = result.stdout.strip().splitlines()
        source_lines = [line for line in lines if line.startswith("^")]
        assert len(source_lines) > 0, (
            f"No NTP sources configured in chrony.\n"
            f"chronyc sources output:\n{result.stdout}"
        )

    def test_chrony_is_tracking_a_source(self, bootstrap_vm):
        """Chrony should be actively tracking an NTP source."""
        # Chrony needs time after boot to poll sources and select one.
        # Retry for up to 60 seconds before giving up.
        import time

        deadline = time.monotonic() + 60
        while True:
            result = bootstrap_vm.exec("chronyc -n tracking")
            assert result.returncode == 0, (
                f"chronyc tracking failed.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            if "Reference ID    : 00000000" not in result.stdout:
                return
            if time.monotonic() > deadline:
                break
            time.sleep(3)

        pytest.fail("Chrony is not tracking any NTP source after 60s")


# ===========================================================================
# Disabled services — verify they're actually absent
# ===========================================================================


class TestDisabledServices:
    """Verify that services disabled in test config are truly absent."""

    def test_swap_not_active(self, bootstrap_vm):
        """Swap is disabled in test config — no swap should be active."""
        result = bootstrap_vm.exec("swapon --show --noheadings")
        assert result.stdout.strip() == "", (
            f"Swap is active but should be disabled: {result.stdout}"
        )

    def test_tailscale_not_running(self, bootstrap_vm):
        """Tailscale is disabled in test config — service should not be active."""
        result = bootstrap_vm.exec("systemctl is-active tailscaled")
        assert "inactive" in result.stdout or result.returncode != 0

    def test_emergency_script_not_deployed_when_tailscale_disabled(self, bootstrap_vm):
        """Req 9.8: Emergency script is NOT deployed when Tailscale is disabled."""
        result = bootstrap_vm.exec(
            "test ! -f /root/emergency-ssh-access.sh && echo ABSENT"
        )
        assert "ABSENT" in result.stdout


# ===========================================================================
# Ansible verification playbook
# ===========================================================================


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


# ===========================================================================
# Playbook idempotency
# ===========================================================================


class TestPlaybookIdempotency:
    """Tests for playbook idempotency (Requirement 15.3)."""

    def test_second_run_reports_no_failures(self, bootstrap_vm):
        """Req 15.3, 15.4: Second playbook run completes without errors."""
        bootstrap_vm.knock()
        result = run_bootstrap_playbook(bootstrap_vm, user="ansible")
        assert result.returncode == 0, (
            f"Second playbook run failed.\nstdout: {result.stdout[-2000:]}"
        )
        assert "failed=0" in result.stdout
        assert "unreachable=0" in result.stdout

    def test_check_mode_reports_no_changes(self, bootstrap_vm):
        """Req 15.4, 15.5: Check mode reports no changes on configured system."""
        bootstrap_vm.knock()
        result = run_bootstrap_playbook(
            bootstrap_vm, check_mode=True, user="ansible",
        )
        assert result.returncode == 0, (
            f"Check mode failed.\nstdout: {result.stdout[-2000:]}"
        )
        if "changed=0" not in result.stdout:
            # Find which tasks reported changed for a useful error message
            import re
            lines = result.stdout.split("\n")
            changed_tasks = []
            last_task = ""
            for line in lines:
                task_match = re.match(r"TASK \[(.+)\]", line)
                if task_match:
                    last_task = task_match.group(1)
                if line.startswith("changed:"):
                    changed_tasks.append(last_task)
            msg = "Check mode reported changes. Tasks that changed:\n"
            for task in changed_tasks:
                msg += f"  - {task}\n"
            msg += f"\nPLAY RECAP: {lines[-2] if len(lines) >= 2 else 'N/A'}"
            pytest.fail(msg)


# ===========================================================================
# Swap behavioral tests — uses a separate VM with zram + disk swap enabled.
# ===========================================================================


class TestSwapBehavior:
    """Verify swap configuration when zram and disk swap are enabled.

    Uses the swap_vm fixture which bootstraps with:
      zram_enabled=True, zram_size=50%, disk_swap_size=512M
    """

    def test_zram_device_exists(self, swap_vm):
        """Req 13.4: Zram device is created."""
        result = swap_vm.exec("test -b /dev/zram0 && echo EXISTS")
        assert "EXISTS" in result.stdout, "Zram device /dev/zram0 not found"

    def test_zram_active_as_swap(self, swap_vm):
        """Req 13.7: Zram device is active as swap space."""
        result = swap_vm.exec("swapon --show --noheadings")
        assert "/dev/zram0" in result.stdout, (
            f"Zram not active as swap.\nswapon output: {result.stdout}"
        )

    def test_zram_compression_is_lz4(self, swap_vm):
        """Req 13.5: Zram uses lz4 compression."""
        result = swap_vm.exec("cat /sys/block/zram0/comp_algorithm")
        assert "lz4" in result.stdout, (
            f"Expected lz4 compression, got: {result.stdout.strip()}"
        )

    def test_disk_swap_file_exists(self, swap_vm):
        """Req 13.11: Swap file exists at /swapfile."""
        result = swap_vm.exec("test -f /swapfile && echo EXISTS")
        assert "EXISTS" in result.stdout, "/swapfile not found"

    def test_disk_swap_file_permissions(self, swap_vm):
        """Req 13.12: Swap file has 0600 permissions."""
        result = swap_vm.exec("stat -c '%a' /swapfile")
        assert result.stdout.strip() == "600", (
            f"Expected 0600 permissions, got: {result.stdout.strip()}"
        )

    def test_disk_swap_active(self, swap_vm):
        """Req 13.14: Disk swap file is active as swap space."""
        result = swap_vm.exec("swapon --show --noheadings")
        assert "/swapfile" in result.stdout, (
            f"/swapfile not active as swap.\nswapon output: {result.stdout}"
        )

    def test_disk_swap_in_fstab(self, swap_vm):
        """Req 13.15: Swap file is in /etc/fstab for persistence."""
        result = swap_vm.exec("grep '/swapfile' /etc/fstab")
        assert result.returncode == 0, "/swapfile not found in /etc/fstab"
        assert "swap" in result.stdout

    def test_zram_priority_higher_than_disk(self, swap_vm):
        """Req 13.9, 13.16: Zram has higher swap priority than disk swap."""
        result = swap_vm.exec("swapon --show=NAME,PRIO --noheadings")
        lines = result.stdout.strip().splitlines()
        priorities = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                priorities[parts[0]] = int(parts[1])
        assert "/dev/zram0" in priorities, (
            f"Zram not in swapon output: {result.stdout}"
        )
        assert "/swapfile" in priorities, (
            f"/swapfile not in swapon output: {result.stdout}"
        )
        assert priorities["/dev/zram0"] > priorities["/swapfile"], (
            f"Zram priority ({priorities['/dev/zram0']}) should be higher "
            f"than disk swap priority ({priorities['/swapfile']})"
        )


# ===========================================================================
# Fail2ban behavioral tests — placed last because banning our IP is
# destructive; tests use try/finally to always unban afterwards.
# ===========================================================================


class TestFail2banBehavior:
    """Verify fail2ban actually bans IPs after failed SSH attempts."""

    def _get_host_ip(self, vm) -> str:
        """Derive the test host's IP from the VM's IP (gateway is .1)."""
        parts = vm.ip_address.rsplit(".", 1)
        return f"{parts[0]}.1"

    def test_bans_ip_after_failed_ssh_attempts(self, bootstrap_vm, tmp_path):
        """Exceed maxretry (5) failed auth attempts and verify the IP is banned."""
        # Ensure fail2ban is clean before we start
        _reset_fail2ban(bootstrap_vm)

        # Generate a wrong SSH key — we need a real key so sshd logs an
        # actual auth failure (not just a closed connection)
        wrong_key = tmp_path / "wrong_key"
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(wrong_key),
             "-N", "", "-q"],
            check=True,
        )

        try:
            # Make 8 failed SSH attempts (maxretry=5, extra margin).
            # We avoid BatchMode=yes here because it causes the client to
            # disconnect before sshd logs a "Failed publickey" entry —
            # sshd only logs "Connection closed" which fail2ban doesn't match.
            for _i in range(8):
                bootstrap_vm.knock()
                time.sleep(1)
                cmd = [
                    "ssh",
                    "-p", str(bootstrap_vm.ssh_port),
                    "-i", str(wrong_key),
                    "-o", "PubkeyAuthentication=yes",
                    "-o", "PasswordAuthentication=no",
                    "-o", "KbdInteractiveAuthentication=no",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "IdentitiesOnly=yes",
                    "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    f"testuser@{bootstrap_vm.ip_address}",
                    "echo FAIL",
                ]
                with contextlib.suppress(subprocess.TimeoutExpired):
                    subprocess.run(
                        cmd, capture_output=True, text=True,
                        timeout=15, check=False,
                    )
                time.sleep(1)

            # Give fail2ban time to process the journal entries
            time.sleep(10)

            # Debug: check what sshd logged
            journal = bootstrap_vm.exec(
                "journalctl -u ssh.service --no-pager --since '-2min' "
                "| grep -i -E 'fail|invalid|refused|closed|error' "
                "| tail -20"
            )

            # Check that fail2ban has banned an IP
            status = bootstrap_vm.exec("fail2ban-client status sshd")
            assert status.returncode == 0, (
                f"fail2ban-client failed.\n"
                f"stdout: {status.stdout}\nstderr: {status.stderr}"
            )

            # Verify an IP was banned
            assert "Currently banned:\t0" not in status.stdout, (
                f"No IPs banned after failed attempts.\n"
                f"fail2ban status:\n{status.stdout}\n"
                f"sshd journal:\n{journal.stdout}"
            )

            # Verify SSH is now blocked even after knocking
            bootstrap_vm.knock()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                with pytest.raises(
                    (ConnectionRefusedError, TimeoutError, OSError),
                ):
                    sock.connect(
                        (bootstrap_vm.ip_address, bootstrap_vm.ssh_port)
                    )
        finally:
            # Always unban to avoid breaking anything after the test suite
            bootstrap_vm.exec("fail2ban-client unban --all")
            _reset_fail2ban(bootstrap_vm)
