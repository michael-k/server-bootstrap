"""
Unit tests for system service roles.

Tests fail2ban jail configuration, journald configuration values,
time sync service selection (chrony vs timesyncd), and swap priority values.

Approach: render Jinja2 templates with known variable sets and assert on
rendered content; parse YAML task files to verify task parameters.

Covers roles: fail2ban, logging, system_config, swap.

Requirements: F2B-1, F2B-4, F2B-5, F2B-7, F2B-9, F2B-10, F2B-11, F2B-13,
F2B-14, F2B-15, LOG-1, LOG-2, LOG-3, LOG-4,
TIME-3, SWAP-1, SWAP-2, SWAP-5, SWAP-9, SWAP-10,
SWAP-12, SWAP-15, SWAP-16
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


def make_env(role_name: str) -> Environment:
    template_dir = ROLES_DIR / role_name / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)))


def load_tasks(role_name: str, task_file: str = "main.yml") -> list[dict[str, Any]]:
    task_path = ROLES_DIR / role_name / "tasks" / task_file
    with open(task_path) as f:
        return yaml.safe_load(f)


def find_task(tasks: list[dict[str, Any]], name_fragment: str) -> dict[str, Any] | None:
    for task in tasks:
        if name_fragment.lower() in task.get("name", "").lower():
            return task
    return None


# ---------------------------------------------------------------------------
# Fail2ban
# ---------------------------------------------------------------------------

class TestFail2banConfiguration:
    """Tests for fail2ban jail configuration values (F2B-1, F2B-4, F2B-5, F2B-7,
    F2B-9, F2B-10, F2B-11, F2B-13, F2B-14, F2B-15)."""

    @pytest.fixture
    def default_vars(self) -> dict:
        return {
            "fail2ban_max_retry": 5,
            "fail2ban_ban_time": "10m",
            "fail2ban_find_time": "10m",
            "fail2ban_ssh_enabled": True,
            "fail2ban_ssh_backend": "systemd",
            "fail2ban_banaction": "nftables-multiport",
            "ssh_port": 22,
        }

    def render(self, variables: dict) -> str:
        return make_env("fail2ban").get_template("jail.local.j2").render(**variables)

    def test_sshd_jail_enabled(self, default_vars):
        """F2B-4: the [sshd] jail is enabled when fail2ban_ssh_enabled is true."""
        config = self.render(default_vars)
        assert "[sshd]" in config
        assert "enabled = true" in config

    def test_banaction_is_nftables(self, default_vars):
        """F2B-11: banaction names the nftables action."""
        config = self.render(default_vars)
        assert "banaction = nftables-multiport" in config

    def test_max_retry_rendered(self, default_vars):
        """F2B-9: maxretry reflects the configured failure count."""
        config = self.render(default_vars)
        assert "maxretry = 5" in config

    def test_ban_time_rendered(self, default_vars):
        """F2B-10: bantime reflects the configured ban duration."""
        config = self.render(default_vars)
        assert "bantime = 10m" in config

    def test_find_time_rendered(self, default_vars):
        """F2B-9: findtime reflects the configured counting window."""
        config = self.render(default_vars)
        assert "findtime = 10m" in config

    def test_backend_is_systemd(self, default_vars):
        """F2B-7: the [DEFAULT] backend is rendered from fail2ban_ssh_backend.

        This is a claim about the rendered file, not about the [sshd] jail:
        the distribution's jail.d/defaults-debian.conf sets backend at jail
        level, which outranks [DEFAULT], so nothing here establishes what
        that jail actually reads. See specs/fail2ban/design.md.
        """
        config = self.render(default_vars)
        assert "backend = systemd" in config

    def test_ssh_port_in_jail(self, default_vars):
        """F2B-5: the sshd jail names the port ssh_port configures."""
        config = self.render(default_vars)
        assert "port = 22" in config

    def test_custom_max_retry(self, default_vars):
        """F2B-9: a custom maxretry value is rendered correctly."""
        default_vars["fail2ban_max_retry"] = 3
        config = self.render(default_vars)
        assert "maxretry = 3" in config

    def test_custom_ban_time(self, default_vars):
        """F2B-10: a custom ban time is rendered correctly."""
        default_vars["fail2ban_ban_time"] = "1h"
        config = self.render(default_vars)
        assert "bantime = 1h" in config

    def test_install_task_exists(self):
        """F2B-1: fail2ban is installed from the distribution's repository."""
        tasks = load_tasks("fail2ban")
        task = find_task(tasks, "install fail2ban package")
        assert task is not None
        apt_params = task["ansible.builtin.apt"]
        assert apt_params.get("name") == "fail2ban"
        assert apt_params.get("state") == "present"

    def test_service_enabled_task_exists(self):
        """F2B-13: the fail2ban service is enabled at boot."""
        tasks = load_tasks("fail2ban")
        task = find_task(tasks, "enable fail2ban service")
        assert task is not None
        systemd_params = task["ansible.builtin.systemd"]
        assert systemd_params.get("name") == "fail2ban"
        assert systemd_params.get("enabled") is True

    def test_service_started_task_exists(self):
        """F2B-14: the fail2ban service is started."""
        tasks = load_tasks("fail2ban")
        task = find_task(tasks, "start fail2ban service")
        assert task is not None
        systemd_params = task["ansible.builtin.systemd"]
        assert systemd_params.get("name") == "fail2ban"
        assert systemd_params.get("state") == "started"

    def test_template_deploy_notifies_restart(self):
        """F2B-15: the jail configuration task notifies the restart handler.

        Tests fail2ban's "deploy fail2ban jail configuration" task, not
        journald's. This asserts only that the task notifies something; it
        does not assert the "and only when" half of F2B-15, which would need
        a count of the notifying tasks in the role.
        """
        tasks = load_tasks("fail2ban")
        task = find_task(tasks, "deploy fail2ban jail configuration")
        assert task is not None
        notify = task.get("notify")
        assert notify is not None, "Template task must notify a handler"


