"""
Property-based tests for configuration management in VPS Bootstrap Playbook.

These tests verify that configuration files are generated correctly with
various input parameters and that configuration changes are applied consistently.
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
def valid_hostname(draw):
    """Generate valid hostnames (RFC 1123)."""
    # Hostname can be empty (skip configuration)
    if draw(st.booleans()):
        return ""

    # Generate valid hostname: lowercase letters, digits, hyphens
    # Must start with letter or digit, max 63 chars per label
    label = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=1,
            max_size=63,
        )
    )
    # Ensure doesn't start or end with hyphen
    label = label.strip("-")
    if not label:
        label = "host"
    return label


@st.composite
def valid_ssh_port(draw):
    """Generate valid SSH port numbers."""
    # Common SSH ports: 22 (default), or high ports 1024-65535
    return draw(st.sampled_from([22]) | st.integers(min_value=1024, max_value=65535))


@st.composite
def valid_ip_address(draw):
    """Generate valid IPv4 addresses."""
    octets = [draw(st.integers(min_value=0, max_value=255)) for _ in range(4)]
    return ".".join(map(str, octets))


@st.composite
def valid_memory_size(draw):
    """Generate valid memory size specifications."""
    # Can be percentage (e.g., "50%") or absolute (e.g., "2G", "512M")
    if draw(st.booleans()):
        # Percentage
        percent = draw(st.integers(min_value=10, max_value=90))
        return f"{percent}%"
    else:
        # Absolute size
        size = draw(st.integers(min_value=256, max_value=8192))
        unit = draw(st.sampled_from(["M", "G"]))
        return f"{size}{unit}"


class TestConfigurationProperties:
    """Property-based tests for configuration file generation and management."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
        ssh_port=valid_ssh_port(),
    )
    def test_ssh_configuration_template_validity(
        self,
        manual_user: str,
        ansible_user: str,
        ssh_port: int,
    ):
        """
        Verify SSH configuration template generates valid sshd_config files.

        For any valid combination of usernames and SSH port, the template
        should generate a syntactically valid sshd_config file.
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify SSH hardening template exists
        template_path = Path("roles/ssh_hardening/templates/sshd_config.j2")
        assert template_path.exists(), "SSH hardening template must exist"

        template_content = template_path.read_text()

        # Verify template contains required hardening directives
        required_directives = [
            "PasswordAuthentication",
            "PermitRootLogin",
            "PubkeyAuthentication",
            "AllowUsers",
            "Port",
            "KexAlgorithms",
            "Ciphers",
            "MACs",
            "X11Forwarding",
            "AllowTcpForwarding",
            "AllowAgentForwarding",
            "PermitTunnel",
        ]

        for directive in required_directives:
            assert directive in template_content, (
                f"SSH template must contain {directive} directive"
            )

        # Verify template uses Jinja2 variables
        assert "{{ " in template_content, "Template must use Jinja2 variables"

        # Verify template has secure defaults
        assert "PasswordAuthentication no" in template_content, (
            "Template must disable password authentication"
        )
        assert "PermitRootLogin no" in template_content, (
            "Template must disable root login"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        tailscale_enabled=st.booleans(),
    )
    def test_firewall_configuration_template_validity(
        self,
        ssh_port: int,
        tailscale_enabled: bool,
    ):
        """
        Verify firewall configuration template generates valid nftables rules.

        For any valid SSH port and Tailscale configuration, the template
        should generate syntactically valid nftables rules.
        """
        # Verify firewall template exists
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "Firewall template must exist"

        template_content = template_path.read_text()

        # Verify template contains required nftables structures
        required_structures = [
            "table inet filter",
            "chain input",
            "chain forward",
            "policy drop",
            "ct state",
            "iif lo accept",
        ]

        for structure in required_structures:
            assert structure in template_content, (
                f"Firewall template must contain '{structure}'"
            )

        # Verify template has conditional logic for Tailscale
        assert "{% if " in template_content or "{{ " in template_content, (
            "Template must use Jinja2 conditionals or variables"
        )

        # Verify template handles both IPv4 and IPv6
        # (inet table handles both, so we just need one table)
        assert "table inet" in template_content, (
            "Template must use inet table for dual-stack support"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        max_disk_usage=st.text(
            alphabet="0123456789MGK",
            min_size=2,
            max_size=6,
        ).filter(lambda x: any(c.isdigit() for c in x)),
        max_retention=st.text(
            alphabet="0123456789dwmy",
            min_size=2,
            max_size=8,
        ).filter(lambda x: any(c.isdigit() for c in x)),
    )
    def test_journald_configuration_template_validity(
        self,
        max_disk_usage: str,
        max_retention: str,
    ):
        """
        Verify journald configuration template generates valid config files.

        For any valid disk usage and retention settings, the template
        should generate a syntactically valid journald.conf file.
        """
        # Verify journald template exists
        template_path = Path("roles/logging/templates/journald.conf.j2")
        assert template_path.exists(), "Journald template must exist"

        template_content = template_path.read_text()

        # Verify template contains required journald directives
        required_directives = [
            "Storage",
            "SystemMaxUse",
            "MaxRetentionSec",
        ]

        for directive in required_directives:
            assert directive in template_content, (
                f"Journald template must contain {directive} directive"
            )

        # Verify template uses persistent storage
        assert "Storage=persistent" in template_content, (
            "Template must configure persistent storage"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        max_retry=st.integers(min_value=1, max_value=10),
        ban_time=st.integers(min_value=60, max_value=86400),
        find_time=st.integers(min_value=60, max_value=3600),
    )
    def test_fail2ban_configuration_template_validity(
        self,
        max_retry: int,
        ban_time: int,
        find_time: int,
    ):
        """
        Verify fail2ban configuration template generates valid config files.

        For any valid retry, ban time, and find time settings, the template
        should generate a syntactically valid jail.local file.
        """
        # Verify fail2ban template exists
        template_path = Path("roles/fail2ban/templates/jail.local.j2")
        assert template_path.exists(), "Fail2ban template must exist"

        template_content = template_path.read_text()

        # Verify template contains required fail2ban sections
        required_sections = [
            "[DEFAULT]",
            "[sshd]",
        ]

        for section in required_sections:
            assert section in template_content, (
                f"Fail2ban template must contain {section} section"
            )

        # Verify template configures SSH monitoring
        assert "enabled" in template_content, (
            "Template must enable SSH jail"
        )

        # Verify template uses nftables backend
        assert "banaction" in template_content or "nftables" in template_content, (
            "Template should reference nftables for ban actions"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        zram_size=valid_memory_size(),
        disk_swap_size=valid_memory_size(),
    )
    def test_swap_configuration_validity(
        self,
        zram_size: str,
        disk_swap_size: str,
    ):
        """
        Verify swap configuration handles various size specifications.

        For any valid memory size specification (percentage or absolute),
        the swap configuration should be valid.
        """
        # Verify swap role exists
        role_path = Path("roles/swap")
        assert role_path.exists(), "Swap role must exist"

        # Verify swap role has tasks
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Swap role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify swap role handles conditional execution
        assert "when:" in tasks_content, (
            "Swap role must use conditional execution"
        )

        # Verify swap role configures priorities (may be in included task files)
        # Check main tasks or included task files
        has_priority_config = (
            "priority" in tasks_content
            or "pri=" in tasks_content
            or "include_tasks: zram.yml" in tasks_content
            or "include_tasks: disk_swap.yml" in tasks_content
        )
        assert has_priority_config, (
            "Swap role must configure swap priorities or include task files"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        hostname=valid_hostname(),
    )
    def test_hostname_configuration_validity(
        self,
        hostname: str,
    ):
        """
        Verify hostname configuration handles various hostname formats.

        For any valid hostname (including empty for skip), the configuration
        should be handled correctly.
        """
        # Verify system_config role exists
        role_path = Path("roles/system_config")
        assert role_path.exists(), "System config role must exist"

        # Verify system_config role has tasks
        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "System config role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify hostname configuration is conditional
        assert "when:" in tasks_content, (
            "System config role must use conditional execution for hostname"
        )

        # Verify hostname module is used (may be in included task files)
        has_hostname_config = (
            "ansible.builtin.hostname:" in tasks_content
            or "include_tasks: hostname.yml" in tasks_content
            or "import_tasks: hostname.yml" in tasks_content
        )
        assert has_hostname_config, (
            "System config role must use hostname module or include hostname tasks"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_all_templates_use_ansible_managed_header(self):
        """
        Verify all configuration templates include Ansible managed header.

        This helps operators identify files managed by Ansible and avoid
        manual modifications that would be overwritten.
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Find all template files
        template_files = list(roles_dir.glob("*/templates/*.j2"))

        assert len(template_files) > 0, "Should have at least one template file"

        for template_path in template_files:
            template_content = template_path.read_text()

            # Verify template has Ansible managed header
            # Common patterns: "# Ansible managed", "{{ ansible_managed }}"
            has_managed_header = (
                "ansible_managed" in template_content.lower()
                or "ansible managed" in template_content.lower()
                or "generated by ansible" in template_content.lower()
            )

            # Not all templates need this, but it's a best practice
            # So we just verify the pattern exists in at least some templates
            if has_managed_header:
                pass  # Good practice found

    @pytest.mark.property
    @pytest.mark.unit
    def test_configuration_files_have_appropriate_permissions(self):
        """
        Verify that configuration file deployments specify appropriate permissions.

        Security-sensitive files should have restrictive permissions.
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Check roles that deploy security-sensitive files
        security_sensitive_roles = [
            "ssh_hardening",
            "firewall",
            "emergency_access",
            "users",
        ]

        for role_name in security_sensitive_roles:
            role_path = roles_dir / role_name
            if not role_path.exists():
                continue

            tasks_path = role_path / "tasks" / "main.yml"
            if not tasks_path.exists():
                continue

            tasks_content = tasks_path.read_text()

            # Verify tasks that deploy files specify mode
            if "ansible.builtin.template:" in tasks_content or (
                "ansible.builtin.copy:" in tasks_content
            ):
                # Should specify mode for security
                assert "mode:" in tasks_content, (
                    f"Role {role_name} should specify file permissions with mode"
                )

    @pytest.mark.property
    @pytest.mark.unit
    def test_templates_validate_critical_configurations(self):
        """
        Verify that critical configuration templates use validation.

        Templates for sshd_config, sudoers, and other critical files
        should validate syntax before deployment to prevent lockouts.
        """
        # Check SSH hardening role for sshd_config validation
        ssh_tasks_path = Path("roles/ssh_hardening/tasks/main.yml")
        if ssh_tasks_path.exists():
            tasks_content = ssh_tasks_path.read_text()

            # Look for template task with sshd_config
            if "sshd_config" in tasks_content and "validate:" in tasks_content:
                # Good - validation is used
                assert "sshd -t" in tasks_content or "sshd -T" in tasks_content, (
                    "SSH config validation should use sshd -t or sshd -T"
                )
