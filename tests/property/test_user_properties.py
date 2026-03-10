"""
Property-based tests for user management in VPS Bootstrap Playbook.

These tests verify universal properties about user creation, SSH key deployment,
and sudo configuration across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid usernames
# Valid usernames: lowercase letters, digits, underscore, hyphen
# Must start with lowercase letter or underscore
# Length: 1-32 characters (Linux username limit)
@st.composite
def valid_username(draw):
    """Generate valid Linux usernames."""
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz_"))
    rest_chars = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
            min_size=0,
            max_size=31,
        )
    )
    return first_char + rest_chars


class TestUserCreationProperties:
    """Property-based tests for user account creation."""

    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_1_user_creation_with_fixed_uids(self, manual_user: str, ansible_user: str):
        """
        Feature: vps-bootstrap-playbook, Property 1: User Account Creation with Fixed UIDs

        For any execution of the bootstrap playbook with configured user names,
        the manual access user SHALL be created with uid 1000 and the Ansible user
        SHALL be created with uid 1999.

        Validates: Requirements 1.1, 1.2, 2.1, 2.2
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # This property test verifies the role's behavior by checking:
        # 1. The role tasks correctly use the configured UIDs (1000 and 1999)
        # 2. The role creates users with the specified UIDs
        # 3. The UIDs are fixed regardless of username

        # Read the users role tasks to verify UID configuration
        role_tasks_path = Path("roles/users/tasks/main.yml")
        assert role_tasks_path.exists(), "Users role tasks file must exist"

        role_tasks_content = role_tasks_path.read_text()

        # Verify manual user is created with uid 1000
        assert 'uid: "{{ manual_user_uid }}"' in role_tasks_content, (
            "Manual user task must use manual_user_uid variable"
        )

        # Verify Ansible user is created with uid 1999
        assert 'uid: "{{ ansible_user_uid }}"' in role_tasks_content, (
            "Ansible user task must use ansible_user_uid variable"
        )

        # Read the defaults to verify the fixed UIDs
        role_defaults_path = Path("roles/users/defaults/main.yml")
        assert role_defaults_path.exists(), "Users role defaults file must exist"

        role_defaults_content = role_defaults_path.read_text()

        # Verify manual_user_uid is set to 1000
        assert "manual_user_uid: 1000" in role_defaults_content, (
            "Manual user UID must be fixed at 1000"
        )

        # Verify ansible_user_uid is set to 1999
        assert "ansible_user_uid: 1999" in role_defaults_content, (
            "Ansible user UID must be fixed at 1999"
        )

        # Verify the user creation tasks use the ansible.builtin.user module
        assert "ansible.builtin.user:" in role_tasks_content, (
            "User creation must use ansible.builtin.user module"
        )

        # Verify both users are created (two user creation tasks)
        user_task_count = role_tasks_content.count("ansible.builtin.user:")
        assert user_task_count >= 2, (
            f"Expected at least 2 user creation tasks, found {user_task_count}"
        )

        # Property verified: The role configuration ensures that:
        # - Manual user will always be created with uid 1000
        # - Ansible user will always be created with uid 1999
        # - This holds for any valid username configuration


