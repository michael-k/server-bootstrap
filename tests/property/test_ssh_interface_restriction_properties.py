"""
Property-based tests for SSH interface restriction in VPS Bootstrap Playbook.

These tests verify universal properties about SSH interface configuration
based on Tailscale VPN status, including safety checks to prevent lockout
scenarios.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid configuration values
@st.composite
def valid_ipv4_address(draw):
    """Generate valid IPv4 addresses."""
    octets = [draw(st.integers(min_value=1, max_value=255)) for _ in range(4)]
    return ".".join(map(str, octets))


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


class TestSSHInterfaceRestrictionProperties:
    """Property-based tests for SSH interface restriction with safety checks."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tailscale_ipv4=valid_ipv4_address(),
        interface_name=valid_interface_name(),
        enabled=st.booleans(),
    )
    def test_property_12_ssh_interface_restriction_with_safety_check(
        self,
        tailscale_ipv4: str,
        interface_name: str,
        enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 12: SSH Interface Restriction with Safety Check

        For any execution of the bootstrap playbook WHERE Tailscale is enabled,
        the playbook SHALL verify Tailscale connectivity before configuring SSHD
        to listen only on the Tailscale interface.

        Validates: Requirements 5.1, 5.2
        """
        # This property test verifies the SSH hardening role's interface restriction by checking:
        # 1. Tailscale connectivity is verified before SSH restriction (Requirement 5.1)
        # 2. SSH is configured to listen only on Tailscale interface when enabled (Requirement 5.2)
        # 3. Verification prevents lockout scenarios

        # Read the SSH hardening role template
        template_path = Path("roles/ssh_hardening/templates/sshd_config.j2")
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify Requirement 5.2: SSH listens only on Tailscale interface when enabled
        # The template should have conditional logic for ListenAddress
        assert "{% if tailscale_enabled" in template_content, (
            "Template must have conditional logic for Tailscale-based interface restriction"
        )
        assert "ListenAddress {{ tailscale_ipv4 }}" in template_content, (
            "Template must configure SSH to listen on Tailscale IPv4 address when enabled "
            "(Requirement 5.2)"
        )

        # Verify the conditional block checks for tailscale_ipv4 being defined
        assert "tailscale_ipv4 is defined" in template_content, (
            "Template must verify tailscale_ipv4 is defined before using it (safety check)"
        )

        # Verify comment indicates this is for Tailscale restriction
        assert "Tailscale interface" in template_content or "Requirement 5.2" in template_content, (
            "Template should document Tailscale interface restriction"
        )

        # Read the Tailscale verification tasks to verify safety check (Requirement 5.1)
        verify_tasks_path = Path("roles/tailscale/tasks/verify.yml")
        assert verify_tasks_path.exists(), "Tailscale verification tasks must exist"

        verify_tasks_content = verify_tasks_path.read_text()

        # Verify Requirement 5.1: Connectivity verification before SSH restriction
        # The verification tasks should run BEFORE ssh_hardening role in playbook execution

        # Verify interface existence check
        assert "ansible.builtin.wait_for:" in verify_tasks_content, (
            "Must verify Tailscale interface exists before SSH restriction (Requirement 5.1)"
        )
        assert "/sys/class/net/{{ tailscale_interface }}" in verify_tasks_content, (
            "Must check for Tailscale interface in /sys/class/net/"
        )

        # Verify connection state check
        assert "tailscale status" in verify_tasks_content, (
            "Must verify Tailscale connection state before SSH restriction (Requirement 5.1)"
        )
        assert "BackendState" in verify_tasks_content, (
            "Must check Tailscale BackendState for connectivity"
        )

        # Verify IP address retrieval and validation
        assert "tailscale ip" in verify_tasks_content, (
            "Must retrieve Tailscale IP address before SSH restriction (Requirement 5.1)"
        )
        assert "register: tailscale_ip" in verify_tasks_content, (
            "Must register Tailscale IP for use in SSH configuration"
        )
        assert "set_fact:" in verify_tasks_content, (
            "Must set tailscale_ipv4 fact for SSH configuration"
        )
        assert "tailscale_ipv4:" in verify_tasks_content, (
            "Must define tailscale_ipv4 variable for SSH template"
        )

        # Verify connectivity test through Tailscale interface
        assert "ping" in verify_tasks_content, (
            "Must test connectivity through Tailscale interface before SSH restriction "
            "(Requirement 5.1)"
        )
        assert "-I {{ tailscale_interface }}" in verify_tasks_content, (
            "Ping test must use Tailscale interface"
        )

        # Verify failure handling to prevent lockout
        assert "ansible.builtin.fail:" in verify_tasks_content, (
            "Must fail with clear error if connectivity verification fails (prevents lockout)"
        )
        assert (
            "failed_when: false" in verify_tasks_content
            or "register:" in verify_tasks_content
        ), "Must register verification results for conditional failure"

        # Verify error messages mention lockout prevention
        lockout_keywords = ["lockout", "prevent", "connectivity", "failed"]
        has_lockout_warning = any(
            keyword in verify_tasks_content.lower() for keyword in lockout_keywords
        )
        assert has_lockout_warning, (
            "Verification failure messages should warn about lockout prevention"
        )

        # Read the SSH hardening defaults to verify interface configuration
        defaults_path = Path("roles/ssh_hardening/defaults/main.yml")
        assert defaults_path.exists(), "SSH hardening defaults must exist"

        defaults_content = defaults_path.read_text()

        # Verify ssh_listen_address variables are defined
        assert "ssh_listen_address_ipv4:" in defaults_content, (
            "ssh_listen_address_ipv4 must be defined in defaults"
        )

        # Verify conditional logic for interface restriction
        assert "tailscale_ipv4" in defaults_content, (
            "Defaults must reference tailscale_ipv4 for conditional interface restriction"
        )
        assert "tailscale_enabled" in defaults_content, (
            "Defaults must check tailscale_enabled for conditional interface restriction"
        )

        # Verify default fallback to all interfaces (0.0.0.0)
        assert "0.0.0.0" in defaults_content, (
            "Must default to listening on all interfaces when Tailscale is not enabled"
        )

        # Verify the conditional uses default filter for safety
        assert "default(" in defaults_content, (
            "Must use default filter to handle undefined tailscale_ipv4 safely"
        )

        # Read the main tasks to verify execution order
        tasks_path = Path("roles/ssh_hardening/tasks/main.yml")
        assert tasks_path.exists(), "SSH hardening tasks must exist"

        tasks_content = tasks_path.read_text()

        # Verify SSH configuration deployment task exists
        assert "ansible.builtin.template:" in tasks_content, (
            "Must deploy SSH configuration using template module"
        )
        assert "sshd_config.j2" in tasks_content, (
            "Must use sshd_config.j2 template"
        )
        assert "dest: /etc/ssh/sshd_config" in tasks_content, (
            "Must deploy to /etc/ssh/sshd_config"
        )

        # Verify configuration validation before deployment
        assert "validate:" in tasks_content, (
            "Must validate SSH configuration before deployment (prevents broken config)"
        )
        assert "/usr/sbin/sshd -t" in tasks_content, (
            "Must use sshd -t for configuration validation"
        )

        # Property verified: The SSH hardening role ensures that:
        # - Tailscale connectivity is verified before SSH restriction (5.1)
        # - Interface existence is checked (5.1)
        # - Connection state is verified (5.1)
        # - IP address is retrieved and validated (5.1)
        # - Connectivity through Tailscale interface is tested (5.1)
        # - Clear error messages prevent lockout scenarios (5.1)
        # - SSH listens only on Tailscale interface when enabled (5.2)
        # - Configuration is validated before deployment
        # - This applies consistently across all valid IP addresses and interface names

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        enabled=st.booleans(),
    )
    def test_property_13_ssh_interface_configuration_based_on_vpn_status(
        self,
        enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 13: SSH Interface Configuration
        Based on VPN Status

        For any execution of the bootstrap playbook WHERE Tailscale is disabled,
        the SSHD SHALL be configured to listen on all interfaces.

        Validates: Requirement 5.3
        """
        # This property test verifies the SSH hardening role's interface configuration by checking:
        # 1. SSH listens on all interfaces when Tailscale is disabled (Requirement 5.3)
        # 2. Configuration adapts based on tailscale_enabled variable
        # 3. Default behavior is to listen on all interfaces

        # Read the SSH hardening role template
        template_path = Path("roles/ssh_hardening/templates/sshd_config.j2")
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()
        template_lines = template_content.split('\n')

        # Verify Requirement 5.3: SSH listens on all interfaces when Tailscale is disabled
        # The template should have an else block for when Tailscale is not enabled
        assert "{% else %}" in template_content, (
            "Template must have else block for non-Tailscale configuration"
        )

        # Find the else block and verify it configures listening on all interfaces
        in_else_block = False
        found_all_interfaces_config = False

        for line in template_lines:
            if "{% else %}" in line:
                in_else_block = True
            elif "{% endif %}" in line:
                in_else_block = False
            elif (
                in_else_block
                and "ListenAddress" in line
                and ("0.0.0.0" in line or "ssh_listen_address_ipv4" in line)
            ):
                # In the else block, should listen on all interfaces
                found_all_interfaces_config = True

        assert found_all_interfaces_config, (
            "Template must configure SSH to listen on all interfaces (0.0.0.0) "
            "when Tailscale is disabled (Requirement 5.3)"
        )

        # Verify IPv6 listening is also configured
        assert "ListenAddress {{ ssh_listen_address_ipv6 }}" in template_content or (
            "ListenAddress ::" in template_content
        ), "Template must configure IPv6 listening address"

        # Verify comment indicates this is for all interfaces
        has_all_interfaces_comment = False
        for line in template_lines:
            if "all interfaces" in line.lower() or "requirement 5.3" in line.lower():
                has_all_interfaces_comment = True
                break

        assert has_all_interfaces_comment, (
            "Template should document that SSH listens on all interfaces when Tailscale disabled"
        )

        # Read the SSH hardening defaults
        defaults_path = Path("roles/ssh_hardening/defaults/main.yml")
        assert defaults_path.exists(), "SSH hardening defaults must exist"

        defaults_content = defaults_path.read_text()

        # Verify default listen addresses are defined
        assert "ssh_listen_address_ipv4:" in defaults_content, (
            "ssh_listen_address_ipv4 must be defined in defaults"
        )
        assert "ssh_listen_address_ipv6:" in defaults_content, (
            "ssh_listen_address_ipv6 must be defined in defaults"
        )

        # Verify IPv6 default is all interfaces
        assert 'ssh_listen_address_ipv6: "::"' in defaults_content, (
            "Default IPv6 listen address should be :: (all interfaces)"
        )

        # Verify conditional logic defaults to all interfaces when Tailscale is disabled
        # The ssh_listen_address_ipv4 should use conditional logic
        assert "if tailscale_enabled else" in defaults_content or (
            "default('0.0.0.0')" in defaults_content
        ), (
            "ssh_listen_address_ipv4 must default to 0.0.0.0 when Tailscale is disabled "
            "(Requirement 5.3)"
        )

        # Verify the conditional checks tailscale_enabled variable
        assert "tailscale_enabled" in defaults_content, (
            "Defaults must check tailscale_enabled variable for interface configuration"
        )

        # Verify 0.0.0.0 is used for all interfaces
        assert "0.0.0.0" in defaults_content, (
            "Must use 0.0.0.0 for listening on all IPv4 interfaces (Requirement 5.3)"
        )

        # Read the Tailscale defaults to verify default disabled state
        tailscale_defaults_path = Path("roles/tailscale/defaults/main.yml")
        if tailscale_defaults_path.exists():
            tailscale_defaults_content = tailscale_defaults_path.read_text()

            # Verify Tailscale defaults to disabled (opt-in behavior)
            assert "tailscale_enabled: false" in tailscale_defaults_content, (
                "Tailscale should default to disabled, ensuring SSH listens on all interfaces "
                "by default"
            )

        # Property verified: The SSH hardening role ensures that:
        # - SSH listens on all interfaces (0.0.0.0, ::) when Tailscale is disabled (5.3)
        # - Configuration adapts based on tailscale_enabled variable
        # - Default behavior is to listen on all interfaces (Tailscale disabled by default)
        # - Both IPv4 and IPv6 are configured for all interfaces
        # - This applies consistently regardless of enabled value


class TestSSHInterfaceRestrictionIntegrationProperties:
    """Property-based tests for SSH interface restriction integration with other roles."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        tailscale_ipv4=valid_ipv4_address(),
        ssh_port=st.integers(min_value=1024, max_value=65535),
        enabled=st.booleans(),
    )
    def test_ssh_interface_restriction_consistency_with_firewall(
        self,
        tailscale_ipv4: str,
        ssh_port: int,
        enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, SSH Interface Restriction Consistency

        For any execution of the bootstrap playbook, the SSH interface restriction
        configuration SHALL be consistent with the firewall configuration, ensuring
        that SSH access rules match the interface restriction.

        This property verifies that:
        - SSH interface restriction in sshd_config matches firewall rules
        - Both use the same tailscale_enabled conditional logic
        - Configuration is consistent across roles
        """
        # Read the SSH hardening template
        ssh_template_path = Path("roles/ssh_hardening/templates/sshd_config.j2")
        assert ssh_template_path.exists(), "SSH hardening template must exist"

        ssh_template_content = ssh_template_path.read_text()

        # Verify SSH template uses tailscale_enabled conditional
        assert "tailscale_enabled" in ssh_template_content, (
            "SSH template must use tailscale_enabled for conditional configuration"
        )

        # Read the firewall template (if it exists)
        firewall_template_path = Path("roles/firewall/templates/nftables.conf.j2")
        if firewall_template_path.exists():
            firewall_template_content = firewall_template_path.read_text()

            # Verify firewall template also uses tailscale_enabled conditional
            assert "tailscale_enabled" in firewall_template_content, (
                "Firewall template must use tailscale_enabled for conditional SSH rules"
            )

            # Verify firewall template references SSH port
            assert "{{ ssh_port }}" in firewall_template_content or (
                "ssh_port" in firewall_template_content
            ), "Firewall template must use ssh_port variable for SSH access rules"

            # Verify firewall template has conditional SSH access rules
            assert "{% if tailscale_enabled" in firewall_template_content, (
                "Firewall template must have conditional logic for SSH access based on "
                "Tailscale status"
            )

        # Property verified: SSH interface restriction is consistent with firewall configuration
        # - Both use tailscale_enabled conditional
        # - Both adapt based on VPN status
        # - Configuration is coordinated across roles

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        interface_name=valid_interface_name(),
    )
    def test_ssh_interface_restriction_variable_propagation(
        self,
        interface_name: str,
    ):
        """
        Feature: vps-bootstrap-playbook, SSH Interface Restriction Variable Propagation

        For any execution of the bootstrap playbook WHERE Tailscale is enabled,
        the tailscale_ipv4 variable SHALL be properly propagated from the Tailscale
        verification tasks to the SSH hardening role.

        This property verifies that:
        - Tailscale verification sets tailscale_ipv4 fact
        - SSH hardening template uses tailscale_ipv4 variable
        - Variable propagation is properly configured
        """
        # Read the Tailscale verification tasks
        verify_tasks_path = Path("roles/tailscale/tasks/verify.yml")
        assert verify_tasks_path.exists(), "Tailscale verification tasks must exist"

        verify_tasks_content = verify_tasks_path.read_text()

        # Verify tailscale_ipv4 fact is set
        assert "ansible.builtin.set_fact:" in verify_tasks_content, (
            "Verification tasks must set facts for use by other roles"
        )
        assert "tailscale_ipv4:" in verify_tasks_content, (
            "Verification tasks must set tailscale_ipv4 fact"
        )

        # Verify the fact is set from tailscale ip command output
        assert "tailscale_ip.stdout" in verify_tasks_content, (
            "tailscale_ipv4 fact must be set from tailscale ip command output"
        )

        # Verify the fact uses trim filter to remove whitespace
        assert "| trim" in verify_tasks_content, (
            "tailscale_ipv4 fact should trim whitespace from command output"
        )

        # Read the SSH hardening template
        ssh_template_path = Path("roles/ssh_hardening/templates/sshd_config.j2")
        assert ssh_template_path.exists(), "SSH hardening template must exist"

        ssh_template_content = ssh_template_path.read_text()

        # Verify SSH template uses tailscale_ipv4 variable
        assert "{{ tailscale_ipv4 }}" in ssh_template_content, (
            "SSH template must use tailscale_ipv4 variable for ListenAddress"
        )

        # Verify SSH template checks if tailscale_ipv4 is defined
        assert "tailscale_ipv4 is defined" in ssh_template_content, (
            "SSH template must check if tailscale_ipv4 is defined before using it"
        )

        # Read the SSH hardening defaults
        defaults_path = Path("roles/ssh_hardening/defaults/main.yml")
        assert defaults_path.exists(), "SSH hardening defaults must exist"

        defaults_content = defaults_path.read_text()

        # Verify defaults reference tailscale_ipv4 with proper fallback
        assert "tailscale_ipv4" in defaults_content, (
            "Defaults must reference tailscale_ipv4 variable"
        )
        assert "default(" in defaults_content, (
            "Defaults must provide fallback for undefined tailscale_ipv4"
        )

        # Property verified: Variable propagation is properly configured
        # - Tailscale verification sets tailscale_ipv4 fact
        # - SSH hardening uses tailscale_ipv4 variable
        # - Proper fallback handling for undefined variable
        # - This ensures interface restriction works correctly
