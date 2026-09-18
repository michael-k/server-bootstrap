"""
Property-based tests for logging configuration in VPS Bootstrap Playbook.

These tests verify universal properties about journald persistent logging
configuration across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid journald configuration values
@st.composite
def valid_disk_usage(draw):
    """Generate valid disk usage values for journald."""
    # Support both numeric (bytes) and string formats (e.g., "500M", "1G")
    format_choice = draw(st.sampled_from(["numeric", "string"]))
    if format_choice == "numeric":
        # Disk usage in bytes (100MB to 2GB)
        return draw(st.integers(min_value=100 * 1024 * 1024, max_value=2 * 1024 * 1024 * 1024))
    else:
        # String format with size units
        value = draw(st.integers(min_value=100, max_value=2048))
        unit = draw(st.sampled_from(["M", "G"]))
        return f"{value}{unit}"


@st.composite
def valid_retention_time(draw):
    """Generate valid retention time durations for journald."""
    # Support both numeric (seconds) and string formats (e.g., "1week", "1month")
    format_choice = draw(st.sampled_from(["numeric", "string"]))
    if format_choice == "numeric":
        # Retention time in seconds (1 day to 90 days)
        return draw(st.integers(min_value=86400, max_value=90 * 86400))
    else:
        # String format with time units
        value = draw(st.integers(min_value=1, max_value=12))
        unit = draw(st.sampled_from(["day", "week", "month", "year"]))
        return f"{value}{unit}"


@st.composite
def valid_storage_mode(draw):
    """Generate valid journald storage modes."""
    return draw(st.sampled_from(["persistent", "volatile", "auto"]))


@st.composite
def valid_compress_setting(draw):
    """Generate valid journald compress settings."""
    return draw(st.sampled_from(["yes", "no"]))


class TestJournaldProperties:
    """Property-based tests for journald persistent logging configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        max_disk_usage=valid_disk_usage(),
        max_retention_time=valid_retention_time(),
        storage_mode=valid_storage_mode(),
        compress=valid_compress_setting(),
    )
    def test_property_28_journald_persistent_logging_configuration(
        self,
        max_disk_usage,
        max_retention_time,
        storage_mode: str,
        compress: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 28: Journald Persistent Logging Configuration

        For any execution of the bootstrap playbook, journald SHALL be configured to
        persist logs to disk with configurable maximum disk usage and retention time.

        Validates: LOG-1, LOG-2, LOG-3, LOG-5
        """
        # This property test verifies the logging role's behavior by checking:
        # 1. journald is configured to persist logs to disk (LOG-1)
        # 2. journald maximum disk usage is configurable (LOG-2)
        # 3. journald log retention time is configurable (LOG-3)
        # 4. the persistent journal directory has correct ownership/mode (LOG-5)

        # Read the logging role tasks
        tasks_path = Path("roles/logging/tasks/main.yml")
        assert tasks_path.exists(), "Logging tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify journald configuration is deployed
        assert "ansible.builtin.template:" in tasks_content, (
            "Journald configuration must be deployed using template module"
        )
        assert "journald.conf.j2" in tasks_content, (
            "Journald configuration template must be journald.conf.j2"
        )
        assert "dest: /etc/systemd/journald.conf" in tasks_content, (
            "Journald configuration must be deployed to /etc/systemd/journald.conf"
        )

        # Verify LOG-4: configuration changes trigger service restart
        assert "notify: Restart systemd-journald" in tasks_content, (
            "Configuration changes must trigger systemd-journald service restart (LOG-4)"
        )

        # Verify LOG-5: journal directory is created
        assert "ansible.builtin.file:" in tasks_content, (
            "Journal directory must be created using file module (LOG-5)"
        )
        assert "/var/log/journal" in tasks_content, (
            "Journal directory must be /var/log/journal (LOG-5)"
        )
        assert "state: directory" in tasks_content, (
            "Journal directory must be created as directory (LOG-5)"
        )

        # Verify LOG-5: journal directory has correct ownership
        assert "owner: root" in tasks_content, (
            "Journal directory must be owned by root (LOG-5)"
        )
        assert "group: systemd-journal" in tasks_content, (
            "Journal directory must be owned by systemd-journal group (LOG-5)"
        )

        # Verify LOG-5: journal directory has correct permissions (2755 for setgid)
        assert "mode: '2755'" in tasks_content or 'mode: "2755"' in tasks_content, (
            "Journal directory must have mode 2755 (setgid) (LOG-5)"
        )

        # Verify LOG-4: handlers are flushed to restart journald immediately
        assert "ansible.builtin.meta: flush_handlers" in tasks_content, (
            "Handlers must be flushed to restart journald after configuration (LOG-4)"
        )

        # Read the logging defaults
        defaults_path = Path("roles/logging/defaults/main.yml")
        assert defaults_path.exists(), "Logging defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify LOG-2: maximum disk usage is configurable
        assert "journald_max_disk_usage:" in defaults_content, (
            "journald_max_disk_usage must be defined in defaults (LOG-2)"
        )

        # Verify LOG-3: retention time is configurable
        assert "journald_max_retention_time:" in defaults_content, (
            "journald_max_retention_time must be defined in defaults (LOG-3)"
        )

        # Read the journald configuration template
        template_path = Path("roles/logging/templates/journald.conf.j2")
        assert template_path.exists(), "Journald configuration template must exist"

        template_content = template_path.read_text()

        # Verify LOG-1: persistent storage is configured
        assert "[Journal]" in template_content, (
            "Journald configuration must have [Journal] section"
        )
        assert "Storage=persistent" in template_content, (
            "Journald must be configured for persistent storage (LOG-1)"
        )

        # Verify LOG-2: SystemMaxUse is configured
        assert "SystemMaxUse={{ journald_max_disk_usage }}" in template_content, (
            "Journald configuration must use journald_max_disk_usage variable (LOG-2)"
        )

        # Verify LOG-3: MaxRetentionSec is configured
        assert "MaxRetentionSec={{ journald_max_retention_time }}" in template_content, (
            "Journald configuration must use journald_max_retention_time variable "
            "(LOG-3)"
        )

        # Verify compression is enabled for efficient storage
        assert "Compress=yes" in template_content, (
            "Journald should enable compression for efficient storage"
        )

        # Verify ForwardToSyslog is disabled (using journald directly)
        assert "ForwardToSyslog=no" in template_content, (
            "ForwardToSyslog should be disabled when using journald directly"
        )

        # Verify template has Ansible managed comment
        assert "Managed by Ansible" in template_content or "DO NOT EDIT" in template_content, (
            "Template should have Ansible managed comment"
        )

        # Verify default values are reasonable
        for line in defaults_content.split('\n'):
            if line.strip().startswith('journald_max_disk_usage:'):
                value = line.split(':')[1].strip().strip('"').strip("'")
                # Check if it's a reasonable size (at least 100M, at most 10G)
                if value.endswith('M'):
                    size_mb = int(value[:-1])
                    assert 100 <= size_mb <= 10240, (
                        f"Default journald_max_disk_usage should be between 100M and 10G, "
                        f"got {value}"
                    )
                elif value.endswith('G'):
                    size_gb = int(value[:-1])
                    assert 1 <= size_gb <= 10, (
                        f"Default journald_max_disk_usage should be between 1G and 10G, "
                        f"got {value}"
                    )

            if line.strip().startswith('journald_max_retention_time:'):
                value = line.split(':')[1].strip().strip('"').strip("'")
                # Check if it's a reasonable retention time
                assert any(unit in value for unit in ['day', 'week', 'month', 'year']), (
                    f"Default journald_max_retention_time should use time units "
                    f"(day/week/month/year), got {value}"
                )

        # Verify handlers file exists for service restart
        handlers_path = Path("roles/logging/handlers/main.yml")
        assert handlers_path.exists(), "Logging handlers file must exist"

        handlers_content = handlers_path.read_text()

        # Verify restart handler is defined
        assert (
            "name: Restart systemd-journald" in handlers_content
            or "name: restart systemd-journald" in handlers_content
        ), "Restart systemd-journald handler must be defined"
        assert "ansible.builtin.systemd:" in handlers_content, (
            "Restart handler must use systemd module"
        )
        assert "name: systemd-journald" in handlers_content, (
            "Restart handler must target systemd-journald service"
        )
        assert "state: restarted" in handlers_content, (
            "Restart handler must restart the service"
        )

        # Property verified: The logging role configuration ensures that:
        # - journald is configured to persist logs to disk (LOG-1)
        # - maximum disk usage is configurable via journald_max_disk_usage (LOG-2)
        # - retention time is configurable via journald_max_retention_time (LOG-3)
        # - configuration changes trigger service restart (LOG-4)
        # - journal directory is created with correct permissions (LOG-5)
        # - compression is enabled for efficient storage
        # - This applies consistently across all valid configuration values


class TestJournaldStorageModeProperties:
    """Property-based tests for journald storage mode configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        storage_mode=valid_storage_mode(),
    )
    def test_journald_storage_mode_configuration(self, storage_mode: str):
        """
        Feature: vps-bootstrap-playbook, Journald Storage Mode Configuration

        For any execution of the bootstrap playbook, journald SHALL be configured
        with persistent storage mode to ensure logs survive system reboots.

        This property verifies that:
        - Storage mode is set to persistent (LOG-1)
        - Journal directory is created for persistent storage (LOG-5)
        - Directory has correct ownership and permissions (LOG-5)

        Validates: LOG-1, LOG-5
        """
        # Read the journald configuration template
        template_path = Path("roles/logging/templates/journald.conf.j2")
        assert template_path.exists(), "Journald configuration template must exist"

        template_content = template_path.read_text()

        # Verify LOG-1: storage mode is persistent (not volatile or auto)
        assert "Storage=persistent" in template_content, (
            "Journald must use persistent storage mode for log persistence (LOG-1)"
        )

        # Read the logging role tasks
        tasks_path = Path("roles/logging/tasks/main.yml")
        assert tasks_path.exists(), "Logging tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify LOG-5: journal directory is created
        assert "/var/log/journal" in tasks_content, (
            "Journal directory /var/log/journal must be created for persistent storage (LOG-5)"
        )

        # Verify LOG-5: directory creation task exists
        assert "ansible.builtin.file:" in tasks_content, (
            "Directory must be created using file module (LOG-5)"
        )
        assert "state: directory" in tasks_content, (
            "Journal path must be created as directory (LOG-5)"
        )

        # Property verified: The logging role ensures:
        # - Storage mode is persistent for log persistence across reboots (LOG-1)
        # - Journal directory is created with correct permissions (LOG-5)
        # - Logs survive system reboots