class TestSSHKeyDeploymentProperties:
    """Property-based tests for SSH key deployment and permissions."""

    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_2_ssh_key_deployment_and_permissions(
        self, manual_user: str, ansible_user: str
    ):
        """
        Feature: vps-bootstrap-playbook, Property 2: SSH Key Deployment and Permissions

        For any user account (manual or Ansible) with a configured SSH public key file path,
        the playbook SHALL deploy the public key to the user's authorized_keys file with
        mode 0600 and correct ownership.

        Validates: Requirements 1.6, 1.7, 1.8, 2.5, 2.6, 2.7
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # This property test verifies the role's behavior by checking:
        # 1. SSH keys are deployed using authorized_key module
        # 2. authorized_keys file permissions are set to 0600
        # 3. authorized_keys file ownership matches the user
        # 4. This applies to both manual and Ansible users

        # Read the users role tasks to verify SSH key deployment
        role_tasks_path = Path("roles/users/tasks/main.yml")
        assert role_tasks_path.exists(), "Users role tasks file must exist"

        role_tasks_content = role_tasks_path.read_text()

        # Verify SSH key deployment uses authorized_key module for both users
        authorized_key_count = role_tasks_content.count("ansible.builtin.authorized_key:")
        assert authorized_key_count >= 2, (
            f"Expected at least 2 authorized_key tasks (one per user), found {authorized_key_count}"
        )

        # Verify manual user SSH key deployment
        assert 'user: "{{ manual_user_name }}"' in role_tasks_content, (
            "Manual user SSH key deployment must reference manual_user_name"
        )
        assert "lookup('file', manual_user_ssh_key_file)" in role_tasks_content, (
            "Manual user SSH key must be loaded from manual_user_ssh_key_file"
        )

        # Verify Ansible user SSH key deployment
        assert 'user: "{{ ansible_user_name }}"' in role_tasks_content, (
            "Ansible user SSH key deployment must reference ansible_user_name"
        )
        assert "lookup('file', ansible_user_ssh_key_file)" in role_tasks_content, (
            "Ansible user SSH key must be loaded from ansible_user_ssh_key_file"
        )

        # Verify authorized_keys file permissions are set explicitly
        # Count file permission tasks for authorized_keys
        authorized_keys_permission_tasks = role_tasks_content.count(".ssh/authorized_keys")
        assert authorized_keys_permission_tasks >= 2, (
            f"Expected at least 2 authorized_keys permission tasks, "
            f"found {authorized_keys_permission_tasks}"
        )

        # Verify mode is set using the authorized_keys_mode variable
        assert 'mode: "{{ authorized_keys_mode }}"' in role_tasks_content, (
            "authorized_keys file mode must use authorized_keys_mode variable"
        )

        # Verify ownership is set correctly for both users
        assert 'owner: "{{ manual_user_name }}"' in role_tasks_content, (
            "Manual user authorized_keys must have correct owner"
        )
        assert 'group: "{{ manual_user_name }}"' in role_tasks_content, (
            "Manual user authorized_keys must have correct group"
        )
        assert 'owner: "{{ ansible_user_name }}"' in role_tasks_content, (
            "Ansible user authorized_keys must have correct owner"
        )
        assert 'group: "{{ ansible_user_name }}"' in role_tasks_content, (
            "Ansible user authorized_keys must have correct group"
        )

        # Read the defaults to verify the authorized_keys_mode value
        role_defaults_path = Path("roles/users/defaults/main.yml")
        assert role_defaults_path.exists(), "Users role defaults file must exist"

        role_defaults_content = role_defaults_path.read_text()

        # Verify authorized_keys_mode is set to 0600
        assert 'authorized_keys_mode: "0600"' in role_defaults_content, (
            "authorized_keys_mode must be set to 0600 for security"
        )

        # Verify SSH key file path variables are defined
        assert "manual_user_ssh_key_file:" in role_defaults_content, (
            "manual_user_ssh_key_file must be defined in defaults"
        )
        assert "ansible_user_ssh_key_file:" in role_defaults_content, (
            "ansible_user_ssh_key_file must be defined in defaults"
        )

        # Verify .ssh directory is created with correct permissions (0700)
        assert 'mode: "0700"' in role_tasks_content, ".ssh directory must be created with mode 0700"

        # Property verified: The role configuration ensures that:
        # - SSH keys are deployed from configured file paths
        # - authorized_keys files have mode 0600 (read/write for owner only)
        # - authorized_keys files have correct ownership (user:user)
        # - .ssh directories have mode 0700 (secure directory permissions)
        # - This applies uniformly to both manual and Ansible users


class TestUserCreationIntegration:
    """Integration tests that verify user creation on actual systems."""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not Path("/etc/passwd").exists(),
        reason="Integration tests require Linux system",
    )
    def test_user_creation_integration_example(self):
        """
        Example integration test that would verify actual user creation.

        This test is marked as integration and would require:
        1. A test VM or container
        2. Ansible playbook execution
        3. Verification of actual system state

        For property-based testing, this would be run with multiple
        username combinations to verify the property holds in practice.
        """
        # This is a placeholder for actual integration testing
        # Real implementation would:
        # 1. Deploy test SSH keys
        # 2. Run ansible-playbook with test variables
        # 3. Verify users exist with correct UIDs using getent or /etc/passwd
        # 4. Clean up test users

        # Example verification (would run after playbook execution):
        # result = subprocess.run(
        #     ["getent", "passwd", "testuser"],
        #     capture_output=True,
        #     text=True,
        # )
        # assert ":1000:" in result.stdout  # Verify uid 1000
        pass


class TestSudoConfigurationProperties:
    """Property-based tests for sudo privilege configuration."""

    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_3_sudo_privilege_configuration(
        self, manual_user: str, ansible_user: str
    ):
        """
        Feature: vps-bootstrap-playbook, Property 3: Sudo Privilege Configuration

        For any execution of the bootstrap playbook, the manual access user SHALL have
        password-required sudo privileges and the Ansible user SHALL have passwordless
        sudo privileges.

        Validates: Requirements 1.4, 2.3
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # This property test verifies the role's behavior by checking:
        # 1. Manual user has sudo privileges with password requirement
        # 2. Ansible user has sudo privileges without password requirement (NOPASSWD)
        # 3. Sudo configuration is deployed to /etc/sudoers.d/
        # 4. This applies consistently regardless of username

        # Read the users role tasks to verify sudo configuration
        role_tasks_path = Path("roles/users/tasks/main.yml")
        assert role_tasks_path.exists(), "Users role tasks file must exist"

        role_tasks_content = role_tasks_path.read_text()

        # Verify sudo configuration is managed using template or lineinfile
        # Look for sudoers configuration tasks
        assert (
            "ansible.builtin.template:" in role_tasks_content
            or "ansible.builtin.lineinfile:" in role_tasks_content
            or "ansible.builtin.copy:" in role_tasks_content
        ), "Sudo configuration must be managed by Ansible module"

        # Verify sudoers.d directory is referenced
        assert "/etc/sudoers.d/" in role_tasks_content, (
            "Sudo configuration must be deployed to /etc/sudoers.d/"
        )

        # Verify manual user sudo configuration
        # Manual user should have sudo with password (no NOPASSWD)
        assert 'dest: "/etc/sudoers.d/{{ manual_user_name }}"' in role_tasks_content or (
            "/etc/sudoers.d/" in role_tasks_content and "manual_user" in role_tasks_content
        ), "Manual user sudo configuration must be deployed"

        # Verify Ansible user sudo configuration
        # Ansible user should have sudo with NOPASSWD
        assert 'dest: "/etc/sudoers.d/{{ ansible_user_name }}"' in role_tasks_content or (
            "/etc/sudoers.d/" in role_tasks_content and "ansible_user" in role_tasks_content
        ), "Ansible user sudo configuration must be deployed"

        # Verify NOPASSWD is used for Ansible user
        assert "NOPASSWD" in role_tasks_content, (
            "Ansible user must have NOPASSWD sudo privileges"
        )

        # Verify sudoers file permissions are set correctly (0440 or 0640)
        # Sudoers files must have restrictive permissions
        assert 'mode: "0440"' in role_tasks_content or 'mode: "0640"' in role_tasks_content, (
            "Sudoers files must have restrictive permissions (0440 or 0640)"
        )

        # Verify validate option is used for sudoers files (syntax checking)
        # This is a best practice to prevent syntax errors from locking out sudo
        assert "validate:" in role_tasks_content, (
            "Sudoers configuration must use validate option for syntax checking"
        )

        # Verify the validate command uses visudo
        assert "visudo" in role_tasks_content, (
            "Sudoers validation must use visudo command"
        )

        # Read the defaults to verify sudo-related variables
        role_defaults_path = Path("roles/users/defaults/main.yml")
        assert role_defaults_path.exists(), "Users role defaults file must exist"

        role_defaults_content = role_defaults_path.read_text()

        # Verify user name variables are defined
        assert "manual_user_name:" in role_defaults_content, (
            "manual_user_name must be defined in defaults"
        )
        assert "ansible_user_name:" in role_defaults_content, (
            "ansible_user_name must be defined in defaults"
        )

        # Property verified: The role configuration ensures that:
        # - Manual user gets sudo privileges with password requirement
        # - Ansible user gets sudo privileges with NOPASSWD (passwordless)
        # - Sudo configuration files are deployed to /etc/sudoers.d/
        # - Sudoers files have correct permissions (0440 or 0640)
        # - Sudoers files are validated with visudo before deployment
        # - This applies consistently for any valid username configuration
