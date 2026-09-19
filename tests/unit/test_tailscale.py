"""
Unit tests for the tailscale role.

Tests Tailscale installation task structure when enabled, skip behavior when
disabled (via when: conditions), and connectivity verification logic.

Approach: parse YAML task files and verify task parameters and conditions.

Each test cites the requirement it checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


def load_tasks(role_name: str, task_file: str = "main.yml") -> list[dict[str, Any]]:
    """Load and parse an Ansible task file."""
    task_path = ROLES_DIR / role_name / "tasks" / task_file
    with open(task_path) as f:
        return yaml.safe_load(f)


def find_task(tasks: list[dict[str, Any]], name_fragment: str) -> dict[str, Any] | None:
    """Find a task by partial name match (case-insensitive)."""
    for task in tasks:
        if name_fragment.lower() in task.get("name", "").lower():
            return task
    return None


class TestTailscaleInstallation:
    """Tests for Tailscale installation task structure."""

    def test_install_tasks_included_when_enabled(self):
        """TS-2: install.yml is included only when tailscale_enabled is true."""
        tasks = load_tasks("tailscale")
        task = find_task(tasks, "include tailscale installation")
        assert task is not None, "Could not find Tailscale installation include task"
        when_condition = task.get("when", "")
        assert "tailscale_enabled" in str(when_condition)

    def test_verify_tasks_included_when_enabled(self):
        """TS-2: verify.yml is included only when tailscale_enabled is true."""
        tasks = load_tasks("tailscale")
        task = find_task(tasks, "include tailscale connectivity verification")
        assert task is not None, "Could not find Tailscale verification include task"
        when_condition = task.get("when", "")
        assert "tailscale_enabled" in str(when_condition)

    def test_gpg_key_task_exists(self):
        """TS-4: A task to add the Tailscale signing key must exist."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "add tailscale gpg key")
        assert task is not None, "Could not find GPG key task"

    def test_gpg_key_uses_official_url(self):
        """TS-4: Signing key is fetched from the official Tailscale URL."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "add tailscale gpg key")
        assert task is not None
        get_url_params = task["ansible.builtin.get_url"]
        url = get_url_params.get("url", "")
        assert "tailscale" in url.lower() or "tailscale_repo_key_url" in url

    def test_repository_task_exists(self):
        """TS-3: A task to add the Tailscale apt repository must exist."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "add tailscale repository")
        assert task is not None, "Could not find repository task"

    def test_install_package_task_exists(self):
        """TS-3: A task to install the tailscale package must exist."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "install tailscale package")
        assert task is not None, "Could not find package install task"
        apt_params = task["ansible.builtin.apt"]
        assert apt_params.get("name") == "tailscale"
        assert apt_params.get("state") == "present"

    def test_authenticate_task_uses_login_server(self):
        """TS-6: Registration task uses --login-server with the control server URL."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "authenticate tailscale")
        assert task is not None, "Could not find Tailscale authentication task"
        cmd_params = task["ansible.builtin.command"]
        cmd = cmd_params.get("cmd", "")
        assert "--login-server" in cmd
        assert "tailscale_control_server" in cmd

    def test_authenticate_task_uses_authkey(self):
        """TS-7: Registration task passes the pre-auth key to the client."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "authenticate tailscale")
        assert task is not None
        cmd_params = task["ansible.builtin.command"]
        cmd = cmd_params.get("cmd", "")
        assert "--authkey" in cmd
        assert "tailscale_pre_auth_key" in cmd

    def test_service_enabled_task_exists(self):
        """TS-12: A task to enable the tailscaled service must exist."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "enable tailscale service")
        assert task is not None, "Could not find service enable task"
        systemd_params = task["ansible.builtin.systemd"]
        assert systemd_params.get("name") == "tailscaled"
        assert systemd_params.get("enabled") is True

    def test_service_started_task_exists(self):
        """TS-13: A task to start the tailscaled service must exist."""
        tasks = load_tasks("tailscale", "install.yml")
        task = find_task(tasks, "start tailscale service")
        assert task is not None, "Could not find service start task"
        systemd_params = task["ansible.builtin.systemd"]
        assert systemd_params.get("name") == "tailscaled"
        assert systemd_params.get("state") == "started"


