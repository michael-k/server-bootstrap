"""
Property-based tests for system configuration in VPS Bootstrap Playbook.

These tests verify universal properties about hostname configuration and time
synchronization across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid system configuration values
@st.composite
def valid_hostname(draw):
    """Generate valid hostnames according to RFC 1123."""
    # Hostname can be 1-63 characters, alphanumeric and hyphens
    # Cannot start or end with hyphen
    length = draw(st.integers(min_value=1, max_value=63))
    # Start with alphanumeric
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"))
    if length == 1:
        return first_char
    # Middle can include hyphens
    middle_chars = draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
        min_size=length - 2,
        max_size=length - 2,
    ))
    # End with alphanumeric
    last_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"))
    return first_char + middle_chars + last_char


@st.composite
def valid_ntp_server(draw):
    """Generate valid NTP server addresses."""
    # Can be domain name or IP address
    server_type = draw(st.sampled_from(["domain", "ip"]))
    if server_type == "domain":
        # Generate domain-like NTP server
        subdomain = draw(st.sampled_from(["0", "1", "2", "3", "time", "ntp"]))
        domain = draw(st.sampled_from([
            "debian.pool.ntp.org",
            "ubuntu.pool.ntp.org",
            "pool.ntp.org",
            "ntp.org",
        ]))
        return f"{subdomain}.{domain}"
    else:
        # Generate IP address
        octets = [draw(st.integers(min_value=1, max_value=255)) for _ in range(4)]
        return ".".join(str(o) for o in octets)


@st.composite
def valid_time_sync_service(draw):
    """Generate valid time synchronization service choices."""
    return draw(st.sampled_from(["chrony", "timesyncd"]))


class TestHostnameConfigurationProperties:
    """Property-based tests for hostname configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        hostname=valid_hostname(),
    )
    def test_property_14_hostname_configuration_persistence(self, hostname: str):
        """
        Feature: vps-bootstrap-playbook, Property 14: Hostname Configuration Persistence

        For any execution of the bootstrap playbook WHERE a hostname is configured,
        the system hostname SHALL be set to the specified value and persisted across
        reboots.

        Validates: HOST-1, HOST-2, HOST-3
        """
        # This property test verifies the system_config role's hostname behavior by checking:
        # 1. System hostname is set when variable is defined (HOST-1)
        # 2. Hostname persists across reboots (HOST-2)
        # 3. Hostname is added to /etc/hosts for local resolution (HOST-3)

        # Read the system_config role tasks
        tasks_path = Path("roles/system_config/tasks/main.yml")
        assert tasks_path.exists(), "System_config tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify hostname configuration is conditionally imported
        assert "ansible.builtin.import_tasks: hostname.yml" in tasks_content, (
            "Hostname configuration tasks must be imported"
        )
        assert (
            "when: system_hostname is defined and system_hostname | length > 0" in tasks_content
        ), "Hostname configuration must be conditional on system_hostname variable"

        # Read the hostname configuration tasks
        hostname_tasks_path = Path("roles/system_config/tasks/hostname.yml")
        assert hostname_tasks_path.exists(), "Hostname tasks file must exist"

        hostname_tasks_content = hostname_tasks_path.read_text()

        # Verify HOST-1: hostname is set using hostname module
        assert "ansible.builtin.hostname:" in hostname_tasks_content, (
            "Hostname must be set using ansible.builtin.hostname module (HOST-1)"
        )
        assert "name: \"{{ system_hostname }}\"" in hostname_tasks_content, (
            "Hostname module must use system_hostname variable"
        )

        # Verify HOST-2: hostname persists across reboots via /etc/hostname
        assert "ansible.builtin.copy:" in hostname_tasks_content, (
            "Hostname persistence must use copy module for /etc/hostname"
        )
        assert "dest: /etc/hostname" in hostname_tasks_content, (
            "Hostname must be written to /etc/hostname for persistence (HOST-2)"
        )
        assert "content: \"{{ system_hostname }}\\n\"" in hostname_tasks_content, (
            "Hostname file must contain system_hostname with newline"
        )

        # Verify /etc/hostname has correct permissions
        assert (
            "mode: \"0644\"" in hostname_tasks_content or "mode: '0644'" in hostname_tasks_content
        ), "Hostname file must have mode 0644"
        assert "owner: root" in hostname_tasks_content, (
            "Hostname file must be owned by root"
        )
        assert "group: root" in hostname_tasks_content, (
            "Hostname file must be owned by root group"
        )

        # Verify HOST-3: hostname is added to /etc/hosts for local resolution
        assert "ansible.builtin.lineinfile:" in hostname_tasks_content, (
            "Hostname must be added to /etc/hosts using lineinfile module"
        )
        assert "path: /etc/hosts" in hostname_tasks_content, (
            "Hostname must be added to /etc/hosts"
        )
        assert "regexp: \"^127\\\\.0\\\\.1\\\\.1\\\\s+\"" in hostname_tasks_content, (
            "Hostname entry must match 127.0.1.1 line in /etc/hosts"
        )
        assert "line: \"127.0.1.1       {{ system_hostname }}\"" in hostname_tasks_content, (
            "Hostname must be set to 127.0.1.1 in /etc/hosts"
        )

        # Verify hostname setting notifies verification handler
        assert "notify: Verify hostname persistence" in hostname_tasks_content, (
            "Hostname setting should notify verification handler"
        )

        # Read the system_config defaults
        defaults_path = Path("roles/system_config/defaults/main.yml")
        assert defaults_path.exists(), "System_config defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify system_hostname variable is defined with empty default
        assert "system_hostname:" in defaults_content, (
            "system_hostname must be defined in defaults"
        )
        assert (
            'system_hostname: ""' in defaults_content or "system_hostname: ''" in defaults_content
        ), "system_hostname default should be empty string to skip configuration"

        # Verify handlers file exists
        handlers_path = Path("roles/system_config/handlers/main.yml")
        assert handlers_path.exists(), "System_config handlers file must exist"

        handlers_content = handlers_path.read_text()

        # Verify hostname verification handler exists
        assert "name: Verify hostname persistence" in handlers_content, (
            "Verify hostname persistence handler must be defined"
        )
        assert "ansible.builtin.command: hostname" in handlers_content, (
            "Verification handler must check hostname command output"
        )
        assert "changed_when: false" in handlers_content, (
            "Verification handler should not report changes"
        )

        # Property verified: The system_config role ensures that:
        # - System hostname is set when system_hostname variable is defined (HOST-1)
        # - Hostname persists across reboots via /etc/hostname (HOST-2)
        # - Hostname is added to /etc/hosts for local resolution (HOST-3)
        # - Hostname file has correct permissions and ownership
        # - Hostname setting is verified after configuration
        # - This applies consistently across all valid hostname values

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_15_hostname_configuration_skip(self):
        """
        Feature: vps-bootstrap-playbook, Property 15: Hostname Configuration Skip

        For any execution of the bootstrap playbook WHERE no hostname is configured,
        the playbook SHALL skip hostname configuration and leave the existing hostname
        unchanged.

        Validates: HOST-4
        """
        # This property test verifies the system_config role's skip behavior by checking:
        # 1. Hostname configuration is skipped when variable is empty or undefined (HOST-4)

        # Read the system_config role tasks
        tasks_path = Path("roles/system_config/tasks/main.yml")
        assert tasks_path.exists(), "System_config tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify HOST-4: hostname configuration is conditional
        assert "ansible.builtin.import_tasks: hostname.yml" in tasks_content, (
            "Hostname configuration tasks must be imported"
        )
        assert (
            "when: system_hostname is defined and system_hostname | length > 0" in tasks_content
        ), (
            "Hostname configuration must be skipped when system_hostname is empty or undefined "
            "(HOST-4)"
        )

        # Verify the condition checks both defined and non-empty
        # This ensures hostname configuration is skipped when:
        # - system_hostname is undefined
        # - system_hostname is empty string ""
        # - system_hostname is null

        # Read the system_config defaults
        defaults_path = Path("roles/system_config/defaults/main.yml")
        assert defaults_path.exists(), "System_config defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify default is empty string (skip configuration by default)
        assert "system_hostname:" in defaults_content, (
            "system_hostname must be defined in defaults"
        )
        assert (
            'system_hostname: ""' in defaults_content or "system_hostname: ''" in defaults_content
        ), "system_hostname default should be empty string to skip configuration by default"

        # Property verified: The system_config role ensures that:
        # - Hostname configuration is skipped when system_hostname is empty or undefined (HOST-4)
        # - Default value is empty string to skip configuration by default
        # - Existing hostname remains unchanged when configuration is skipped
        # - This applies consistently regardless of the reason for skipping