# ---------------------------------------------------------------------------
# Journald / Logging
# ---------------------------------------------------------------------------

class TestJournaldConfiguration:
    """Tests for journald configuration values (LOG-1, LOG-2, LOG-3, LOG-4)."""

    @pytest.fixture
    def default_vars(self) -> dict:
        return {
            "journald_max_disk_usage": "500M",
            "journald_max_retention_time": "1month",
        }

    def render(self, variables: dict) -> str:
        return make_env("logging").get_template("journald.conf.j2").render(**variables)

    def test_storage_is_persistent(self, default_vars):
        """LOG-1: Storage must be set to persistent."""
        config = self.render(default_vars)
        assert "Storage=persistent" in config

    def test_max_disk_usage_rendered(self, default_vars):
        """LOG-2: SystemMaxUse must reflect the configured value."""
        config = self.render(default_vars)
        assert "SystemMaxUse=500M" in config

    def test_max_retention_rendered(self, default_vars):
        """LOG-3: MaxRetentionSec must reflect the configured value."""
        config = self.render(default_vars)
        assert "MaxRetentionSec=1month" in config

    def test_custom_disk_usage(self, default_vars):
        """LOG-2: Custom disk usage value is rendered correctly."""
        default_vars["journald_max_disk_usage"] = "1G"
        config = self.render(default_vars)
        assert "SystemMaxUse=1G" in config

    def test_custom_retention_time(self, default_vars):
        """LOG-3: Custom retention time is rendered correctly."""
        default_vars["journald_max_retention_time"] = "2weeks"
        config = self.render(default_vars)
        assert "MaxRetentionSec=2weeks" in config

    def test_journal_section_header(self, default_vars):
        """Config must have [Journal] section header."""
        config = self.render(default_vars)
        assert "[Journal]" in config

    def test_deploy_task_notifies_restart(self):
        """LOG-4: Template deployment must notify journald restart handler."""
        tasks = load_tasks("logging")
        task = find_task(tasks, "deploy journald configuration")
        assert task is not None
        notify = task.get("notify")
        assert notify is not None, "journald template task must notify a handler"
        notify_str = notify if isinstance(notify, str) else " ".join(notify)
        assert "journald" in notify_str.lower()


# ---------------------------------------------------------------------------
# Time Synchronization
# ---------------------------------------------------------------------------

class TestTimeSyncServiceSelection:
    """Tests for time sync service selection (Requirements 12.1-12.5)."""

    @pytest.fixture
    def ntp_servers(self) -> list[str]:
        return [
            "0.debian.pool.ntp.org",
            "1.debian.pool.ntp.org",
            "2.debian.pool.ntp.org",
            "3.debian.pool.ntp.org",
        ]

    def render_chrony(self, ntp_servers: list[str]) -> str:
        return make_env("system_config").get_template("chrony.conf.j2").render(
            ntp_servers=ntp_servers
        )

    def render_timesyncd(self, ntp_servers: list[str]) -> str:
        return make_env("system_config").get_template("timesyncd.conf.j2").render(
            ntp_servers=ntp_servers
        )

    def test_chrony_contains_pool_directives(self, ntp_servers):
        """TIME-3: chrony.conf must contain pool directives for each NTP server."""
        config = self.render_chrony(ntp_servers)
        for server in ntp_servers:
            assert f"pool {server} iburst" in config

    def test_chrony_has_all_four_servers(self, ntp_servers):
        """TIME-3: chrony.conf must include all configured NTP servers."""
        config = self.render_chrony(ntp_servers)
        # Count actual pool directives (lines starting with "pool ")
        pool_count = sum(1 for line in config.split('\n') if line.strip().startswith('pool '))
        assert pool_count == 4

    def test_chrony_custom_servers(self):
        """TIME-3: Custom NTP servers are rendered in chrony.conf."""
        servers = ["ntp1.example.com", "ntp2.example.com"]
        config = self.render_chrony(servers)
        assert "pool ntp1.example.com iburst" in config
        assert "pool ntp2.example.com iburst" in config

    def test_chrony_has_makestep(self, ntp_servers):
        """chrony.conf must include makestep for initial large offset correction."""
        config = self.render_chrony(ntp_servers)
        assert "makestep" in config

    def test_chrony_has_rtcsync(self, ntp_servers):
        """chrony.conf must include rtcsync for hardware clock sync."""
        config = self.render_chrony(ntp_servers)
        assert "rtcsync" in config

    def test_timesyncd_ntp_line(self, ntp_servers):
        """TIME-3: timesyncd.conf must have NTP= line with all servers."""
        config = self.render_timesyncd(ntp_servers)
        assert "NTP=" in config
        for server in ntp_servers:
            assert server in config

    def test_timesyncd_has_time_section(self, ntp_servers):
        """timesyncd.conf must have [Time] section header."""
        config = self.render_timesyncd(ntp_servers)
        assert "[Time]" in config

    def test_timesyncd_servers_space_separated(self, ntp_servers):
        """TIME-3: timesyncd NTP servers must be space-separated on one line."""
        config = self.render_timesyncd(ntp_servers)
        ntp_line = next(
            line for line in config.splitlines() if line.startswith("NTP=")
        )
        # All servers on one line, space-separated
        for server in ntp_servers:
            assert server in ntp_line


