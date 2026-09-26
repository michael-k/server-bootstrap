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
        Fail2ban Installation and Configuration

        Checks the fail2ban role's package install, configuration directory, jail
        template and its destination, the restart handler it notifies, and the
        service's enabled and started state; the defaults for the counters,
        backend, ban action and SSH jail switch; that the jail template contains a
        `[sshd]` header, the switch, `filter = sshd`, the counters, the port and
        the protocol anywhere in the file; and that its `[DEFAULT]` section renders
        the ban action, counters and backend.

        Validates: F2B-1, F2B-2, F2B-3, F2B-4, F2B-5, F2B-7, F2B-9, F2B-10,
        F2B-11, F2B-13, F2B-14, F2B-15
        """
        # This property test reads the role's files and asserts on their text:
        # 1. fail2ban is installed from the distribution's repository (F2B-1)
        # 2. the configuration directory and the jail file are managed
        #    (F2B-2, F2B-3)
        # 3. the SSH jail exists and names the SSH port (F2B-4, F2B-5)
        # 4. the counters and the ban duration are configurable
        #    (F2B-9, F2B-10)
        # 5. bans go in through nftables (F2B-11)
        # 6. the service is enabled at boot and started (F2B-13, F2B-14)
        # 7. a jail configuration change notifies the restart handler (F2B-15)
        #
        # Every assertion below is a substring check against a file's text.
        # None of them starts fail2ban or observes a ban.

        # Read the fail2ban role tasks
        tasks_path = Path("roles/fail2ban/tasks/main.yml")
        assert tasks_path.exists(), "Fail2ban tasks file must exist"

        tasks_content = tasks_path.read_text()

        # F2B-1: fail2ban is installed from the distribution's repository
        assert "ansible.builtin.apt:" in tasks_content, (
            "Fail2ban must be installed using ansible.builtin.apt module"
        )
        assert "name: fail2ban" in tasks_content, (
            "Fail2ban package must be installed (F2B-1)"
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

        # F2B-13: fail2ban service is enabled at boot
        assert "ansible.builtin.systemd:" in tasks_content, (
            "Fail2ban service must be managed using systemd module"
        )
        assert "name: fail2ban" in tasks_content, (
            "Service name must be fail2ban"
        )
        assert "enabled: true" in tasks_content or "enabled: yes" in tasks_content, (
            "Fail2ban service must be enabled to start on boot (F2B-13)"
        )

        # F2B-14: fail2ban service is started
        assert "state: started" in tasks_content, (
            "Fail2ban service must be started (F2B-14)"
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

        # F2B-9: max retry and find time are configurable
        assert "fail2ban_max_retry:" in defaults_content, (
            "fail2ban_max_retry must be defined in defaults (F2B-9)"
        )
        assert "fail2ban_find_time:" in defaults_content, (
            "fail2ban_find_time must be defined in defaults (F2B-9)"
        )

        # F2B-10: ban time is configurable
        assert "fail2ban_ban_time:" in defaults_content, (
            "fail2ban_ban_time must be defined in defaults (F2B-10)"
        )

        # Verify SSH jail is configurable
        assert "fail2ban_ssh_enabled:" in defaults_content, (
            "SSH jail enablement must be configurable"
        )

        # Verify backend is configurable
        assert "fail2ban_ssh_backend:" in defaults_content, (
            "fail2ban backend must be configurable"
        )

        # F2B-11: the nftables ban action is configured
        assert "fail2ban_banaction:" in defaults_content, (
            "fail2ban banaction must be defined for NFTables integration (F2B-11)"
        )

        # Verify default banaction uses nftables
        assert "nftables" in defaults_content.lower(), (
            "Default banaction must use nftables for firewall integration (F2B-11)"
        )

        # Read the jail configuration template
        template_path = Path("roles/fail2ban/templates/jail.local.j2")
        assert template_path.exists(), "Jail configuration template must exist"

        template_content = template_path.read_text()

        # F2B-4: the SSH jail exists and is gated on fail2ban_ssh_enabled
        assert "[sshd]" in template_content, (
            "SSH jail must be configured to monitor SSHD (F2B-4)"
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

        # F2B-9: max retry is rendered from the variable
        assert "maxretry = {{ fail2ban_max_retry }}" in template_content, (
            "SSH jail must use fail2ban_max_retry variable (F2B-9)"
        )

        # F2B-10: ban time is rendered from the variable
        assert "bantime = {{ fail2ban_ban_time }}" in template_content, (
            "SSH jail must use fail2ban_ban_time variable (F2B-10)"
        )

        # F2B-9: find time is rendered from the variable
        assert "findtime = {{ fail2ban_find_time }}" in template_content, (
            "SSH jail must use fail2ban_find_time variable (F2B-9)"
        )

        # F2B-11: the ban action is rendered from the variable
        assert "banaction = {{ fail2ban_banaction }}" in template_content, (
            "Jail configuration must use fail2ban_banaction variable (F2B-11)"
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

        # What this establishes: the role's files contain the strings above
        # for every generated combination of configuration values. What it
        # does not establish: that any of it takes effect. The values the
        # strategies generate are never rendered into the template and never
        # reach fail2ban, so this property holds identically for a role that
        # is deployed and one that is not.


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
        Fail2ban Journald Backend Configuration

        Checks that `fail2ban_ssh_backend` defaults to `systemd`, that the jail
        template renders `backend = {{ fail2ban_ssh_backend }}`, and that the
        `[sshd]` section mentions journald or systemd.

        Validates: F2B-7

        The template assertion is not scoped to the [DEFAULT] section. The test
        does not establish what backend the [sshd] jail is created with: the
        distribution's jail.d/defaults-debian.conf sets backend at jail level,
        which outranks [DEFAULT]. See specs/fail2ban/design.md.
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

        # Check that the [sshd] section mentions journald or systemd
        sshd_section_start = template_content.find("[sshd]")
        if sshd_section_start != -1:
            # Find the next section or end of file
            next_section = template_content.find("\n[", sshd_section_start + 1)
            if next_section == -1:
                sshd_section = template_content[sshd_section_start:]
            else:
                sshd_section = template_content[sshd_section_start:next_section]

            assert "journald" in sshd_section.lower() or "systemd" in sshd_section.lower(), (
                "SSH jail section should document journald/systemd backend usage"
            )


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
        Fail2ban NFTables Integration

        Checks that `fail2ban_banaction` defaults to `nftables-multiport`, and that
        the jail template's `[DEFAULT]` section renders both `banaction` and
        `banaction_allports` from it.

        Validates: F2B-11

        Asserts on the rendered text only. Nothing here observes the table the
        ban action builds, nor that a ban is ever installed. The
        banaction_allports assertion's failure message says "for all-port
        blocking", which the value it asserts does not produce - Debian's own
        default for that setting is nftables[type=allports] and this project
        replaces it with a multiport action. See specs/fail2ban/design.md.
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

        # Verify banaction_allports is rendered from the same variable
        assert "banaction_allports = {{ fail2ban_banaction }}" in default_section, (
            "DEFAULT section should configure banaction_allports for all-port blocking"
        )


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
        Fail2ban Configuration Consistency

        Checks that the jail template renders `maxretry`, `findtime` and `bantime`
        from their variables in both the `[DEFAULT]` section and the `[sshd]`
        section, and that the template mentions inheritance.

        Validates: F2B-9, F2B-10, F2B-12

        The jail-level check is presence only: it does not establish what the
        restatement buys, which is that a jail-level setting outranks [DEFAULT]
        from every file fail2ban reads. The inheritance assertion is a substring
        check on the word, so it passes whether the surrounding sentence is true
        or false.
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