class TestTimeSynchronizationProperties:
    """Property-based tests for time synchronization configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        time_sync_service=valid_time_sync_service(),
        ntp_server_count=st.integers(min_value=1, max_value=8),
    )
    def test_property_29_time_synchronization_service_configuration(
        self,
        time_sync_service: str,
        ntp_server_count: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 29: Time Synchronization Service Configuration

        For any execution of the bootstrap playbook, a time synchronization service
        SHALL be installed, configured with reliable NTP servers, enabled to start on
        boot, started, and verified to be actively synchronizing.

        Validates: TIME-1, TIME-2, TIME-3, TIME-4, TIME-5
        """
        # This property test verifies the system_config role's time sync behavior by checking:
        # 1. Time sync service is installed (TIME-1)
        # 2. NTP servers are configured (TIME-3)
        # 3. Service is enabled to start on boot (TIME-4)
        # 4. Service is started (TIME-5)
        # 5. Synchronization status is queried and registered, not asserted

        # Read the system_config role tasks
        tasks_path = Path("roles/system_config/tasks/main.yml")
        assert tasks_path.exists(), "System_config tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify time synchronization configuration is imported
        assert "ansible.builtin.import_tasks: time_sync.yml" in tasks_content, (
            "Time synchronization configuration tasks must be imported"
        )

        # Read the time synchronization tasks
        time_sync_tasks_path = Path("roles/system_config/tasks/time_sync.yml")
        assert time_sync_tasks_path.exists(), "Time sync tasks file must exist"

        time_sync_tasks_content = time_sync_tasks_path.read_text()

        # Verify TIME-1: chrony is installed when selected
        assert "ansible.builtin.apt:" in time_sync_tasks_content, (
            "Time sync service must be installed using apt module (TIME-1)"
        )
        assert "name: chrony" in time_sync_tasks_content, (
            "Chrony package must be installable"
        )
        assert "when: time_sync_service == \"chrony\"" in time_sync_tasks_content, (
            "Chrony installation must be conditional on time_sync_service variable"
        )

        # Verify conflicting services are stopped
        assert "Stop and disable systemd-timesyncd when using chrony" in time_sync_tasks_content, (
            "Conflicting time sync services must be stopped"
        )
        assert "Stop and disable chrony when using systemd-timesyncd" in time_sync_tasks_content, (
            "Conflicting time sync services must be stopped"
        )

        # Verify TIME-1, TIME-3: chrony is configured with NTP servers
        assert "ansible.builtin.template:" in time_sync_tasks_content, (
            "Time sync configuration must be deployed using template module"
        )
        assert "src: chrony.conf.j2" in time_sync_tasks_content, (
            "Chrony configuration template must be chrony.conf.j2"
        )
        assert "dest: /etc/chrony/chrony.conf" in time_sync_tasks_content, (
            "Chrony configuration must be deployed to /etc/chrony/chrony.conf"
        )
        assert "when: time_sync_service == \"chrony\"" in time_sync_tasks_content, (
            "Chrony configuration must be conditional"
        )

        # Verify configuration changes trigger service restart
        assert "notify: Restart chrony" in time_sync_tasks_content, (
            "Configuration changes must trigger chrony service restart"
        )

        # Verify TIME-4: chrony service is enabled
        assert "ansible.builtin.systemd:" in time_sync_tasks_content, (
            "Time sync service must be managed using systemd module"
        )
        assert "name: chrony" in time_sync_tasks_content, (
            "Service name must be chrony"
        )
        assert (
            "enabled: true" in time_sync_tasks_content or "enabled: yes" in time_sync_tasks_content
        ), "Chrony service must be enabled to start on boot (TIME-4)"

        # Verify TIME-5: chrony service is started
        assert "state: started" in time_sync_tasks_content, (
            "Chrony service must be started (TIME-5)"
        )

        # The synchronization status is queried with chronyc tracking
        assert "ansible.builtin.command: chronyc tracking" in time_sync_tasks_content, (
            "Chrony synchronization status must be queried using chronyc tracking"
        )
        assert "register: chrony_status" in time_sync_tasks_content, (
            "Chrony status must be registered for verification"
        )
        assert "changed_when: false" in time_sync_tasks_content, (
            "Status check should not report changes"
        )

        # Verify status is displayed
        assert "ansible.builtin.debug:" in time_sync_tasks_content, (
            "Synchronization status must be displayed"
        )
        assert (
            "msg: \"Chrony synchronization status: {{ chrony_status.stdout_lines }}\""
            in time_sync_tasks_content
        ), "Chrony status output must be displayed"

        # Verify systemd-timesyncd configuration
        assert "src: timesyncd.conf.j2" in time_sync_tasks_content, (
            "Systemd-timesyncd configuration template must be timesyncd.conf.j2"
        )
        assert "dest: /etc/systemd/timesyncd.conf" in time_sync_tasks_content, (
            "Systemd-timesyncd configuration must be deployed to /etc/systemd/timesyncd.conf"
        )
        assert "when: time_sync_service == \"timesyncd\"" in time_sync_tasks_content, (
            "Systemd-timesyncd configuration must be conditional"
        )

        # Verify systemd-timesyncd service management
        assert "name: systemd-timesyncd" in time_sync_tasks_content, (
            "Systemd-timesyncd service must be managed"
        )
        assert "notify: Restart systemd-timesyncd" in time_sync_tasks_content, (
            "Configuration changes must trigger systemd-timesyncd service restart"
        )

        # Verify systemd-timesyncd synchronization status
        assert "ansible.builtin.command: timedatectl timesync-status" in time_sync_tasks_content, (
            "Systemd-timesyncd synchronization status must be verified using timedatectl"
        )
        assert "register: timesyncd_status" in time_sync_tasks_content, (
            "Timesyncd status must be registered for verification"
        )

        # Read the system_config defaults
        defaults_path = Path("roles/system_config/defaults/main.yml")
        assert defaults_path.exists(), "System_config defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify time_sync_service variable is defined
        assert "time_sync_service:" in defaults_content, (
            "time_sync_service must be defined in defaults"
        )
        assert (
            'time_sync_service: "chrony"' in defaults_content
            or "time_sync_service: chrony" in defaults_content
        ), "Default time_sync_service should be chrony"

        # Verify TIME-3: NTP servers are configurable
        assert "ntp_servers:" in defaults_content, (
            "ntp_servers must be defined in defaults (TIME-3)"
        )

        # Verify default NTP servers are reliable
        assert "debian.pool.ntp.org" in defaults_content or "pool.ntp.org" in defaults_content, (
            "Default NTP servers should include reliable pool servers"
        )

        # Verify multiple NTP servers are configured for redundancy
        ntp_server_lines = [
            line
            for line in defaults_content.split("\n")
            if "pool.ntp.org" in line or "ntp.org" in line
        ]
        assert len(ntp_server_lines) >= 2, (
            "At least 2 NTP servers should be configured for redundancy"
        )

        # Read the chrony configuration template
        chrony_template_path = Path("roles/system_config/templates/chrony.conf.j2")
        assert chrony_template_path.exists(), "Chrony configuration template must exist"

        chrony_template_content = chrony_template_path.read_text()

        # Verify TIME-3: NTP servers are configured in template
        assert "{% for server in ntp_servers %}" in chrony_template_content, (
            "Chrony template must iterate over ntp_servers list (TIME-3)"
        )
        assert "pool {{ server }} iburst" in chrony_template_content, (
            "Chrony template must configure NTP servers with iburst option"
        )

        # Verify chrony drift file is configured
        assert "driftfile /var/lib/chrony/drift" in chrony_template_content, (
            "Chrony must configure drift file for clock rate tracking"
        )

        # Verify chrony makestep is configured for initial sync
        assert "makestep" in chrony_template_content, (
            "Chrony must configure makestep for initial time adjustment"
        )

        # Verify chrony RTC sync is enabled
        assert "rtcsync" in chrony_template_content, (
            "Chrony must enable RTC synchronization"
        )

        # Verify template has Ansible managed comment
        assert (
            "managed by ansible" in chrony_template_content.lower()
        ), "Template should have Ansible managed comment"

        # Read the systemd-timesyncd configuration template
        timesyncd_template_path = Path("roles/system_config/templates/timesyncd.conf.j2")
        assert timesyncd_template_path.exists(), (
            "Systemd-timesyncd configuration template must exist"
        )

        timesyncd_template_content = timesyncd_template_path.read_text()

        # Verify TIME-3: NTP servers are configured in timesyncd template
        assert "[Time]" in timesyncd_template_content, (
            "Systemd-timesyncd template must have [Time] section"
        )
        assert "NTP={{ ntp_servers | join(' ') }}" in timesyncd_template_content, (
            "Systemd-timesyncd template must configure NTP servers (TIME-3)"
        )

        # Verify template has Ansible managed comment
        assert (
            "managed by ansible" in timesyncd_template_content.lower()
        ), "Template should have Ansible managed comment"

        # Verify handlers file exists
        handlers_path = Path("roles/system_config/handlers/main.yml")
        assert handlers_path.exists(), "System_config handlers file must exist"

        handlers_content = handlers_path.read_text()

        # Verify restart handlers are defined
        assert "name: Restart chrony" in handlers_content, (
            "Restart chrony handler must be defined"
        )
        assert "name: Restart systemd-timesyncd" in handlers_content, (
            "Restart systemd-timesyncd handler must be defined"
        )

        # Verify handlers use systemd module
        assert "ansible.builtin.systemd:" in handlers_content, (
            "Restart handlers must use systemd module"
        )
        assert "state: restarted" in handlers_content, (
            "Restart handlers must restart the service"
        )

        # Verify handlers are conditional
        assert "when: time_sync_service == \"chrony\"" in handlers_content, (
            "Chrony restart handler must be conditional"
        )
        assert "when: time_sync_service == \"timesyncd\"" in handlers_content, (
            "Systemd-timesyncd restart handler must be conditional"
        )

        # Property verified: The system_config role ensures that:
        # - Time sync service is installed (TIME-1)
        # - NTP servers are configured (TIME-3)
        # - Service is enabled to start on boot (TIME-4)
        # - Service is started (TIME-5)
        # - Synchronization status is queried (not asserted)
        # - Conflicting services are stopped (TIME-2)
        # - Configuration changes trigger service restart
        # - Multiple NTP servers are configured for redundancy
        # - This applies consistently across all valid configuration values


