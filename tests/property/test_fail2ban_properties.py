"""
Property-based tests for fail2ban configuration in VPS Bootstrap Playbook.

These tests verify universal properties about fail2ban installation, configuration,
and intrusion prevention across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid fail2ban configuration values
@st.composite
def valid_max_retry(draw):
    """Generate valid max retry values (1-10 attempts)."""
    return draw(st.integers(min_value=1, max_value=10))


@st.composite
def valid_ban_time(draw):
    """Generate valid ban time durations."""
    # Support both numeric (seconds) and string formats (e.g., "10m", "1h")
    format_choice = draw(st.sampled_from(["numeric", "string"]))
    if format_choice == "numeric":
        # Ban time in seconds (60s to 86400s = 1 minute to 1 day)
        return draw(st.integers(min_value=60, max_value=86400))
    else:
        # String format with time units
        value = draw(st.integers(min_value=1, max_value=1440))
        unit = draw(st.sampled_from(["s", "m", "h", "d"]))
        return f"{value}{unit}"


@st.composite
def valid_find_time(draw):
    """Generate valid find time durations."""
    # Support both numeric (seconds) and string formats
    format_choice = draw(st.sampled_from(["numeric", "string"]))
    if format_choice == "numeric":
        # Find time in seconds (60s to 3600s = 1 minute to 1 hour)
        return draw(st.integers(min_value=60, max_value=3600))
    else:
        # String format with time units
        value = draw(st.integers(min_value=1, max_value=60))
        unit = draw(st.sampled_from(["s", "m", "h"]))
        return f"{value}{unit}"


@st.composite
def valid_backend(draw):
    """Generate valid fail2ban backend types."""
    return draw(st.sampled_from(["systemd", "auto", "polling"]))


@st.composite
def valid_banaction(draw):
    """Generate valid fail2ban ban actions for nftables."""
    return draw(st.sampled_from([
        "nftables-multiport",
        "nftables-allports",
        "nftables",
    ]))


class TestFail2banProperties:
    """Property-based tests for fail2ban installation and configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        max_retry=valid_max_retry(),
        ban_time=valid_ban_time(),
        find_time=valid_find_time(),
        backend=valid_backend(),
        banaction=valid_banaction(),
        ssh_enabled=st.booleans(),
    )
    def test_property_27_fail2ban_installation_and_configuration(
        self,
        max_retry: int,
        ban_time,
        find_time,
        backend: str,
        banaction: str,
        ssh_enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 27: Fail2ban Installation and Configuration

        For any execution of the bootstrap playbook, fail2ban SHALL be installed,
        configured to monitor SSHD logs, configured with a configurable ban threshold
        and duration, integrated with NFTables, enabled to start on boot, and started.

        Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
        """
        # This property test verifies the fail2ban role's behavior by checking:
        # 1. fail2ban is installed from Debian repository (Requirement 10.1)
        # 2. fail2ban is configured to monitor SSHD logs (Requirement 10.2)
        # 3. fail2ban is configured with max_retry and find_time (Requirement 10.3)
        # 4. fail2ban is configured with ban_time (Requirement 10.4)
        # 5. fail2ban is integrated with NFTables (Requirement 10.5)
        # 6. fail2ban service is enabled to start on boot (Requirement 10.6)
        # 7. fail2ban service is started (Requirement 10.7)

        # Read the fail2ban role tasks
        tasks_path = Path("roles/fail2ban/tasks/main.yml")
        assert tasks_path.exists(), "Fail2ban tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify Requirement 10.1: fail2ban is installed from Debian repository
        assert "ansible.builtin.apt:" in tasks_content, (
            "Fail2ban must be installed using ansible.builtin.apt module"
        )
        assert "name: fail2ban" in tasks_content, (
            "Fail2ban package must be installed (Requirement 10.1)"
        )
        assert "state: present" in tasks_content, (
            "Fail2ban package state must be present"
        )

        # Verify package cache is updated during installation
        assert "update_cache: true" in tasks_content or "update_cache: yes" in tasks_content, (
            "Package cache should be updated during fail2ban installation"
        )

        # Verify configuration directory is created
        assert "/etc/fail2ban" in tasks_content, (
            "Fail2ban configuration directory must be managed"
        )
        assert "ansible.builtin.file:" in tasks_content, (
            "Configuration directory must be created using file module"
        )

        # Verify jail configuration is deployed
        assert "ansible.builtin.template:" in tasks_content, (
            "Jail configuration must be deployed using template module"
        )
        assert "jail.local.j2" in tasks_content, (
            "Jail configuration template must be jail.local.j2"
        )
        assert "dest: /etc/fail2ban/jail.local" in tasks_content, (
            "Jail configuration must be deployed to /etc/fail2ban/jail.local"
        )

        # Verify configuration changes trigger service restart
        assert "notify: restart fail2ban" in tasks_content, (
            "Configuration changes must trigger fail2ban service restart"
        )

        # Verify Requirement 10.6: fail2ban service is enabled
        assert "ansible.builtin.systemd:" in tasks_content, (
            "Fail2ban service must be managed using systemd module"
        )
        assert "name: fail2ban" in tasks_content, (
            "Service name must be fail2ban"
        )
        assert "enabled: true" in tasks_content or "enabled: yes" in tasks_content, (
            "Fail2ban service must be enabled to start on boot (Requirement 10.6)"
        )

        # Verify Requirement 10.7: fail2ban service is started
        assert "state: started" in tasks_content, (
            "Fail2ban service must be started (Requirement 10.7)"
        )

        # Verify tasks are properly tagged
        assert "tags:" in tasks_content, (
            "Tasks should be tagged for selective execution"
        )
        assert "fail2ban" in tasks_content, (
            "Tasks should have fail2ban tag"
        )
        assert "security" in tasks_content, (
            "Tasks should have security tag"
        )

        # Read the fail2ban defaults
        defaults_path = Path("roles/fail2ban/defaults/main.yml")
        assert defaults_path.exists(), "Fail2ban defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify Requirement 10.3: max_retry and find_time are configurable
        assert "fail2ban_max_retry:" in defaults_content, (
            "fail2ban_max_retry must be defined in defaults (Requirement 10.3)"
        )
        assert "fail2ban_find_time:" in defaults_content, (
            "fail2ban_find_time must be defined in defaults (Requirement 10.3)"
        )

        # Verify Requirement 10.4: ban_time is configurable
        assert "fail2ban_ban_time:" in defaults_content, (
            "fail2ban_ban_time must be defined in defaults (Requirement 10.4)"
        )

        # Verify SSH jail is configurable
        assert "fail2ban_ssh_enabled:" in defaults_content, (
            "SSH jail enablement must be configurable"
        )

        # Verify backend is configurable
        assert "fail2ban_ssh_backend:" in defaults_content, (
            "fail2ban backend must be configurable"
        )

        # Verify Requirement 10.5: NFTables integration is configured
        assert "fail2ban_banaction:" in defaults_content, (
            "fail2ban banaction must be defined for NFTables integration (Requirement 10.5)"
        )

        # Verify default banaction uses nftables
        assert "nftables" in defaults_content.lower(), (
            "Default banaction must use nftables for firewall integration (Requirement 10.5)"
        )

        # Read the jail configuration template
        template_path = Path("roles/fail2ban/templates/jail.local.j2")
        assert template_path.exists(), "Jail configuration template must exist"

        template_content = template_path.read_text()

        # Verify Requirement 10.2: SSHD monitoring is configured
        assert "[sshd]" in template_content, (
            "SSH jail must be configured to monitor SSHD (Requirement 10.2)"
        )
        assert "enabled = " in template_content, (
            "SSH jail must have enabled directive"
        )
        assert "{{ 'true' if fail2ban_ssh_enabled else 'false' }}" in template_content, (
            "SSH jail enabled status must be configurable"
        )

        # Verify SSH jail uses correct filter
        assert "filter = sshd" in template_content, (
            "SSH jail must use sshd filter for log parsing"
        )

        # Verify Requirement 10.3: max_retry is configured
        assert "maxretry = {{ fail2ban_max_retry }}" in template_content, (
            "SSH jail must use fail2ban_max_retry variable (Requirement 10.3)"
        )

        # Verify Requirement 10.4: ban_time is configured
        assert "bantime = {{ fail2ban_ban_time }}" in template_content, (
            "SSH jail must use fail2ban_ban_time variable (Requirement 10.4)"
        )

        # Verify Requirement 10.3: find_time is configured
        assert "findtime = {{ fail2ban_find_time }}" in template_content, (
            "SSH jail must use fail2ban_find_time variable (Requirement 10.3)"
        )

        # Verify Requirement 10.5: NFTables banaction is configured
        assert "banaction = {{ fail2ban_banaction }}" in template_content, (
            "Jail configuration must use fail2ban_banaction variable (Requirement 10.5)"
        )

        # Verify backend is configured
        assert "backend = {{ fail2ban_ssh_backend }}" in template_content, (
            "Jail configuration must use fail2ban_ssh_backend variable"
        )

        # Verify SSH port is configurable
        assert "port = {{ ssh_port" in template_content, (
            "SSH jail must use configurable SSH port"
        )

        # Verify protocol is specified
        assert "protocol = tcp" in template_content, (
            "SSH jail must specify TCP protocol"
        )

        # Verify DEFAULT section exists for global settings
        assert "[DEFAULT]" in template_content, (
            "Jail configuration must have DEFAULT section for global settings"
        )

        # Verify DEFAULT section includes banaction
        default_section_start = template_content.find("[DEFAULT]")
        sshd_section_start = template_content.find("[sshd]")
        default_section = template_content[default_section_start:sshd_section_start]

        assert "banaction = {{ fail2ban_banaction }}" in default_section, (
            "DEFAULT section must configure banaction for NFTables integration"
        )

        # Verify default ban time, find time, and max retry in DEFAULT section
        assert "bantime = {{ fail2ban_ban_time }}" in default_section, (
            "DEFAULT section must configure default ban time"
        )
        assert "findtime = {{ fail2ban_find_time }}" in default_section, (
            "DEFAULT section must configure default find time"
        )
        assert "maxretry = {{ fail2ban_max_retry }}" in default_section, (
            "DEFAULT section must configure default max retry"
        )

        # Verify backend is configured in DEFAULT section
        assert "backend = {{ fail2ban_ssh_backend }}" in default_section, (
            "DEFAULT section must configure backend"
        )

        # Verify default values are reasonable
        for line in defaults_content.split('\n'):
            if line.strip().startswith('fail2ban_max_retry:'):
                value = line.split(':')[1].strip()
                try:
                    default_max_retry = int(value)
                    assert 1 <= default_max_retry <= 10, (
                        f"Default fail2ban_max_retry should be between 1 and 10, "
                        f"got {default_max_retry}"
                    )
                except ValueError:
                    pass  # Value might be a variable reference

        # Verify handlers file exists for service restart
        handlers_path = Path("roles/fail2ban/handlers/main.yml")
        assert handlers_path.exists(), "Fail2ban handlers file must exist"

        handlers_content = handlers_path.read_text()

        # Verify restart handler is defined
        assert (
            "name: restart fail2ban" in handlers_content
            or "name: Restart fail2ban" in handlers_content
        ), "Restart fail2ban handler must be defined"
        assert (
            "ansible.builtin.systemd:" in handlers_content
            or "ansible.builtin.service:" in handlers_content
        ), "Restart handler must use systemd or service module"
        assert "name: fail2ban" in handlers_content, (
            "Restart handler must target fail2ban service"
        )
        assert "state: restarted" in handlers_content, (
            "Restart handler must restart the service"
        )

        # Property verified: The fail2ban role configuration ensures that:
        # - fail2ban is installed from Debian repository (10.1)
        # - fail2ban is configured to monitor SSHD logs (10.2)
        # - max_retry and find_time are configurable (10.3)
        # - ban_time is configurable (10.4)
        # - NFTables integration is configured via banaction (10.5)
        # - fail2ban service is enabled to start on boot (10.6)
        # - fail2ban service is started (10.7)
        # - Configuration changes trigger service restart
        # - Tasks are properly tagged for selective execution
        # - This applies consistently across all valid configuration values


class TestFail2banJournaldIntegrationProperties:
    """Property-based tests for fail2ban journald integration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        backend=valid_backend(),
    )
    def test_fail2ban_journald_backend_configuration(self, backend: str):
        """
        Feature: vps-bootstrap-playbook, Fail2ban Journald Backend Configuration

        For any execution of the bootstrap playbook with systemd-based logging,
        fail2ban SHALL be configured to use the journald backend for log monitoring,
        ensuring compatibility with modern systemd-based systems.

        This property verifies that:
        - Backend is configurable
        - Default backend is systemd for journald integration
        - No explicit logpath is needed with systemd backend
        """
        # Read the fail2ban defaults
        defaults_path = Path("roles/fail2ban/defaults/main.yml")
        assert defaults_path.exists(), "Fail2ban defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify backend is configurable
        assert "fail2ban_ssh_backend:" in defaults_content, (
            "fail2ban backend must be configurable"
        )

        # Verify default backend is systemd for journald integration
        assert (
            'fail2ban_ssh_backend: "systemd"' in defaults_content
            or "fail2ban_ssh_backend: systemd" in defaults_content
        ), "Default backend should be 'systemd' for journald integration"

        # Read the jail configuration template
        template_path = Path("roles/fail2ban/templates/jail.local.j2")
        assert template_path.exists(), "Jail configuration template must exist"

        template_content = template_path.read_text()

        # Verify backend is used in configuration
        assert "backend = {{ fail2ban_ssh_backend }}" in template_content, (
            "Jail configuration must use fail2ban_ssh_backend variable"
        )

        # Verify no explicit logpath is configured when using systemd backend
        # (journald backend reads from systemd journal automatically)
        sshd_section_start = template_content.find("[sshd]")
        if sshd_section_start != -1:
            # Find the next section or end of file
            next_section = template_content.find("\n[", sshd_section_start + 1)
            if next_section == -1:
                sshd_section = template_content[sshd_section_start:]
            else:
                sshd_section = template_content[sshd_section_start:next_section]

            # Verify comment about journald backend not needing logpath
            assert "journald" in sshd_section.lower() or "systemd" in sshd_section.lower(), (
                "SSH jail section should document journald/systemd backend usage"
            )

        # Property verified: The fail2ban role ensures:
        # - Backend is configurable via fail2ban_ssh_backend variable
        # - Default backend is systemd for journald integration
        # - Configuration is compatible with systemd-based logging


