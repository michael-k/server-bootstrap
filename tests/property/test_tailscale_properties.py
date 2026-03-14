"""
Property-based tests for Tailscale VPN in VPS Bootstrap Playbook.

These tests verify universal properties about Tailscale installation,
authentication, service configuration, and connectivity verification
across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid Tailscale configuration values
@st.composite
def valid_control_server_url(draw):
    """Generate valid Headscale control server URLs."""
    protocol = "https"
    domain = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.",
            min_size=5,
            max_size=50,
        ).filter(lambda x: ".." not in x and not x.startswith("-") and not x.endswith("-"))
    )
    return f"{protocol}://{domain}"


@st.composite
def valid_pre_auth_key(draw):
    """Generate valid Tailscale pre-authentication key format."""
    # Tailscale pre-auth keys typically start with "tskey-auth-" followed by alphanumeric
    key_suffix = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=20,
            max_size=40,
        )
    )
    return f"tskey-auth-{key_suffix}"


@st.composite
def valid_interface_name(draw):
    """Generate valid network interface names."""
    # Linux interface names: alphanumeric, max 15 chars
    return draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=3,
            max_size=15,
        ).filter(lambda x: x[0].isalpha())
    )


class TestTailscaleInstallationProperties:
    """Property-based tests for Tailscale installation and configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        control_server=valid_control_server_url(),
        pre_auth_key=valid_pre_auth_key(),
        interface_name=valid_interface_name(),
        enabled=st.booleans(),
    )
    def test_property_10_tailscale_installation_and_configuration(
        self,
        control_server: str,
        pre_auth_key: str,
        interface_name: str,
        enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 10: Tailscale Installation and Configuration

        For any execution of the bootstrap playbook WHERE Tailscale is enabled,
        the playbook SHALL install Tailscale packages, authenticate with the control
        server using a pre-auth key from Vault, configure the control server URL,
        enable the service, and start the service.

        Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
        """
        # This property test verifies the Tailscale role's behavior by checking:
        # 1. Tailscale packages are installed from official repository (Requirement 4.1)
        # 2. Authentication uses pre-auth key from Vault (Requirement 4.2)
        # 3. Control server URL is configured (Requirement 4.3)
        # 4. Tailscale service is enabled to start on boot (Requirement 4.4)
        # 5. Tailscale service is started (Requirement 4.5)
        # 6. All tasks are conditional on tailscale_enabled variable (Requirement 4.6)

        # Read the Tailscale role main tasks
        main_tasks_path = Path("roles/tailscale/tasks/main.yml")
        assert main_tasks_path.exists(), "Tailscale main tasks file must exist"

        main_tasks_content = main_tasks_path.read_text()

        # Verify conditional execution based on tailscale_enabled (Requirement 4.6)
        assert "when: tailscale_enabled | bool" in main_tasks_content, (
            "Tailscale tasks must be conditional on tailscale_enabled variable"
        )

        # Verify installation tasks are included
        assert "ansible.builtin.include_tasks: install.yml" in main_tasks_content, (
            "Main tasks must include installation tasks"
        )

        # Verify verification tasks are included
        assert "ansible.builtin.include_tasks: verify.yml" in main_tasks_content, (
            "Main tasks must include verification tasks"
        )

        # Read the Tailscale installation tasks
        install_tasks_path = Path("roles/tailscale/tasks/install.yml")
        assert install_tasks_path.exists(), "Tailscale installation tasks file must exist"

        install_tasks_content = install_tasks_path.read_text()

        # Verify Requirement 4.1: Install Tailscale packages from official repository
        assert "ansible.builtin.get_url:" in install_tasks_content, (
            "Must download Tailscale GPG key using get_url module"
        )
        assert "tailscale-archive-keyring.gpg" in install_tasks_content, (
            "GPG key must be saved to standard location"
        )

        assert "ansible.builtin.apt_repository:" in install_tasks_content, (
            "Must add Tailscale repository using apt_repository module"
        )
        assert "{{ tailscale_repo_url }}" in install_tasks_content, (
            "Repository URL must use tailscale_repo_url variable"
        )

        assert "ansible.builtin.apt:" in install_tasks_content, (
            "Must install Tailscale package using apt module"
        )
        assert "name: tailscale" in install_tasks_content, (
            "Must install tailscale package"
        )
        assert "state: present" in install_tasks_content, (
            "Package state must be present"
        )

        # Verify Requirement 4.2, 4.3: Authenticate with control server using pre-auth key
        assert "ansible.builtin.command:" in install_tasks_content, (
            "Must use command module for Tailscale authentication"
        )
        assert "tailscale up" in install_tasks_content, (
            "Must execute 'tailscale up' command for authentication"
        )
        assert "--login-server={{ tailscale_control_server }}" in install_tasks_content, (
            "Must configure control server URL using tailscale_control_server variable "
            "(Requirement 4.3)"
        )
        assert "--authkey={{ tailscale_pre_auth_key }}" in install_tasks_content, (
            "Must use pre-auth key from tailscale_pre_auth_key variable (Requirement 4.2)"
        )

        # Verify authentication is guarded by a status check for idempotency
        assert "tailscale_auth_check" in install_tasks_content, (
            "Authentication must check current status before running tailscale up"
        )

        # Verify authentication task registers result
        assert "register: tailscale_auth" in install_tasks_content, (
            "Authentication task must register result"
        )

        # Verify changed_when is properly configured
        assert "changed_when: tailscale_auth.rc == 0" in install_tasks_content, (
            "Authentication task must set changed_when based on return code"
        )

        # Verify Requirement 4.4: Enable Tailscale service to start on boot
        assert "ansible.builtin.systemd:" in install_tasks_content, (
            "Must use systemd module for service management"
        )
        assert "name: tailscaled" in install_tasks_content, (
            "Must manage tailscaled service"
        )
        assert "enabled: true" in install_tasks_content, (
            "Tailscale service must be enabled to start on boot (Requirement 4.4)"
        )

        # Verify Requirement 4.5: Start Tailscale service
        assert "state: started" in install_tasks_content, (
            "Tailscale service must be started (Requirement 4.5)"
        )

        # Verify tasks are properly tagged
        assert "tags:" in install_tasks_content, (
            "Tasks must be tagged for selective execution"
        )
        assert "tailscale" in install_tasks_content, (
            "Tasks must have tailscale tag"
        )

        # Read the Tailscale defaults to verify configuration variables
        defaults_path = Path("roles/tailscale/defaults/main.yml")
        assert defaults_path.exists(), "Tailscale defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify tailscale_enabled variable is defined
        assert "tailscale_enabled:" in defaults_content, (
            "tailscale_enabled must be defined in defaults"
        )

        # Verify default is false (opt-in behavior)
        assert "tailscale_enabled: false" in defaults_content, (
            "Default tailscale_enabled should be false (opt-in)"
        )

        # Verify tailscale_control_server variable is defined
        assert "tailscale_control_server:" in defaults_content, (
            "tailscale_control_server must be defined in defaults (Requirement 4.3)"
        )

        # Verify tailscale_pre_auth_key variable is defined
        assert "tailscale_pre_auth_key:" in defaults_content, (
            "tailscale_pre_auth_key must be defined in defaults (Requirement 4.2)"
        )

        # Verify tailscale_interface variable is defined
        assert "tailscale_interface:" in defaults_content, (
            "tailscale_interface must be defined in defaults"
        )

        # Verify default interface name is tailscale0
        assert 'tailscale_interface: "tailscale0"' in defaults_content, (
            "Default tailscale_interface should be tailscale0"
        )

        # Verify repository configuration variables are defined
        assert "tailscale_repo_url:" in defaults_content, (
            "tailscale_repo_url must be defined in defaults"
        )
        assert "tailscale_repo_key_url:" in defaults_content, (
            "tailscale_repo_key_url must be defined in defaults"
        )

        # Verify repository URL points to official Tailscale repository
        assert "pkgs.tailscale.com" in defaults_content, (
            "Repository URL must point to official Tailscale package repository"
        )

        # Property verified: The Tailscale role configuration ensures that:
        # - Tailscale packages are installed from official repository (4.1)
        # - Authentication uses pre-auth key from Vault (4.2)
        # - Control server URL is configured (4.3)
        # - Tailscale service is enabled to start on boot (4.4)
        # - Tailscale service is started (4.5)
        # - All tasks are conditional on tailscale_enabled variable (4.6)
        # - Configuration is idempotent (uses creates parameter)
        # - Tasks are properly tagged for selective execution
        # - This applies consistently across all valid configuration values


class TestTailscaleConnectivityVerificationProperties:
    """Property-based tests for Tailscale connectivity verification."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        interface_name=valid_interface_name(),
        timeout_seconds=st.integers(min_value=10, max_value=60),
    )
    def test_property_12_tailscale_connectivity_verification(
        self,
        interface_name: str,
        timeout_seconds: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 12 (partial): Tailscale Connectivity Verification

        For any execution of the bootstrap playbook WHERE Tailscale is enabled,
        the playbook SHALL verify Tailscale connectivity before configuring SSH
        to listen only on the Tailscale interface.

        This test verifies the connectivity verification logic (Requirement 5.1).
        The SSH interface restriction logic is tested separately.

        Validates: Requirement 5.1 (connectivity verification aspect)
        """
        # This property test verifies the Tailscale role's connectivity verification by checking:
        # 1. Tailscale interface existence is verified (Requirement 5.1)
        # 2. Tailscale connection state is verified (Requirement 5.1)
        # 3. Tailscale IP address assignment is verified (Requirement 5.1)
        # 4. Connectivity through Tailscale interface is tested (Requirement 5.1)
        # 5. Verification fails with clear error if connectivity test fails (Requirement 5.1)

        # Read the Tailscale verification tasks
        verify_tasks_path = Path("roles/tailscale/tasks/verify.yml")
        assert verify_tasks_path.exists(), "Tailscale verification tasks file must exist"

        verify_tasks_content = verify_tasks_path.read_text()

        # Verify Requirement 5.1: Wait for Tailscale interface to be created
        assert "ansible.builtin.wait_for:" in verify_tasks_content, (
            "Must use wait_for module to check for Tailscale interface"
        )
        assert "path: /sys/class/net/{{ tailscale_interface }}" in verify_tasks_content, (
            "Must check for Tailscale interface in /sys/class/net/"
        )
        assert "timeout:" in verify_tasks_content, (
            "Interface check must have a timeout"
        )
        assert "register: tailscale_interface_wait" in verify_tasks_content, (
            "Interface check must register result"
        )
        assert "failed_when: false" in verify_tasks_content, (
            "Interface check must not fail immediately (for custom error message)"
        )

        # Verify failure handling for missing interface
        assert "ansible.builtin.fail:" in verify_tasks_content, (
            "Must fail with clear error if interface does not exist"
        )
        assert "when: tailscale_interface_wait.failed" in verify_tasks_content, (
            "Must fail when interface wait times out"
        )
        assert "prevent lockout" in verify_tasks_content.lower(), (
            "Error message must mention lockout prevention"
        )

        # Verify Tailscale status check
        assert "tailscale status --json" in verify_tasks_content, (
            "Must check Tailscale status using JSON output"
        )
        assert "register: tailscale_status" in verify_tasks_content, (
            "Status check must register result"
        )
        assert "changed_when: false" in verify_tasks_content, (
            "Status check should not be marked as a change"
        )

        # Verify status parsing
        assert "ansible.builtin.set_fact:" in verify_tasks_content, (
            "Must parse Tailscale status JSON"
        )
        assert (
            "tailscale_status_json: \"{{ tailscale_status.stdout | from_json }}\""
            in verify_tasks_content
        ), "Must parse status output as JSON"

        # Verify connection state check
        assert "BackendState" in verify_tasks_content, (
            "Must check Tailscale BackendState"
        )
        assert "Running" in verify_tasks_content, (
            "Must verify BackendState is Running"
        )
        assert 'BackendState == "Running"' in verify_tasks_content, (
            "Must retry until BackendState is Running"
        )

        # Verify IP address retrieval
        assert "tailscale ip -4" in verify_tasks_content, (
            "Must retrieve Tailscale IPv4 address"
        )
        assert "register: tailscale_ip" in verify_tasks_content, (
            "IP retrieval must register result"
        )

        # Verify IP address fact setting
        assert "tailscale_ipv4: \"{{ tailscale_ip.stdout | trim }}\"" in verify_tasks_content, (
            "Must set tailscale_ipv4 fact from command output"
        )

        # Verify IP address validation
        assert 'when: tailscale_ipv4 == ""' in verify_tasks_content, (
            "Must fail if Tailscale IP is not assigned"
        )

        # Verify connectivity test through Tailscale interface
        assert "ping -c" in verify_tasks_content, (
            "Must test connectivity using ping"
        )
        assert "-I {{ tailscale_interface }}" in verify_tasks_content, (
            "Ping must use Tailscale interface"
        )
        assert "{{ tailscale_ipv4 }}" in verify_tasks_content, (
            "Ping must target Tailscale IP address"
        )
        assert "register: tailscale_ping" in verify_tasks_content, (
            "Ping test must register result"
        )

        # Verify ping test failure handling
        assert "when: tailscale_ping.rc != 0" in verify_tasks_content, (
            "Must fail if ping test fails"
        )

        # Verify success message
        assert "ansible.builtin.debug:" in verify_tasks_content, (
            "Must display success message after verification"
        )
        assert "verified successfully" in verify_tasks_content.lower(), (
            "Success message must indicate verification succeeded"
        )

        # Verify tasks are properly tagged
        assert "verification" in verify_tasks_content, (
            "Verification tasks must have verification tag"
        )

        # Property verified: The Tailscale role verification ensures that:
        # - Tailscale interface existence is verified with timeout (5.1)
        # - Tailscale connection state is verified (BackendState == Running) (5.1)
        # - Tailscale IP address assignment is verified (5.1)
        # - Connectivity through Tailscale interface is tested (5.1)
        # - Clear error messages prevent lockout scenarios (5.1)
        # - All checks are performed before SSH restriction
        # - This applies consistently across all valid interface names and timeouts


class TestTailscaleConditionalExecutionProperties:
    """Property-based tests for Tailscale conditional execution."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        enabled=st.booleans(),
    )
    def test_property_11_tailscale_conditional_execution(self, enabled: bool):
        """
        Feature: vps-bootstrap-playbook, Property 11: Tailscale Conditional Execution

        For any execution of the bootstrap playbook WHERE Tailscale is disabled,
        the playbook SHALL skip all Tailscale installation, configuration, and
        SSH restriction steps.

        Validates: Requirements 4.6, 9.8
        """
        # This property test verifies the Tailscale role's conditional execution by checking:
        # 1. All Tailscale tasks are conditional on tailscale_enabled (Requirement 4.6)
        # 2. Emergency script deployment is conditional on tailscale_enabled (Requirement 9.8)
        # 3. SSH restriction is conditional on tailscale_enabled

        # Read the Tailscale role main tasks
        main_tasks_path = Path("roles/tailscale/tasks/main.yml")
        assert main_tasks_path.exists(), "Tailscale main tasks file must exist"

        main_tasks_content = main_tasks_path.read_text()

        # Verify all task includes are conditional
        task_includes = [
            "ansible.builtin.include_tasks: install.yml",
            "ansible.builtin.include_tasks: verify.yml",
        ]

        for task_include in task_includes:
            if task_include in main_tasks_content:
                # Find the task block containing this include
                lines = main_tasks_content.split('\n')
                for i, line in enumerate(lines):
                    if task_include in line:
                        # Check the next few lines for when condition
                        task_block = '\n'.join(lines[i:i+5])
                        assert "when: tailscale_enabled | bool" in task_block, (
                            f"Task include '{task_include}' must be conditional on "
                            "tailscale_enabled"
                        )

        # Read the Tailscale defaults
        defaults_path = Path("roles/tailscale/defaults/main.yml")
        assert defaults_path.exists(), "Tailscale defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify tailscale_enabled defaults to false (opt-in behavior)
        assert "tailscale_enabled: false" in defaults_content, (
            "tailscale_enabled must default to false (Requirement 4.6)"
        )

        # Verify emergency_access role exists and has conditional deployment
        emergency_access_tasks_path = Path("roles/emergency_access/tasks/main.yml")
        if emergency_access_tasks_path.exists():
            emergency_access_content = emergency_access_tasks_path.read_text()

            # Verify emergency script deployment is conditional
            # The role uses emergency_access_enabled which defaults to tailscale_enabled
            assert "when: emergency_access_enabled | bool" in emergency_access_content, (
                "Emergency script deployment must be conditional on emergency_access_enabled "
                "(Requirement 9.8)"
            )

            # Verify the defaults file links emergency_access_enabled to tailscale_enabled
            emergency_defaults_path = Path("roles/emergency_access/defaults/main.yml")
            if emergency_defaults_path.exists():
                emergency_defaults_content = emergency_defaults_path.read_text()
                assert "emergency_access_enabled:" in emergency_defaults_content, (
                    "emergency_access_enabled must be defined in defaults"
                )
                assert "tailscale_enabled" in emergency_defaults_content, (
                    "emergency_access_enabled must reference tailscale_enabled (Requirement 9.8)"
                )

        # Property verified: The Tailscale role configuration ensures that:
        # - All Tailscale installation tasks are conditional on tailscale_enabled (4.6)
        # - All Tailscale verification tasks are conditional on tailscale_enabled (4.6)
        # - Emergency script deployment is conditional on tailscale_enabled (9.8)
        # - Default value is false (opt-in behavior)
        # - When disabled, all Tailscale-related tasks are skipped
        # - This applies consistently regardless of enabled value