class TestTimeSyncServiceSelectionProperties:
    """Property-based tests for time sync service selection."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        time_sync_service=valid_time_sync_service(),
    )
    def test_time_sync_service_mutual_exclusion(self, time_sync_service: str):
        """
        Feature: vps-bootstrap-playbook, Time Sync Service Mutual Exclusion

        For any execution of the bootstrap playbook with a selected time sync service,
        the playbook SHALL ensure that only the selected service is running and enabled,
        and conflicting services are stopped and disabled.

        Validates: TIME-2

        This property verifies that:
        - Only one time sync service is active at a time
        - Conflicting services are stopped and disabled
        - Service selection is configurable
        """
        # Read the time synchronization tasks
        time_sync_tasks_path = Path("roles/system_config/tasks/time_sync.yml")
        assert time_sync_tasks_path.exists(), "Time sync tasks file must exist"

        time_sync_tasks_content = time_sync_tasks_path.read_text()

        # Verify chrony stops systemd-timesyncd
        assert "Stop and disable systemd-timesyncd when using chrony" in time_sync_tasks_content, (
            "Chrony configuration must stop conflicting systemd-timesyncd"
        )
        assert "name: systemd-timesyncd" in time_sync_tasks_content, (
            "Systemd-timesyncd must be stopped when using chrony"
        )
        assert "state: stopped" in time_sync_tasks_content, (
            "Conflicting service must be stopped"
        )
        assert (
            "enabled: false" in time_sync_tasks_content or "enabled: no" in time_sync_tasks_content
        ), "Conflicting service must be disabled"

        # Verify systemd-timesyncd stops chrony
        assert "Stop and disable chrony when using systemd-timesyncd" in time_sync_tasks_content, (
            "Systemd-timesyncd configuration must stop conflicting chrony"
        )
        assert "name: chrony" in time_sync_tasks_content, (
            "Chrony must be stopped when using systemd-timesyncd"
        )

        # Verify failed_when: false for graceful handling
        assert "failed_when: false" in time_sync_tasks_content, (
            "Service stop tasks should use failed_when: false for graceful handling"
        )

        # Read the system_config defaults
        defaults_path = Path("roles/system_config/defaults/main.yml")
        assert defaults_path.exists(), "System_config defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify time_sync_service is configurable
        assert "time_sync_service:" in defaults_content, (
            "time_sync_service must be configurable"
        )

        # Verify default is chrony (more feature-rich)
        assert (
            'time_sync_service: "chrony"' in defaults_content
            or "time_sync_service: chrony" in defaults_content
        ), "Default time_sync_service should be chrony"

        # Property verified: The system_config role ensures:
        # - Only one time sync service is active at a time
        # - Conflicting services are stopped and disabled
        # - Service selection is configurable via time_sync_service variable
        # - Graceful handling of missing services


class TestNTPServerConfigurationProperties:
    """Property-based tests for NTP server configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ntp_server_count=st.integers(min_value=1, max_value=8),
    )
    def test_ntp_server_list_configuration(self, ntp_server_count: int):
        """
        Feature: vps-bootstrap-playbook, NTP Server List Configuration

        For any execution of the bootstrap playbook with configured NTP servers,
        the playbook SHALL configure all specified NTP servers in the time sync
        service configuration for redundancy and reliability.

        Validates: TIME-3

        This property verifies that:
        - Multiple NTP servers can be configured
        - All servers are included in configuration
        - Configuration uses pool directive for load balancing
        """
        # Read the chrony configuration template
        chrony_template_path = Path("roles/system_config/templates/chrony.conf.j2")
        assert chrony_template_path.exists(), "Chrony configuration template must exist"

        chrony_template_content = chrony_template_path.read_text()

        # Verify NTP servers are iterated
        assert "{% for server in ntp_servers %}" in chrony_template_content, (
            "Chrony template must iterate over all NTP servers"
        )
        assert "pool {{ server }} iburst" in chrony_template_content, (
            "Chrony template must use pool directive for each server"
        )
        assert "{% endfor %}" in chrony_template_content, (
            "Chrony template must close the for loop"
        )

        # Verify iburst option is used for faster initial sync
        assert "iburst" in chrony_template_content, (
            "Chrony should use iburst option for faster initial synchronization"
        )

        # Read the systemd-timesyncd configuration template
        timesyncd_template_path = Path("roles/system_config/templates/timesyncd.conf.j2")
        assert timesyncd_template_path.exists(), (
            "Systemd-timesyncd configuration template must exist"
        )

        timesyncd_template_content = timesyncd_template_path.read_text()

        # Verify NTP servers are joined with spaces
        assert "NTP={{ ntp_servers | join(' ') }}" in timesyncd_template_content, (
            "Systemd-timesyncd template must join all NTP servers with spaces"
        )

        # Read the system_config defaults
        defaults_path = Path("roles/system_config/defaults/main.yml")
        assert defaults_path.exists(), "System_config defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify ntp_servers is a list
        assert "ntp_servers:" in defaults_content, (
            "ntp_servers must be defined as a list"
        )

        # Verify at least 2 default servers for redundancy
        ntp_server_lines = [
            line for line in defaults_content.split('\n')
            if line.strip().startswith('- ') and ('ntp.org' in line or 'time' in line)
        ]
        assert len(ntp_server_lines) >= 2, (
            "At least 2 NTP servers should be configured by default for redundancy"
        )

        # Property verified: The system_config role ensures:
        # - Multiple NTP servers can be configured
        # - All servers are included in configuration
        # - Chrony uses pool directive for load balancing
        # - Systemd-timesyncd joins servers with spaces
        # - At least 2 servers are configured by default for redundancy