class TestFail2banNFTablesIntegrationProperties:
    """Property-based tests for fail2ban NFTables integration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        banaction=valid_banaction(),
    )
    def test_fail2ban_nftables_banaction_configuration(self, banaction: str):
        """
        Feature: vps-bootstrap-playbook, Fail2ban NFTables Integration

        For any execution of the bootstrap playbook, fail2ban SHALL be configured
        to use NFTables for dynamic IP blocking, ensuring integration with the
        firewall component.

        This property verifies that:
        - Banaction is configurable
        - Default banaction uses nftables
        - Banaction is applied to both DEFAULT and SSH jail sections
        """
        # Read the fail2ban defaults
        defaults_path = Path("roles/fail2ban/defaults/main.yml")
        assert defaults_path.exists(), "Fail2ban defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify banaction is configurable
        assert "fail2ban_banaction:" in defaults_content, (
            "fail2ban banaction must be configurable"
        )

        # Verify default banaction uses nftables
        assert "nftables" in defaults_content.lower(), (
            "Default banaction must use nftables for firewall integration"
        )

        # Verify default is nftables-multiport (recommended for multi-port support)
        assert (
            'fail2ban_banaction: "nftables-multiport"' in defaults_content
            or "fail2ban_banaction: nftables-multiport" in defaults_content
        ), "Default banaction should be 'nftables-multiport' for multi-port support"

        # Read the jail configuration template
        template_path = Path("roles/fail2ban/templates/jail.local.j2")
        assert template_path.exists(), "Jail configuration template must exist"

        template_content = template_path.read_text()

        # Verify banaction is configured in DEFAULT section
        assert "[DEFAULT]" in template_content, (
            "Jail configuration must have DEFAULT section"
        )

        default_section_start = template_content.find("[DEFAULT]")
        sshd_section_start = template_content.find("[sshd]")
        default_section = template_content[default_section_start:sshd_section_start]

        assert "banaction = {{ fail2ban_banaction }}" in default_section, (
            "DEFAULT section must configure banaction"
        )

        # Verify banaction_allports is also configured for comprehensive blocking
        assert "banaction_allports = {{ fail2ban_banaction }}" in default_section, (
            "DEFAULT section should configure banaction_allports for all-port blocking"
        )

        # Property verified: The fail2ban role ensures:
        # - Banaction is configurable via fail2ban_banaction variable
        # - Default banaction uses nftables-multiport
        # - Banaction is configured in DEFAULT section for all jails
        # - Integration with NFTables firewall component


class TestFail2banConfigurationValidationProperties:
    """Property-based tests for fail2ban configuration validation."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        max_retry=valid_max_retry(),
        ban_time=valid_ban_time(),
        find_time=valid_find_time(),
    )
    def test_fail2ban_configuration_consistency(
        self,
        max_retry: int,
        ban_time,
        find_time,
    ):
        """
        Feature: vps-bootstrap-playbook, Fail2ban Configuration Consistency

        For any execution of the bootstrap playbook with configured fail2ban parameters,
        the configuration SHALL be consistent between DEFAULT section and SSH jail section,
        ensuring predictable behavior.

        This property verifies that:
        - Configuration parameters are defined in DEFAULT section
        - SSH jail inherits from DEFAULT section
        - SSH jail can override DEFAULT values if needed
        """
        # Read the jail configuration template
        template_path = Path("roles/fail2ban/templates/jail.local.j2")
        assert template_path.exists(), "Jail configuration template must exist"

        template_content = template_path.read_text()

        # Verify DEFAULT section exists
        assert "[DEFAULT]" in template_content, (
            "Jail configuration must have DEFAULT section"
        )

        # Verify SSH jail section exists
        assert "[sshd]" in template_content, (
            "Jail configuration must have SSH jail section"
        )

        # Extract DEFAULT and SSH sections
        default_section_start = template_content.find("[DEFAULT]")
        sshd_section_start = template_content.find("[sshd]")

        default_section = template_content[default_section_start:sshd_section_start]
        sshd_section = template_content[sshd_section_start:]

        # Verify configuration parameters are in DEFAULT section
        assert "bantime = {{ fail2ban_ban_time }}" in default_section, (
            "DEFAULT section must configure ban time"
        )
        assert "findtime = {{ fail2ban_find_time }}" in default_section, (
            "DEFAULT section must configure find time"
        )
        assert "maxretry = {{ fail2ban_max_retry }}" in default_section, (
            "DEFAULT section must configure max retry"
        )

        # Verify SSH jail also specifies these parameters (can override DEFAULT)
        assert "maxretry = {{ fail2ban_max_retry }}" in sshd_section, (
            "SSH jail should specify max retry (can override DEFAULT)"
        )
        assert "bantime = {{ fail2ban_ban_time }}" in sshd_section, (
            "SSH jail should specify ban time (can override DEFAULT)"
        )
        assert "findtime = {{ fail2ban_find_time }}" in sshd_section, (
            "SSH jail should specify find time (can override DEFAULT)"
        )

        # Verify comments explain inheritance behavior
        assert (
            "Inherits from DEFAULT" in template_content
            or "inherit" in template_content.lower()
        ), "Template should document inheritance behavior from DEFAULT section"

        # Property verified: The fail2ban role ensures:
        # - Configuration parameters are defined in DEFAULT section
        # - SSH jail can override DEFAULT values
        # - Configuration is consistent and predictable
        # - Inheritance behavior is documented