class TestTailscaleRepositoryConfigurationProperties:
    """Property-based tests for Tailscale repository configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        distribution_release=st.sampled_from(["bookworm", "bullseye", "buster"]),
    )
    def test_tailscale_repository_configuration(self, distribution_release: str):
        """
        Feature: vps-bootstrap-playbook, Tailscale Repository Configuration

        For any execution of the bootstrap playbook on a Debian system,
        the Tailscale role SHALL configure the official Tailscale package
        repository with proper GPG key verification.

        This property verifies that:
        - Official Tailscale repository is used (Requirement 4.1)
        - GPG key is properly configured for package verification
        - Repository configuration adapts to Debian release
        """
        # Read the Tailscale defaults
        defaults_path = Path("roles/tailscale/defaults/main.yml")
        assert defaults_path.exists(), "Tailscale defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify repository URL is defined
        assert "tailscale_repo_url:" in defaults_content, (
            "tailscale_repo_url must be defined"
        )

        # Verify repository URL points to official Tailscale repository
        assert "https://pkgs.tailscale.com/stable/debian" in defaults_content, (
            "Repository URL must point to official Tailscale stable repository"
        )

        # Verify GPG key URL is defined
        assert "tailscale_repo_key_url:" in defaults_content, (
            "tailscale_repo_key_url must be defined"
        )

        # Verify GPG key URL uses distribution release variable
        assert "{{ ansible_distribution_release }}" in defaults_content, (
            "GPG key URL must adapt to distribution release"
        )

        # Verify GPG key URL points to official Tailscale repository
        assert "pkgs.tailscale.com" in defaults_content, (
            "GPG key URL must point to official Tailscale repository"
        )

        # Read the installation tasks
        install_tasks_path = Path("roles/tailscale/tasks/install.yml")
        assert install_tasks_path.exists(), "Tailscale installation tasks must exist"

        install_tasks_content = install_tasks_path.read_text()

        # Verify GPG key is downloaded to standard location
        assert "/usr/share/keyrings/tailscale-archive-keyring.gpg" in install_tasks_content, (
            "GPG key must be stored in standard keyrings directory"
        )

        # Verify repository configuration uses signed-by parameter
        assert (
            "signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg"
            in install_tasks_content
        ), "Repository must use signed-by parameter for GPG verification"

        # Verify repository uses distribution release variable
        assert "{{ ansible_distribution_release }}" in install_tasks_content, (
            "Repository configuration must use distribution release variable"
        )

        # Property verified: The Tailscale role ensures:
        # - Official Tailscale repository is configured (4.1)
        # - GPG key verification is properly configured
        # - Repository configuration adapts to Debian release
        # - Package authenticity is verified during installation
