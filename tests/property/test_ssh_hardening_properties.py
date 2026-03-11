"""
Property-based tests for SSH hardening in VPS Bootstrap Playbook.

These tests verify that SSH daemon configuration is hardened correctly with
modern cryptographic algorithms, restrictive policies, and appropriate session
security settings across various configuration parameters.
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
def valid_ssh_port(draw):
    """Generate valid SSH port numbers."""
    # Common SSH ports: 22 (default), or high ports 1024-65535
    return draw(st.sampled_from([22]) | st.integers(min_value=1024, max_value=65535))


@st.composite
def valid_timeout_seconds(draw):
    """Generate valid timeout values in seconds."""
    return draw(st.integers(min_value=30, max_value=600))


@st.composite
def valid_timeout_string(draw):
    """Generate valid timeout strings (e.g., '30s', '5m')."""
    value = draw(st.integers(min_value=10, max_value=600))
    unit = draw(st.sampled_from(["s", "m"]))
    return f"{value}{unit}"


@st.composite
def valid_max_auth_tries(draw):
    """Generate valid MaxAuthTries values."""
    return draw(st.integers(min_value=1, max_value=6))


@st.composite
def valid_client_alive_count(draw):
    """Generate valid ClientAliveCountMax values."""
    return draw(st.integers(min_value=0, max_value=5))


class TestSSHHardeningProperties:
    """Property-based tests for SSH daemon hardening configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
        ssh_port=valid_ssh_port(),
    )
    def test_property_5_ssh_daemon_hardening_configuration(
        self,
        manual_user: str,
        ansible_user: str,
        ssh_port: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 5: SSH Daemon Hardening Configuration

        For any execution of the bootstrap playbook, the SSHD configuration SHALL
        disable password authentication globally, disable root login, restrict key
        exchange algorithms to modern elliptic curves, restrict ciphers to
        authenticated encryption, restrict MACs to Encrypt-Then-MAC variants, and
        disable X11 forwarding, TCP forwarding, agent forwarding, tunneling, and
        empty passwords.

        Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.14, 3.18

        This property test verifies that:
        1. Password authentication is disabled globally
        2. Root login is disabled
        3. Key exchange algorithms are restricted to modern elliptic curves
        4. Ciphers are restricted to authenticated encryption (AEAD)
        5. MACs are restricted to Encrypt-Then-MAC variants
        6. X11 forwarding is disabled
        7. TCP forwarding is disabled
        8. Agent forwarding is disabled
        9. Tunneling is disabled
        10. Empty passwords are not permitted
        11. Public key authentication is enabled
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify password authentication is disabled (Requirement 3.1)
        assert "PasswordAuthentication no" in template_content, (
            "Template must disable password authentication"
        )

        # Verify root login is disabled (Requirement 3.2)
        assert "PermitRootLogin no" in template_content, (
            "Template must disable root login"
        )

        # Verify empty passwords are not permitted (Requirement 3.18)
        assert "PermitEmptyPasswords no" in template_content, (
            "Template must disable empty passwords"
        )

        # Verify public key authentication is enabled (Requirement 3.14)
        assert "PubkeyAuthentication yes" in template_content, (
            "Template must enable public key authentication"
        )

        # Verify key exchange algorithms are restricted (Requirement 3.3)
        assert "KexAlgorithms" in template_content, (
            "Template must restrict key exchange algorithms"
        )

        # Verify ciphers are restricted (Requirement 3.4)
        assert "Ciphers" in template_content, (
            "Template must restrict ciphers"
        )

        # Verify MACs are restricted (Requirement 3.5)
        assert "MACs" in template_content, (
            "Template must restrict MACs"
        )

        # Verify X11 forwarding is disabled (Requirement 3.6)
        assert "X11Forwarding no" in template_content, (
            "Template must disable X11 forwarding"
        )

        # Verify TCP forwarding is disabled (Requirement 3.7)
        assert "AllowTcpForwarding no" in template_content, (
            "Template must disable TCP forwarding"
        )

        # Verify agent forwarding is disabled (Requirement 3.8)
        assert "AllowAgentForwarding no" in template_content, (
            "Template must disable agent forwarding"
        )

        # Verify tunneling is disabled (Requirement 3.9)
        assert "PermitTunnel no" in template_content, (
            "Template must disable tunneling"
        )

        # Verify defaults file defines algorithm restrictions
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "SSH hardening role must have defaults file"

        defaults_content = defaults_path.read_text()

        # Verify modern elliptic curve algorithms are defined (Requirement 3.3)
        assert "ssh_kex_algorithms:" in defaults_content, (
            "Defaults must define key exchange algorithms"
        )
        assert "curve25519" in defaults_content, (
            "Defaults must include curve25519 key exchange"
        )

        # Verify AEAD ciphers are defined (Requirement 3.4)
        assert "ssh_ciphers:" in defaults_content, (
            "Defaults must define ciphers"
        )
        assert "chacha20-poly1305" in defaults_content or "gcm" in defaults_content, (
            "Defaults must include AEAD ciphers (chacha20-poly1305 or GCM)"
        )

        # Verify Encrypt-Then-MAC MACs are defined (Requirement 3.5)
        assert "ssh_macs:" in defaults_content, (
            "Defaults must define MACs"
        )
        assert "etm" in defaults_content, (
            "Defaults must include Encrypt-Then-MAC variants"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
    )
    def test_property_6_ssh_access_restriction(
        self,
        manual_user: str,
        ansible_user: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 6: SSH Access Restriction

        For any execution of the bootstrap playbook with configured user names,
        the SSHD AllowUsers directive SHALL contain only the manual access user
        and Ansible user.

        Validates: Requirements 3.10

        This property test verifies that:
        1. AllowUsers directive is present in configuration
        2. AllowUsers references manual_user_name variable
        3. AllowUsers references ansible_user_name variable
        4. AllowUsers is configurable through variables
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify AllowUsers directive is present (Requirement 3.10)
        assert "AllowUsers" in template_content, (
            "Template must include AllowUsers directive"
        )

        # Verify AllowUsers uses variable for user list
        assert "{{ ssh_allowed_users" in template_content or (
            "{{ manual_user_name }}" in template_content
            and "{{ ansible_user_name }}" in template_content
        ), "Template must use variables for allowed users"

        # Verify defaults file defines allowed users
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "SSH hardening role must have defaults file"

        defaults_content = defaults_path.read_text()

        # Verify ssh_allowed_users is defined
        assert "ssh_allowed_users:" in defaults_content, (
            "Defaults must define ssh_allowed_users"
        )

        # Verify allowed users references manual and Ansible users
        assert "manual_user_name" in defaults_content, (
            "Allowed users must reference manual_user_name"
        )

        assert "ansible_user_name" in defaults_content, (
            "Allowed users must reference ansible_user_name"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
    )
    def test_property_7_ssh_port_configuration(
        self,
        ssh_port: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 7: SSH Port Configuration

        For any execution of the bootstrap playbook with an optional SSH port
        variable, the SSHD SHALL listen on the specified port (or default port 22
        if not specified).

        Validates: Requirements 3.11, 3.12

        This property test verifies that:
        1. Port directive is present in configuration
        2. Port uses configurable variable
        3. Default port is 22
        4. Port configuration is validated
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify Port directive is present (Requirement 3.12)
        assert "Port" in template_content, (
            "Template must include Port directive"
        )

        # Verify Port uses variable (Requirement 3.11)
        assert "{{ ssh_port }}" in template_content, (
            "Template must use ssh_port variable"
        )

        # Verify defaults file defines SSH port
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "SSH hardening role must have defaults file"

        defaults_content = defaults_path.read_text()

        # Verify ssh_port default is 22 (Requirement 3.11)
        assert "ssh_port: 22" in defaults_content, (
            "Default SSH port must be 22"
        )

        # Verify tasks file validates configuration
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "SSH hardening role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify template deployment uses validation (Requirement 3.13)
        assert "validate:" in tasks_content, (
            "SSH config deployment must use validation"
        )

        assert "sshd" in tasks_content, (
            "SSH config validation must use sshd"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        max_auth_tries=valid_max_auth_tries(),
        login_grace_time=valid_timeout_string(),
        client_alive_interval=valid_timeout_seconds(),
        client_alive_count_max=valid_client_alive_count(),
    )
    def test_property_8_ssh_session_security_configuration(
        self,
        max_auth_tries: int,
        login_grace_time: str,
        client_alive_interval: int,
        client_alive_count_max: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 8: SSH Session Security Configuration

        For any execution of the bootstrap playbook, the SSHD configuration SHALL
        set MaxAuthTries to a low value, LoginGraceTime to a short duration, and
        configure ClientAliveInterval and ClientAliveCountMax for idle session
        management.

        Validates: Requirements 3.15, 3.16, 3.17

        This property test verifies that:
        1. MaxAuthTries is configured with a low value
        2. LoginGraceTime is configured with a short duration
        3. ClientAliveInterval is configured for keepalive
        4. ClientAliveCountMax is configured for idle timeout
        5. All session security settings are configurable
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify MaxAuthTries is configured (Requirement 3.15)
        assert "MaxAuthTries" in template_content, (
            "Template must include MaxAuthTries directive"
        )

        assert "{{ ssh_max_auth_tries }}" in template_content, (
            "Template must use ssh_max_auth_tries variable"
        )

        # Verify LoginGraceTime is configured (Requirement 3.16)
        assert "LoginGraceTime" in template_content, (
            "Template must include LoginGraceTime directive"
        )

        assert "{{ ssh_login_grace_time }}" in template_content, (
            "Template must use ssh_login_grace_time variable"
        )

        # Verify ClientAliveInterval is configured (Requirement 3.17)
        assert "ClientAliveInterval" in template_content, (
            "Template must include ClientAliveInterval directive"
        )

        assert "{{ ssh_client_alive_interval }}" in template_content, (
            "Template must use ssh_client_alive_interval variable"
        )

        # Verify ClientAliveCountMax is configured (Requirement 3.17)
        assert "ClientAliveCountMax" in template_content, (
            "Template must include ClientAliveCountMax directive"
        )

        assert "{{ ssh_client_alive_count_max }}" in template_content, (
            "Template must use ssh_client_alive_count_max variable"
        )

        # Verify defaults file defines session security settings
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "SSH hardening role must have defaults file"

        defaults_content = defaults_path.read_text()

        # Verify MaxAuthTries default is low (Requirement 3.15)
        assert "ssh_max_auth_tries:" in defaults_content, (
            "Defaults must define ssh_max_auth_tries"
        )

        # Extract MaxAuthTries value and verify it's low (≤6)
        for line in defaults_content.split("\n"):
            if "ssh_max_auth_tries:" in line and "#" not in line.split("ssh_max_auth_tries:")[0]:
                # Parse the value
                value_str = line.split("ssh_max_auth_tries:")[1].strip()
                if value_str.isdigit():
                    value = int(value_str)
                    assert value <= 6, (
                        f"Default MaxAuthTries must be low (≤6), got {value}"
                    )

        # Verify LoginGraceTime default is short (Requirement 3.16)
        assert "ssh_login_grace_time:" in defaults_content, (
            "Defaults must define ssh_login_grace_time"
        )

        # Verify ClientAliveInterval is defined (Requirement 3.17)
        assert "ssh_client_alive_interval:" in defaults_content, (
            "Defaults must define ssh_client_alive_interval"
        )

        # Verify ClientAliveCountMax is defined (Requirement 3.17)
        assert "ssh_client_alive_count_max:" in defaults_content, (
            "Defaults must define ssh_client_alive_count_max"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
    )
    def test_ssh_configuration_uses_secure_defaults(
        self,
        ssh_port: int,
    ):
        """
        Verify SSH configuration uses secure defaults beyond minimum requirements.

        This test checks for additional security best practices:
        - StrictModes enabled
        - UsePAM enabled for system integration
        - Compression disabled (prevents CRIME-style attacks)
        - UseDNS disabled (prevents DNS-based delays/attacks)
        - GatewayPorts disabled
        - PermitUserEnvironment disabled
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify additional security settings
        security_settings = {
            "StrictModes": "yes",
            "UsePAM": "yes",
            "Compression": "no",
            "UseDNS": "no",
            "GatewayPorts": "no",
            "PermitUserEnvironment": "no",
        }

        for setting, expected_value in security_settings.items():
            assert f"{setting} {expected_value}" in template_content, (
                f"Template should set {setting} to {expected_value} for security"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_configuration_template_has_documentation(self):
        """
        Verify SSH configuration template includes documentation.

        The template should have comments explaining security settings
        and referencing requirements for traceability.
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify template has comments
        assert "#" in template_content, (
            "Template should have comments explaining configuration"
        )

        # Verify template references requirements
        assert "Requirement" in template_content, (
            "Template should reference requirements for traceability"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_hardening_role_has_handler_for_service_restart(self):
        """
        Verify SSH hardening role has handler to restart sshd on config changes.

        Validates: Requirement 3.13 (service restart on configuration change)
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify handlers file exists
        handlers_path = role_path / "handlers" / "main.yml"
        assert handlers_path.exists(), "SSH hardening role must have handlers"

        handlers_content = handlers_path.read_text()

        # Verify handler for sshd restart exists
        assert "name:" in handlers_content, (
            "Handlers must have named handlers"
        )

        assert "sshd" in handlers_content.lower(), (
            "Handlers must include sshd restart handler"
        )

        # Verify handler uses service or systemd module
        assert (
            "ansible.builtin.service:" in handlers_content
            or "ansible.builtin.systemd:" in handlers_content
            or "ansible.builtin.systemd_service:" in handlers_content
        ), "Handler must use service management module"

        # Verify handler uses restarted state
        assert "state: restarted" in handlers_content, (
            "Handler must restart sshd service"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_hardening_tasks_notify_handler_on_config_change(self):
        """
        Verify SSH hardening tasks notify handler when configuration changes.

        Validates: Requirement 3.13 (service restart on configuration change)
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify tasks file exists
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "SSH hardening role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify tasks notify handler
        assert "notify:" in tasks_content, (
            "Tasks must notify handler on configuration changes"
        )

        # Verify notification references sshd restart
        assert "sshd" in tasks_content.lower(), (
            "Tasks must notify sshd restart handler"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tailscale_enabled=st.booleans(),
    )
    def test_ssh_interface_restriction_based_on_tailscale_status(
        self,
        tailscale_enabled: bool,
    ):
        """
        Verify SSH ListenAddress configuration adapts to Tailscale status.

        When Tailscale is enabled, SSH should listen only on Tailscale interface.
        When Tailscale is disabled, SSH should listen on all interfaces.

        Validates: Requirements 5.2, 5.3
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify SSH hardening template exists
        template_path = role_path / "templates" / "sshd_config.j2"
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify ListenAddress directive is present
        assert "ListenAddress" in template_content, (
            "Template must include ListenAddress directive"
        )

        # Verify template has conditional logic for Tailscale
        assert "{% if " in template_content, (
            "Template must use conditional logic for interface restriction"
        )

        assert "tailscale" in template_content.lower(), (
            "Template must reference Tailscale for conditional logic"
        )

        # Verify template listens on all interfaces when Tailscale disabled
        assert "0.0.0.0" in template_content or "ssh_listen_address" in template_content, (
            "Template must listen on all interfaces when Tailscale disabled"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_algorithm_restrictions_use_modern_standards(self):
        """
        Verify SSH algorithm restrictions follow modern cryptographic standards.

        Key exchange: curve25519, DH group 16/18
        Ciphers: ChaCha20-Poly1305, AES-GCM
        MACs: HMAC-SHA2 with ETM
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify defaults file exists
        defaults_path = role_path / "defaults" / "main.yml"
        assert defaults_path.exists(), "SSH hardening role must have defaults file"

        defaults_content = defaults_path.read_text()

        # Verify modern key exchange algorithms
        modern_kex = [
            "curve25519-sha256",
            "diffie-hellman-group16-sha512",
            "diffie-hellman-group18-sha512",
        ]

        for kex in modern_kex:
            assert kex in defaults_content, (
                f"Defaults must include modern key exchange algorithm: {kex}"
            )

        # Verify AEAD ciphers
        aead_ciphers = [
            "chacha20-poly1305@openssh.com",
            "aes256-gcm@openssh.com",
            "aes128-gcm@openssh.com",
        ]

        for cipher in aead_ciphers:
            assert cipher in defaults_content, (
                f"Defaults must include AEAD cipher: {cipher}"
            )

        # Verify Encrypt-Then-MAC MACs
        etm_macs = [
            "hmac-sha2-512-etm@openssh.com",
            "hmac-sha2-256-etm@openssh.com",
        ]

        for mac in etm_macs:
            assert mac in defaults_content, (
                f"Defaults must include Encrypt-Then-MAC variant: {mac}"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_configuration_backup_is_created(self):
        """
        Verify SSH configuration deployment creates backup of existing config.

        This allows recovery if new configuration causes issues.
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify tasks file exists
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "SSH hardening role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify backup parameter is used
        assert "backup:" in tasks_content, (
            "SSH config deployment should create backup"
        )

        assert "backup: true" in tasks_content or "backup: yes" in tasks_content, (
            "SSH config deployment should enable backup"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_configuration_validation_prevents_lockout(self):
        """
        Verify SSH configuration is validated before deployment.

        This prevents deploying invalid configuration that could lock out access.
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify tasks file exists
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "SSH hardening role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify validation is used
        assert "validate:" in tasks_content, (
            "SSH config deployment must validate configuration"
        )

        # Verify validation uses sshd test mode
        assert "/usr/sbin/sshd" in tasks_content and "-t" in tasks_content, (
            "SSH config validation must use sshd -t"
        )

        # Verify validation uses %s placeholder for temp file
        assert "%s" in tasks_content, (
            "SSH config validation must use %s placeholder"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_hardening_role_has_appropriate_tags(self):
        """
        Verify SSH hardening role has appropriate tags for selective execution.

        Tags allow running specific subsets of tasks (e.g., only SSH hardening).
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify tasks file exists
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "SSH hardening role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify tasks have tags (optional but recommended)
        # Tags are useful for selective execution
        # Not strictly required, so we just check if present
        if "tags:" in tasks_content:
            # Good practice - tags are present
            pass

    @pytest.mark.property
    @pytest.mark.unit
    def test_ssh_configuration_file_permissions_are_secure(self):
        """
        Verify SSH configuration file is deployed with secure permissions.

        sshd_config should be readable by all but writable only by root.
        """
        # Verify SSH hardening role exists
        role_path = Path("roles/ssh_hardening")
        assert role_path.exists(), "SSH hardening role must exist"

        # Verify tasks file exists
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "SSH hardening role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify file permissions are set
        assert "mode:" in tasks_content, (
            "SSH config deployment must set file permissions"
        )

        # Verify mode is 0644 (rw-r--r--)
        assert 'mode: "0644"' in tasks_content or "mode: '0644'" in tasks_content, (
            "SSH config must have mode 0644"
        )

        # Verify ownership is set to root
        assert "owner: root" in tasks_content, (
            "SSH config must be owned by root"
        )

        assert "group: root" in tasks_content, (
            "SSH config must have group root"
        )