class TestTailscaleSkipWhenDisabled:
    """Tests for skip behavior when Tailscale is disabled."""

    def test_main_tasks_use_when_condition(self):
        """TS-2: All main tasks have a when: tailscale_enabled condition."""
        tasks = load_tasks("tailscale")
        for task in tasks:
            when_condition = task.get("when", "")
            assert "tailscale_enabled" in str(when_condition), (
                f"Task '{task.get('name')}' missing tailscale_enabled when condition"
            )

    def test_only_two_include_tasks_in_main(self):
        """TS-2: main.yml contains exactly two include_tasks (install + verify)."""
        tasks = load_tasks("tailscale")
        include_tasks = [t for t in tasks if "ansible.builtin.include_tasks" in t]
        assert len(include_tasks) == 2, (
            f"Expected 2 include_tasks in main.yml, found {len(include_tasks)}"
        )


class TestTailscaleConnectivityVerification:
    """Tests for connectivity verification logic."""

    def test_interface_wait_task_exists(self):
        """TS-15: A task to wait for the Tailscale interface must exist."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "wait for tailscale interface")
        assert task is not None, "Could not find interface wait task"

    def test_interface_wait_uses_tailscale_interface_var(self):
        """TS-14, TS-15: Interface wait task uses the tailscale_interface variable."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "wait for tailscale interface")
        assert task is not None
        wait_params = task["ansible.builtin.wait_for"]
        path = wait_params.get("path", "")
        assert "tailscale_interface" in path

    def test_fail_if_interface_missing(self):
        """TS-15: A fail task exists when the interface does not appear."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "fail if tailscale interface does not exist")
        assert task is not None, "Could not find interface-missing fail task"
        fail_params = task["ansible.builtin.fail"]
        assert "tailscale" in fail_params.get("msg", "").lower()

    def test_get_tailscale_status_task_exists(self):
        """TS-16: A task to get Tailscale status JSON must exist."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "wait for tailscale to reach running state")
        assert task is not None, "Could not find status task"
        cmd_params = task["ansible.builtin.command"]
        cmd = cmd_params.get("cmd", "")
        assert "tailscale status" in cmd

    def test_fail_if_not_connected(self):
        """TS-16: The status task retries until Tailscale reaches Running state."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "wait for tailscale to reach running state")
        assert task is not None, "Could not find status task"
        assert task.get("retries", 0) > 0, "Status task should have retries"

    def test_get_tailscale_ip_task_exists(self):
        """TS-17: A task to retrieve the Tailscale IPv4 address must exist."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "get tailscale ipv4 address")
        assert task is not None, "Could not find IP address task"
        cmd_params = task["ansible.builtin.command"]
        cmd = cmd_params.get("cmd", "")
        assert "tailscale ip" in cmd

    def test_set_tailscale_ip_fact(self):
        """TS-17: A task to set the tailscale_ipv4 fact must exist."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "set tailscale ip facts")
        assert task is not None, "Could not find set_fact task for tailscale_ipv4"
        set_fact_params = task["ansible.builtin.set_fact"]
        assert "tailscale_ipv4" in set_fact_params

    def test_connectivity_ping_test_exists(self):
        """TS-21: A ping connectivity test through the Tailscale interface must exist."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "test connectivity through tailscale interface")
        assert task is not None, "Could not find connectivity ping task"
        cmd_params = task["ansible.builtin.command"]
        cmd = cmd_params.get("cmd", "")
        assert "ping" in cmd
        assert "tailscale_interface" in cmd

    def test_fail_if_connectivity_test_fails(self):
        """TS-21: A fail task exists when the connectivity ping test fails."""
        tasks = load_tasks("tailscale", "verify.yml")
        task = find_task(tasks, "fail if tailscale connectivity test fails")
        assert task is not None, "Could not find connectivity-fail task"
        fail_params = task["ansible.builtin.fail"]
        assert "tailscale" in fail_params.get("msg", "").lower()
