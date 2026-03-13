"""
Unit tests for the users role.

Tests specific user creation behavior, SSH key deployment,
sudo configuration file content, and authorized_keys permissions.

Requirements: 1.1-1.8, 2.1-2.8
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


class TestManualUserCreation:
    """Tests for manual access user creation."""

    def test_manual_user_uid_is_1000(self):
        """Test that the manual user task specifies uid 1000 via variable."""
        tasks = load_tasks("users")
        task = find_task(tasks, "create manual access user")
        assert task is not None, "Could not find manual user creation task"
        user_params = task["ansible.builtin.user"]
        uid_value = user_params["uid"]
        # Accept either the literal 1000 or the variable reference
        assert uid_value == 1000 or uid_value == "{{ manual_user_uid }}", (
            f"Expected uid 1000 or '{{{{ manual_user_uid }}}}', got {uid_value!r}"
        )

    def test_manual_user_password_uses_sha512(self):
        """Test that the manual user password uses password_hash('sha512')."""
        tasks = load_tasks("users")
        task = find_task(tasks, "create manual access user")
        assert task is not None, "Could not find manual user creation task"
        user_params = task["ansible.builtin.user"]
        password_value = user_params["password"]
        assert "password_hash('sha512')" in password_value, (
            f"Expected password_hash('sha512') in password filter, got {password_value!r}"
        )

    def test_manual_user_update_password_on_create(self):
        """Test that the manual user task sets update_password to on_create."""
        tasks = load_tasks("users")
        task = find_task(tasks, "create manual access user")
        assert task is not None, "Could not find manual user creation task"
        user_params = task["ansible.builtin.user"]
        assert user_params.get("update_password") == "on_create", (
            f"Expected update_password: on_create, got {user_params.get('update_password')!r}"
        )

    def test_manual_user_creates_home_directory(self):
        """Test that the manual user task sets create_home to true."""
        tasks = load_tasks("users")
        task = find_task(tasks, "create manual access user")
        assert task is not None, "Could not find manual user creation task"
        user_params = task["ansible.builtin.user"]
        assert user_params.get("create_home") is True, (
            f"Expected create_home: true, got {user_params.get('create_home')!r}"
        )

    def test_manual_user_ssh_dir_mode_0700(self):
        """Test that the .ssh directory task for manual user sets mode 0700."""
        tasks = load_tasks("users")
        task = find_task(tasks, "ensure .ssh directory exists for manual user")
        assert task is not None, "Could not find manual user .ssh directory task"
        file_params = task["ansible.builtin.file"]
        assert file_params.get("mode") == "0700", (
            f"Expected mode 0700 for .ssh directory, got {file_params.get('mode')!r}"
        )


class TestAnsibleUserCreation:
    """Tests for Ansible automation user creation."""

    def test_deploy_user_uid_is_1999(self):
        """Test that the Ansible user task specifies uid 1999 via variable."""
        tasks = load_tasks("users")
        task = find_task(tasks, "create ansible user")
        assert task is not None, "Could not find Ansible user creation task"
        user_params = task["ansible.builtin.user"]
        uid_value = user_params["uid"]
        assert uid_value == 1999 or uid_value == "{{ deploy_user_uid }}", (
            f"Expected uid 1999 or '{{{{ deploy_user_uid }}}}', got {uid_value!r}"
        )

    def test_ansible_user_password_is_locked(self):
        """Test that the Ansible user password is set to '!' (locked/disabled)."""
        tasks = load_tasks("users")
        task = find_task(tasks, "create ansible user")
        assert task is not None, "Could not find Ansible user creation task"
        user_params = task["ansible.builtin.user"]
        assert user_params.get("password") == "!", (
            f"Expected password '!', got {user_params.get('password')!r}"
        )

    def test_ansible_user_ssh_dir_mode_0700(self):
        """Test that the .ssh directory task for Ansible user sets mode 0700."""
        tasks = load_tasks("users")
        task = find_task(tasks, "ensure .ssh directory exists for ansible user")
        assert task is not None, "Could not find Ansible user .ssh directory task"
        file_params = task["ansible.builtin.file"]
        assert file_params.get("mode") == "0700", (
            f"Expected mode 0700 for .ssh directory, got {file_params.get('mode')!r}"
        )


class TestSSHKeyDeployment:
    """Tests for SSH key deployment to authorized_keys."""

    def test_manual_user_authorized_key_state_present(self):
        """Test that the manual user authorized_key task uses state: present."""
        tasks = load_tasks("users")
        task = find_task(tasks, "deploy ssh public key to manual user")
        assert task is not None, "Could not find manual user authorized_key task"
        ak_params = task["ansible.posix.authorized_key"]
        assert ak_params.get("state") == "present", (
            f"Expected state: present, got {ak_params.get('state')!r}"
        )

    def test_manual_user_authorized_key_not_exclusive(self):
        """Test that the manual user authorized_key task uses exclusive: false."""
        tasks = load_tasks("users")
        task = find_task(tasks, "deploy ssh public key to manual user")
        assert task is not None, "Could not find manual user authorized_key task"
        ak_params = task["ansible.posix.authorized_key"]
        assert ak_params.get("exclusive") is False, (
            f"Expected exclusive: false, got {ak_params.get('exclusive')!r}"
        )

    def test_ansible_user_authorized_key_state_present(self):
        """Test that the Ansible user authorized_key task uses state: present."""
        tasks = load_tasks("users")
        task = find_task(tasks, "deploy ssh public key to ansible user")
        assert task is not None, "Could not find Ansible user authorized_key task"
        ak_params = task["ansible.posix.authorized_key"]
        assert ak_params.get("state") == "present", (
            f"Expected state: present, got {ak_params.get('state')!r}"
        )

    def test_ansible_user_authorized_key_not_exclusive(self):
        """Test that the Ansible user authorized_key task uses exclusive: false."""
        tasks = load_tasks("users")
        task = find_task(tasks, "deploy ssh public key to ansible user")
        assert task is not None, "Could not find Ansible user authorized_key task"
        ak_params = task["ansible.posix.authorized_key"]
        assert ak_params.get("exclusive") is False, (
            f"Expected exclusive: false, got {ak_params.get('exclusive')!r}"
        )

    def test_manual_user_authorized_keys_mode_uses_variable(self):
        """Test that the authorized_keys permission task uses the authorized_keys_mode variable."""
        tasks = load_tasks("users")
        task = find_task(tasks, "set correct permissions on manual user authorized_keys")
        assert task is not None, "Could not find manual user authorized_keys permission task"
        file_params = task["ansible.builtin.file"]
        assert file_params.get("mode") == "{{ authorized_keys_mode }}", (
            f"Expected mode '{{{{ authorized_keys_mode }}}}', got {file_params.get('mode')!r}"
        )

    def test_ansible_user_authorized_keys_mode_uses_variable(self):
        """Test that the Ansible user authorized_keys permission task uses the variable."""
        tasks = load_tasks("users")
        task = find_task(tasks, "set correct permissions on ansible user authorized_keys")
        assert task is not None, "Could not find Ansible user authorized_keys permission task"
        file_params = task["ansible.builtin.file"]
        assert file_params.get("mode") == "{{ authorized_keys_mode }}", (
            f"Expected mode '{{{{ authorized_keys_mode }}}}', got {file_params.get('mode')!r}"
        )


class TestSudoConfiguration:
    """Tests for sudo privilege configuration files."""

    def test_manual_user_sudo_content_requires_password(self):
        """Test that the manual user sudo file requires a password."""
        tasks = load_tasks("users")
        task = find_task(tasks, "grant sudo privileges to manual user")
        assert task is not None, "Could not find manual user sudo task"
        copy_params = task["ansible.builtin.copy"]
        content = copy_params.get("content", "")
        assert content == "{{ manual_user_name }} ALL=(ALL:ALL) ALL\n", (
            f"Expected password-required sudo content, got {content!r}"
        )

    def test_ansible_user_sudo_content_is_passwordless(self):
        """Test that the Ansible user sudo file grants passwordless sudo."""
        tasks = load_tasks("users")
        task = find_task(tasks, "grant passwordless sudo privileges to ansible user")
        assert task is not None, "Could not find Ansible user sudo task"
        copy_params = task["ansible.builtin.copy"]
        content = copy_params.get("content", "")
        assert content == "{{ deploy_user_name }} ALL=(ALL:ALL) NOPASSWD:ALL\n", (
            f"Expected passwordless sudo content, got {content!r}"
        )

    def test_manual_user_sudo_file_mode_0440(self):
        """Test that the manual user sudo file is deployed with mode 0440."""
        tasks = load_tasks("users")
        task = find_task(tasks, "grant sudo privileges to manual user")
        assert task is not None, "Could not find manual user sudo task"
        copy_params = task["ansible.builtin.copy"]
        assert copy_params.get("mode") == "0440", (
            f"Expected mode 0440 for sudo file, got {copy_params.get('mode')!r}"
        )

    def test_ansible_user_sudo_file_mode_0440(self):
        """Test that the Ansible user sudo file is deployed with mode 0440."""
        tasks = load_tasks("users")
        task = find_task(tasks, "grant passwordless sudo privileges to ansible user")
        assert task is not None, "Could not find Ansible user sudo task"
        copy_params = task["ansible.builtin.copy"]
        assert copy_params.get("mode") == "0440", (
            f"Expected mode 0440 for sudo file, got {copy_params.get('mode')!r}"
        )

    def test_manual_user_sudo_file_uses_visudo_validate(self):
        """Test that the manual user sudo file uses visudo for validation."""
        tasks = load_tasks("users")
        task = find_task(tasks, "grant sudo privileges to manual user")
        assert task is not None, "Could not find manual user sudo task"
        copy_params = task["ansible.builtin.copy"]
        assert copy_params.get("validate") == "visudo -cf %s", (
            f"Expected validate: 'visudo -cf %s', got {copy_params.get('validate')!r}"
        )

    def test_ansible_user_sudo_file_uses_visudo_validate(self):
        """Test that the Ansible user sudo file uses visudo for validation."""
        tasks = load_tasks("users")
        task = find_task(tasks, "grant passwordless sudo privileges to ansible user")
        assert task is not None, "Could not find Ansible user sudo task"
        copy_params = task["ansible.builtin.copy"]
        assert copy_params.get("validate") == "visudo -cf %s", (
            f"Expected validate: 'visudo -cf %s', got {copy_params.get('validate')!r}"
        )