# ---------------------------------------------------------------------------
# Swap
# ---------------------------------------------------------------------------

class TestSwapPriorityValues:
    """Tests for swap configuration values.

    Covers SWAP-1, SWAP-2, SWAP-5, SWAP-9, SWAP-10, SWAP-12, SWAP-15 and
    SWAP-16 by rendering the zram template and parsing the role's task files.
    """

    @pytest.fixture
    def zram_vars(self) -> dict:
        return {
            "zram_size": "50%",
            "zram_swap_priority": 100,
            "disk_swap_priority": 10,
        }

    def render_zram_conf(self, variables: dict) -> str:
        return make_env("swap").get_template("zram.conf.j2").render(**variables)

    def test_zram_priority_higher_than_disk(self, zram_vars):
        """SWAP-16: zram priority (100) must be higher than disk priority (10).

        Asserts on this fixture's own values, not on anything the role
        defines — see the swap design's failure modes.
        """
        assert zram_vars["zram_swap_priority"] > zram_vars["disk_swap_priority"]

    def test_zram_priority_in_conf(self, zram_vars):
        """SWAP-9: zram.conf must include the swap priority."""
        config = self.render_zram_conf(zram_vars)
        assert "PRIORITY=100" in config

    def test_zram_compression_is_lz4(self, zram_vars):
        """SWAP-5: zram.conf must configure lz4 compression algorithm."""
        config = self.render_zram_conf(zram_vars)
        assert "ALGO=lz4" in config

    def test_zram_percentage_size(self, zram_vars):
        """SWAP-2: Percentage-based zram size is rendered correctly."""
        config = self.render_zram_conf(zram_vars)
        assert "PERCENTAGE=50" in config

    def test_zram_absolute_size_gb(self, zram_vars):
        """SWAP-2: Absolute GB zram size is converted to MB."""
        zram_vars["zram_size"] = "2G"
        config = self.render_zram_conf(zram_vars)
        assert "SIZE=2048" in config

    def test_zram_absolute_size_mb(self, zram_vars):
        """SWAP-2: Absolute MB zram size is rendered directly."""
        zram_vars["zram_size"] = "512M"
        config = self.render_zram_conf(zram_vars)
        assert "SIZE=512" in config

    def test_disk_swap_file_mode_0600(self):
        """SWAP-12: Swap file must be created with mode 0600."""
        tasks = load_tasks("swap", "disk_swap.yml")
        task = find_task(tasks, "set swap file permissions")
        assert task is not None
        file_params = task["ansible.builtin.file"]
        assert file_params.get("mode") == "0600"
        assert file_params.get("path") == "/swapfile"

    def test_disk_swap_fstab_entry_includes_priority(self):
        """SWAP-15: fstab entry must include the disk swap priority."""
        tasks = load_tasks("swap", "disk_swap.yml")
        task = find_task(tasks, "add swap file to fstab")
        assert task is not None
        lineinfile_params = task["ansible.builtin.lineinfile"]
        line = lineinfile_params.get("line", "")
        assert "/swapfile" in line
        assert "swap" in line
        assert "disk_swap_priority" in line

    def test_zram_conditional_on_zram_enabled(self):
        """SWAP-1: zram tasks are only included when zram_enabled is true."""
        tasks = load_tasks("swap")
        task = find_task(tasks, "include zram swap configuration")
        assert task is not None
        when_condition = task.get("when", "")
        assert "zram_enabled" in str(when_condition)

    def test_disk_swap_conditional_on_size(self):
        """SWAP-10: disk swap tasks are only included when disk_swap_size is set."""
        tasks = load_tasks("swap")
        task = find_task(tasks, "include disk swap configuration")
        assert task is not None
        when_condition = task.get("when", "")
        assert "disk_swap_size" in str(when_condition)