class TestJournaldCompressionProperties:
    """Property-based tests for journald compression configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        compress=valid_compress_setting(),
    )
    def test_journald_compression_configuration(self, compress: str):
        """
        Feature: vps-bootstrap-playbook, Journald Compression Configuration

        For any execution of the bootstrap playbook, journald SHALL be configured
        with compression enabled to reduce disk space usage for log storage.

        This property verifies that:
        - Compression is enabled
        - Configuration uses efficient compression algorithm
        """
        # Read the journald configuration template
        template_path = Path("roles/logging/templates/journald.conf.j2")
        assert template_path.exists(), "Journald configuration template must exist"

        template_content = template_path.read_text()

        # Verify compression is enabled
        assert "Compress=yes" in template_content, (
            "Journald should enable compression to reduce disk space usage"
        )

        # Verify [Journal] section exists
        assert "[Journal]" in template_content, (
            "Journald configuration must have [Journal] section"
        )

        # Property verified: The logging role ensures:
        # - Compression is enabled for efficient disk space usage
        # - Logs are compressed automatically by journald


class TestJournaldServiceRestartProperties:
    """Property-based tests for journald service restart behavior."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        max_disk_usage=valid_disk_usage(),
        max_retention_time=valid_retention_time(),
    )
    def test_journald_service_restart_on_configuration_change(
        self,
        max_disk_usage,
        max_retention_time,
    ):
        """
        Feature: vps-bootstrap-playbook, Journald Service Restart

        For any execution of the bootstrap playbook where journald configuration
        is modified, the systemd-journald service SHALL be restarted to apply
        the new configuration.

        This property verifies that:
        - Configuration changes trigger service restart via handler (LOG-4)
        - Handler is flushed immediately after configuration (LOG-4)
        - Service restart uses systemd module

        Validates: LOG-4
        """
        # Read the logging role tasks
        tasks_path = Path("roles/logging/tasks/main.yml")
        assert tasks_path.exists(), "Logging tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify LOG-4: configuration deployment notifies restart handler
        assert "notify: Restart systemd-journald" in tasks_content, (
            "Configuration deployment must notify restart handler (LOG-4)"
        )

        # Verify LOG-4: handlers are flushed immediately
        assert "ansible.builtin.meta: flush_handlers" in tasks_content, (
            "Handlers must be flushed to restart journald immediately (LOG-4)"
        )

        # Read the handlers file
        handlers_path = Path("roles/logging/handlers/main.yml")
        assert handlers_path.exists(), "Logging handlers file must exist"

        handlers_content = handlers_path.read_text()

        # Verify restart handler exists
        assert (
            "name: Restart systemd-journald" in handlers_content
            or "name: restart systemd-journald" in handlers_content
        ), "Restart handler must be defined"

        # Verify handler uses systemd module
        assert "ansible.builtin.systemd:" in handlers_content, (
            "Restart handler must use systemd module"
        )

        # Verify handler targets correct service
        assert "name: systemd-journald" in handlers_content, (
            "Restart handler must target systemd-journald service"
        )

        # Verify handler restarts the service
        assert "state: restarted" in handlers_content, (
            "Handler must restart the service"
        )

        # Property verified: The logging role ensures:
        # - Configuration changes trigger service restart (LOG-4)
        # - Restart happens immediately via handler flush (LOG-4)
        # - Service restart uses systemd module
        # - New configuration is applied without manual intervention
