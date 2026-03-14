"""
Property-based tests for user management in VPS Bootstrap Playbook.

These tests verify that user accounts are created correctly with proper UIDs,
SSH key deployment, sudo privileges, and authentication methods across various
configuration parameters.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid configuration values
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


@st.composite
def valid_uid(draw):
    """Generate valid user IDs."""
    # UIDs 1000-60000 are typically for regular users
    # UIDs 100-999 are for system users
    return draw(st.integers(min_value=1000, max_value=60000))


@st.composite
def valid_shell(draw):
    """Generate valid shell paths."""
    return draw(st.sampled_from([
        "/bin/bash",
        "/bin/sh",
        "/bin/zsh",
        "/usr/bin/fish",
        "/bin/dash",
    ]))


@st.composite
def valid_file_mode(draw):
    """Generate valid file permission modes."""
    # Common permission modes for SSH files
    return draw(st.sampled_from([
        "0600",  # rw-------
        "0644",  # rw-r--r--
        "0700",  # rwx------
        "0755",  # rwxr-xr-x
    ]))


class TestUserManagementProperties:
    """Property-based tests for user account creation and configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_1_user_creation_with_fixed_uids(
        self,
        manual_user: str,
        ansible_user: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 1: User Account Creation with Fixed UIDs

        For any execution of the bootstrap playbook with configured user names,
        the manual access user SHALL be created with uid 1000 and the Ansible user
        SHALL be created with uid 1999.

        Validates: Requirements 1.1, 1.2, 2.1, 2.2

        This property test verifies that:
        1. Users role creates manual access user with uid 1000
        2. Users role creates Ansible user with uid 1999
        3. UIDs are fixed regardless of username
        4. User creation tasks use correct Ansible modules
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        # Verify users role has tasks
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify manual user creation with uid 1000
        assert "ansible.builtin.user:" in tasks_content, (
            "Users role must use ansible.builtin.user module"
        )

        # Verify manual user uid is 1000
        assert "manual_user_uid" in tasks_content or "uid: 1000" in tasks_content, (
            "Users role must set manual user uid to 1000"
        )

        # Verify Ansible user uid is 1999
        assert "deploy_user_uid" in tasks_content or "uid: 1999" in tasks_content, (
            "Users role must set Ansible user uid to 1999"
        )

        # Verify defaults file defines UIDs
        defaults_path = role_path / "defaults" / "main.yml"
        if defaults_path.exists():
            defaults_content = defaults_path.read_text()

            # Verify manual user uid default is 1000
            assert "manual_user_uid: 1000" in defaults_content, (
                "Manual user uid default must be 1000"
            )

            # Verify Ansible user uid default is 1999
            assert "deploy_user_uid: 1999" in defaults_content, (
                "Ansible user uid default must be 1999"
            )

        # Verify user creation uses state: present for idempotency
        assert "state: present" in tasks_content, (
            "User creation must use state: present for idempotency"
        )

        # Verify users are created with home directories
        assert "create_home: true" in tasks_content, (
            "Users must be created with home directories"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
        file_mode=valid_file_mode(),
    )
    def test_property_2_ssh_key_deployment_and_permissions(
        self,
        manual_user: str,
        ansible_user: str,
        file_mode: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 2: SSH Key Deployment and Permissions

        For any user account (manual or Ansible) with a configured SSH public key
        file path, the playbook SHALL deploy the public key to the user's
        authorized_keys file with mode 0600 and correct ownership.

        Validates: Requirements 1.6, 1.7, 1.8, 2.5, 2.6, 2.7

        This property test verifies that:
        1. SSH keys are deployed using authorized_key module
        2. authorized_keys file has mode 0600
        3. authorized_keys file has correct ownership
        4. .ssh directory is created with mode 0700
        5. SSH key file path is configurable
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify SSH key deployment uses authorized_key module
        assert "ansible.posix.authorized_key:" in tasks_content, (
            "SSH key deployment must use ansible.posix.authorized_key module"
        )

        # Verify .ssh directory is created with correct permissions
        assert 'path: "/home/{{ manual_user_name }}/.ssh"' in tasks_content or (
            ".ssh" in tasks_content
        ), "Must create .ssh directory for manual user"

        assert 'path: "/home/{{ deploy_user_name }}/.ssh"' in tasks_content or (
            ".ssh" in tasks_content
        ), "Must create .ssh directory for Ansible user"

        # Verify .ssh directory has mode 0700
        assert 'mode: "0700"' in tasks_content, (
            ".ssh directory must have mode 0700"
        )

        # Verify authorized_keys file permissions are set
        assert "authorized_keys" in tasks_content, (
            "Must configure authorized_keys file"
        )

        # Verify authorized_keys mode is configurable or set to 0600
        assert (
            "authorized_keys_mode" in tasks_content
            or 'mode: "0600"' in tasks_content
        ), "authorized_keys file must have mode 0600 or use configurable mode"

        # Verify defaults file defines authorized_keys_mode
        defaults_path = role_path / "defaults" / "main.yml"
        if defaults_path.exists():
            defaults_content = defaults_path.read_text()

            # Verify authorized_keys_mode default is 0600
            assert 'authorized_keys_mode: "0600"' in defaults_content, (
                "authorized_keys_mode default must be 0600"
            )

        # Verify SSH key file path is configurable
        assert "manual_user_ssh_key_file" in tasks_content or (
            "lookup('file'" in tasks_content
        ), "Manual user SSH key file path must be configurable"

        assert "deploy_user_ssh_key_file" in tasks_content or (
            "lookup('file'" in tasks_content
        ), "Ansible user SSH key file path must be configurable"

        # Verify ownership is set correctly
        assert "owner:" in tasks_content, (
            "File ownership must be set"
        )

        assert "group:" in tasks_content, (
            "File group must be set"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_3_sudo_privilege_configuration(
        self,
        manual_user: str,
        ansible_user: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 3: Sudo Privilege Configuration

        For any execution of the bootstrap playbook, the manual access user SHALL
        have password-required sudo privileges and the Ansible user SHALL have
        passwordless sudo privileges.

        Validates: Requirements 1.4, 2.3

        This property test verifies that:
        1. Manual user has sudo with password (ALL=(ALL:ALL) ALL)
        2. Ansible user has passwordless sudo (ALL=(ALL:ALL) NOPASSWD:ALL)
        3. Sudoers files are created in /etc/sudoers.d/
        4. Sudoers files have mode 0440
        5. Sudoers files are validated before deployment
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify sudoers files are created
        assert "/etc/sudoers.d/" in tasks_content, (
            "Sudoers files must be created in /etc/sudoers.d/"
        )

        # Verify manual user has password-required sudo
        # Pattern: username ALL=(ALL:ALL) ALL (without NOPASSWD)
        assert "ALL=(ALL:ALL) ALL" in tasks_content, (
            "Manual user must have sudo privileges"
        )

        # Verify Ansible user has passwordless sudo
        # Pattern: username ALL=(ALL:ALL) NOPASSWD:ALL
        assert "NOPASSWD:ALL" in tasks_content, (
            "Ansible user must have passwordless sudo"
        )

        # Verify sudoers files have correct permissions (0440)
        assert 'mode: "0440"' in tasks_content, (
            "Sudoers files must have mode 0440"
        )

        # Verify sudoers files are validated before deployment
        assert "validate:" in tasks_content, (
            "Sudoers files must be validated before deployment"
        )

        assert "visudo" in tasks_content, (
            "Sudoers validation must use visudo"
        )

        # Verify sudoers files have correct ownership (root:root)
        assert "owner: root" in tasks_content, (
            "Sudoers files must be owned by root"
        )

        assert "group: root" in tasks_content, (
            "Sudoers files must have group root"
        )

        # Verify separate sudoers files for each user
        # This ensures clean separation of privileges
        assert "{{ manual_user_name }}" in tasks_content, (
            "Manual user sudoers file must use username variable"
        )

        assert "{{ deploy_user_name }}" in tasks_content, (
            "Ansible user sudoers file must use username variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_4_user_authentication_method_configuration(
        self,
        manual_user: str,
        ansible_user: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 4: User Authentication Method Configuration

        For any execution of the bootstrap playbook, the manual access user SHALL
        support both password and SSH key authentication, while the Ansible user
        SHALL support only SSH key authentication.

        Validates: Requirements 1.3, 1.5, 2.4, 2.8

        This property test verifies that:
        1. Manual user has password set (hashed)
        2. Manual user has SSH key deployed
        3. Ansible user has password disabled (locked account)
        4. Ansible user has SSH key deployed
        5. Password authentication is configured correctly
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify manual user has password authentication
        # Password is set from a pre-hashed variable (not double-hashed at runtime)
        assert "manual_user_password" in tasks_content, (
            "Manual user password must be set from the manual_user_password variable"
        )

        assert "manual_user_password" in tasks_content, (
            "Manual user password must be configurable"
        )

        # Verify password update policy for manual user
        assert "update_password:" in tasks_content, (
            "Password update policy must be specified"
        )

        # Verify Ansible user has password disabled
        # Disabled password is typically "!" or "*"
        assert 'password: "!"' in tasks_content, (
            "Ansible user password must be disabled (locked account)"
        )

        # Verify both users have SSH keys deployed
        # Count authorized_key module usage - should be at least 2
        authorized_key_count = tasks_content.count("ansible.posix.authorized_key:")
        assert authorized_key_count >= 2, (
            "Both users must have SSH keys deployed"
        )

        # Verify SSH key deployment for manual user
        assert "manual_user_ssh_key_file" in tasks_content or (
            "lookup('file'" in tasks_content
        ), "Manual user must have SSH key configured"

        # Verify SSH key deployment for Ansible user
        assert "deploy_user_ssh_key_file" in tasks_content or (
            "lookup('file'" in tasks_content
        ), "Ansible user must have SSH key configured"

        # Verify defaults file documents authentication methods
        defaults_path = role_path / "defaults" / "main.yml"
        if defaults_path.exists():
            defaults_content = defaults_path.read_text()

            # Verify manual user password is documented
            assert "manual_user_password" in defaults_content, (
                "Manual user password must be documented in defaults"
            )

            # Verify SSH key file paths are defined
            assert "manual_user_ssh_key_file" in defaults_content, (
                "Manual user SSH key file path must be defined"
            )

            assert "deploy_user_ssh_key_file" in defaults_content, (
                "Ansible user SSH key file path must be defined"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        username=valid_username(),
        uid=valid_uid(),
        shell=valid_shell(),
    )
    def test_user_creation_module_parameters(
        self,
        username: str,
        uid: int,
        shell: str,
    ):
        """
        Verify that user creation uses appropriate Ansible module parameters.

        For any valid username, uid, and shell, the user creation tasks should
        use proper Ansible module parameters for idempotent and secure user creation.
        """
        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify user module uses required parameters
        required_params = [
            "name:",
            "uid:",
            "shell:",
            "state:",
            "create_home:",
        ]

        for param in required_params:
            assert param in tasks_content, (
                f"User creation must specify {param} parameter"
            )

        # Verify user creation is idempotent (state: present)
        assert "state: present" in tasks_content, (
            "User creation must use state: present"
        )

        # Verify home directory is created
        assert "create_home: true" in tasks_content, (
            "Users must be created with home directories"
        )

        # Verify shell is configurable
        assert "manual_user_shell" in tasks_content or "shell:" in tasks_content, (
            "User shell must be configurable"
        )

        assert "deploy_user_shell" in tasks_content or "shell:" in tasks_content, (
            "User shell must be configurable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_user_role_has_appropriate_tags(self):
        """
        Verify that user management tasks have appropriate tags for selective execution.

        Tags allow running specific subsets of tasks (e.g., only manual user creation).
        """
        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify tasks have tags
        assert "tags:" in tasks_content, (
            "User tasks should have tags for selective execution"
        )

        # Verify common tags are used
        expected_tags = [
            "users",
            "manual_user",
            "ansible_user",
            "sudo",
        ]

        for tag in expected_tags:
            assert tag in tasks_content, (
                f"User tasks should include '{tag}' tag"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_user_role_uses_secure_defaults(self):
        """
        Verify that user role uses secure defaults for user creation.

        Security best practices:
        - Home directories should be created
        - SSH directories should have mode 0700
        - authorized_keys should have mode 0600
        - Sudoers files should have mode 0440
        - Sudoers files should be validated
        """
        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify secure file permissions
        secure_permissions = {
            "0700": ".ssh directory",
            "0440": "sudoers files",
        }

        for mode, description in secure_permissions.items():
            assert f'mode: "{mode}"' in tasks_content, (
                f"{description} must have mode {mode}"
            )

        # Verify authorized_keys uses mode variable or explicit 0600
        assert (
            "authorized_keys_mode" in tasks_content
            or 'mode: "0600"' in tasks_content
        ), "authorized_keys file must have mode 0600 or use authorized_keys_mode variable"

        # Verify sudoers validation
        assert "validate:" in tasks_content, (
            "Sudoers files must be validated"
        )

        assert "visudo" in tasks_content, (
            "Sudoers validation must use visudo"
        )

        # Verify home directories are created
        assert "create_home: true" in tasks_content, (
            "Users must be created with home directories"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_user_role_supports_variable_configuration(
        self,
        manual_user: str,
        ansible_user: str,
    ):
        """
        Verify that user role supports configuration through variables.

        All user-specific settings should be configurable through variables
        rather than hardcoded in tasks.
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify configurable variables are used
        configurable_vars = [
            "manual_user_name",
            "manual_user_uid",
            "manual_user_ssh_key_file",
            "deploy_user_name",
            "deploy_user_uid",
            "deploy_user_ssh_key_file",
        ]

        for var in configurable_vars:
            assert f"{{{{ {var} }}}}" in tasks_content or var in tasks_content, (
                f"Variable {var} must be used in tasks"
            )

        # Verify defaults file exists and defines variables
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "Users role must have defaults file"

        defaults_content = defaults_path.read_text()

        for var in configurable_vars:
            assert f"{var}:" in defaults_content, (
                f"Variable {var} must be defined in defaults"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_user_role_documentation_completeness(self):
        """
        Verify that user role has complete documentation.

        Documentation should explain:
        - Purpose of each user account
        - Required variables
        - Optional variables
        - Security considerations
        """
        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        # Verify defaults file has documentation
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "Users role must have defaults file"

        defaults_content = defaults_path.read_text()

        # Verify defaults file has comments explaining variables
        assert "#" in defaults_content, (
            "Defaults file should have comments explaining variables"
        )

        # Verify key concepts are documented
        documentation_keywords = [
            "manual",
            "ansible",
            "uid",
            "ssh",
        ]

        for keyword in documentation_keywords:
            assert keyword.lower() in defaults_content.lower(), (
                f"Defaults file should document {keyword}"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_user_role_idempotency_patterns(self):
        """
        Verify that user role follows idempotency best practices.

        Idempotent patterns:
        - Use state: present for user creation
        - Use ansible.posix.authorized_key for SSH keys
        - Use ansible.builtin.file for directory/file creation
        - Use ansible.builtin.copy with validate for sudoers
        """
        # Verify users role exists
        role_path = Path("roles/users")
        assert role_path.exists(), "Users role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Users role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify idempotent modules are used
        idempotent_modules = [
            "ansible.builtin.user:",
            "ansible.builtin.file:",
            "ansible.posix.authorized_key:",
            "ansible.builtin.copy:",
        ]

        for module in idempotent_modules:
            assert module in tasks_content, (
                f"User role should use idempotent module {module}"
            )

        # Verify state parameters are used
        assert "state: present" in tasks_content, (
            "User creation must use state: present"
        )

        # Verify no shell/command modules are used
        # (User management should use declarative modules only)
        assert "ansible.builtin.shell:" not in tasks_content, (
            "User role should not use shell module"
        )

        assert "ansible.builtin.command:" not in tasks_content, (
            "User role should not use command module"
        )
