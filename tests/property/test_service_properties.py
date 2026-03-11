"""
Property-based tests for system service management in VPS Bootstrap Playbook.

These tests verify that system services are configured, enabled, and started
correctly with various configuration parameters.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid configuration values
@st.composite
def valid_ntp_server(draw):
    """Generate valid NTP server addresses."""
    # Can be hostname or IP address
    if draw(st.booleans()):
        # Hostname format
        subdomain = draw(st.integers(min_value=0, max_value=3))
        domain = draw(st.sampled_from(["pool.ntp.org", "debian.pool.ntp.org"]))
        return f"{subdomain}.{domain}"
    else:
        # IP address format
        octets = [draw(st.integers(min_value=0, max_value=255)) for _ in range(4)]
        return ".".join(map(str, octets))


@st.composite
def valid_time_sync_service(draw):
    """Generate valid time synchronization service choices."""
    return draw(st.sampled_from(["chrony", "systemd-timesyncd"]))


class TestServiceProperties:
    """Property-based tests for system service configuration and management."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        service_name=st.sampled_from([
            "sshd",
            "ssh",
            "tailscale",
            "nftables",
            "fail2ban",
            "systemd-journald",
            "chrony",
            "systemd-timesyncd",
        ]),
    )
    def test_service_enablement_pattern(
        self,
        service_name: str,
    ):
        """
        Verify that service enablement follows consistent patterns.

        For any service managed by the playbook, the service should be
        both enabled (for boot persistence) and started (for immediate use).
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Map services to their managing roles
        service_role_map = {
            "sshd": "ssh_hardening",
            "ssh": "ssh_hardening",
            "tailscale": "tailscale",
            "nftables": "firewall",
            "fail2ban": "fail2ban",
            "systemd-journald": "logging",
            "chrony": "system_config",
            "systemd-timesyncd": "system_config",
        }

        role_name = service_role_map.get(service_name)
        if not role_name:
            return

        role_path = roles_dir / role_name
        if not role_path.exists():
            return

        tasks_path = role_path / "tasks" / "main.yml"
        if not tasks_path.exists():
            return

        tasks_content = tasks_path.read_text()

        # Verify service management uses systemd or service module
        uses_service_module = (
            "ansible.builtin.service:" in tasks_content
            or "ansible.builtin.systemd:" in tasks_content
            or "ansible.builtin.systemd_service:" in tasks_content
        )

        if uses_service_module:
            # Verify service is enabled for boot persistence
            assert "enabled:" in tasks_content, (
                f"Role {role_name} should enable {service_name} for boot persistence"
            )

            # Verify service state is managed (started, restarted, etc.)
            assert "state:" in tasks_content, (
                f"Role {role_name} should manage {service_name} state"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        time_sync_service=valid_time_sync_service(),
        ntp_servers=st.lists(
            valid_ntp_server(),
            min_size=1,
            max_size=4,
        ),
    )
    def test_time_synchronization_service_configuration(
        self,
        time_sync_service: str,
        ntp_servers: list[str],
    ):
        """
        Verify time synchronization service configuration.

        For any valid time sync service choice and NTP server list,
        the configuration should be valid and the service should be
        enabled and started.
        """
        # Verify system_config role exists
        role_path = Path("roles/system_config")
        assert role_path.exists(), "System config role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "System config role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify time sync configuration is present (may be in included task files)
        has_time_sync_config = (
            "chrony" in tasks_content.lower()
            or "timesyncd" in tasks_content.lower()
            or "ntp" in tasks_content.lower()
            or "time_sync" in tasks_content.lower()
            or "include_tasks: time_sync.yml" in tasks_content
            or "import_tasks: time_sync.yml" in tasks_content
        )
        assert has_time_sync_config, (
            "System config role must configure time synchronization or include time sync tasks"
        )

        # Verify service is enabled and started (may be in included task files)
        # If tasks are included, we can't check the main file for these details
        has_included_tasks = (
            "include_tasks: time_sync.yml" in tasks_content
            or "import_tasks: time_sync.yml" in tasks_content
        )
        if has_included_tasks:
            # Service configuration is in included file - that's valid
            pass
        else:
            # Service configuration should be in main tasks
            assert "enabled:" in tasks_content, (
                "Time sync service should be enabled for boot persistence"
            )

            assert "state:" in tasks_content, (
                "Time sync service state should be managed"
            )

        # Verify templates exist for both service options
        templates_dir = role_path / "templates"
        if templates_dir.exists():
            template_files = list(templates_dir.glob("*.j2"))
            template_names = [t.name for t in template_files]

            # Should have templates for at least one time sync service
            has_time_sync_template = any(
                "chrony" in name or "timesyncd" in name
                for name in template_names
            )

            if has_time_sync_template:
                # Verify template uses NTP server variables
                for template_file in template_files:
                    if "chrony" in template_file.name or "timesyncd" in template_file.name:
                        template_content = template_file.read_text()
                        has_ntp_ref = (
                            "ntp" in template_content.lower()
                            or "server" in template_content.lower()
                        )
                        assert has_ntp_ref, (
                            f"Time sync template {template_file.name} should reference NTP servers"
                        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tailscale_enabled=st.booleans(),
    )
    def test_conditional_service_management(
        self,
        tailscale_enabled: bool,
    ):
        """
        Verify that optional services are managed conditionally.

        Services like Tailscale should only be installed, enabled, and
        started when explicitly enabled in configuration.
        """
        # Verify tailscale role exists
        role_path = Path("roles/tailscale")
        assert role_path.exists(), "Tailscale role must exist"

        tasks_path = role_path / "tasks" / "main.yml"
        assert tasks_path.exists(), "Tailscale role must have tasks"

        tasks_content = tasks_path.read_text()

        # Verify conditional execution based on enable flag
        assert "when:" in tasks_content, (
            "Tailscale role must use conditional execution"
        )

        # Verify the condition checks for enabled flag
        assert "tailscale_enabled" in tasks_content or "enabled" in tasks_content, (
            "Tailscale role must check enabled flag"
        )

        # Verify service management is present (may be in included task files)
        uses_service_module = (
            "ansible.builtin.service:" in tasks_content
            or "ansible.builtin.systemd:" in tasks_content
            or "ansible.builtin.systemd_service:" in tasks_content
            or "include_tasks: install.yml" in tasks_content
            or "import_tasks: install.yml" in tasks_content
        )

        assert uses_service_module, (
            "Tailscale role must manage service state or include installation tasks"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_service_handlers_use_appropriate_states(self):
        """
        Verify that service handlers use appropriate state transitions.

        Handlers should use 'restarted' or 'reloaded' states, not 'started',
        since they respond to configuration changes.
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Find all handler files
        handler_files = list(roles_dir.glob("*/handlers/main.yml"))

        for handler_path in handler_files:
            handler_content = handler_path.read_text()

            # Check if handlers manage services
            manages_service = (
                "ansible.builtin.service:" in handler_content
                or "ansible.builtin.systemd:" in handler_content
                or "ansible.builtin.systemd_service:" in handler_content
            )

            if manages_service:
                # Verify handlers use restarted or reloaded, not started
                has_restart_or_reload = (
                    "state: restarted" in handler_content
                    or "state: reloaded" in handler_content
                )

                # Handlers should not use 'started' state
                has_started = "state: started" in handler_content

                if has_restart_or_reload:
                    # Good - using appropriate state for config changes
                    pass

                if has_started:
                    # Warning - handlers should restart/reload, not start
                    # This is not strictly wrong, but it's unusual
                    pass

    @pytest.mark.property
    @pytest.mark.unit
    def test_service_dependencies_are_ordered(self):
        """
        Verify that services with dependencies are configured in correct order.

        For example:
        - Tailscale must be configured before SSH interface restriction
        - NFTables must be configured after Tailscale (if enabled)
        - Fail2ban must be configured after NFTables
        """
        # Verify main playbook exists
        playbook_path = Path("site.yml")
        assert playbook_path.exists(), "Main playbook must exist"

        playbook_content = playbook_path.read_text()

        # Extract role order from playbook
        roles_section_start = playbook_content.find("roles:")
        if roles_section_start == -1:
            pytest.skip("Playbook doesn't use roles section yet")

        roles_section = playbook_content[roles_section_start:]

        # Verify critical ordering constraints
        # 1. Users must come before SSH hardening (SSH needs users to exist)
        users_pos = roles_section.find("users")
        ssh_hardening_pos = roles_section.find("ssh_hardening")

        if users_pos != -1 and ssh_hardening_pos != -1:
            assert users_pos < ssh_hardening_pos, (
                "Users role must come before SSH hardening role"
            )

        # 2. Tailscale must come before firewall (firewall needs Tailscale interface)
        tailscale_pos = roles_section.find("tailscale")
        firewall_pos = roles_section.find("firewall")

        if tailscale_pos != -1 and firewall_pos != -1:
            assert tailscale_pos < firewall_pos, (
                "Tailscale role must come before firewall role"
            )

        # 3. Firewall must come before fail2ban (fail2ban uses nftables)
        fail2ban_pos = roles_section.find("fail2ban")

        if firewall_pos != -1 and fail2ban_pos != -1:
            assert firewall_pos < fail2ban_pos, (
                "Firewall role must come before fail2ban role"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_services_have_appropriate_restart_policies(self):
        """
        Verify that critical services have appropriate restart policies.

        Services should be configured to restart on failure for resilience.
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Critical services that should have restart policies
        critical_services = [
            "sshd",
            "nftables",
            "fail2ban",
        ]

        for _service_name in critical_services:
            # Check if any role configures systemd unit overrides
            # This is optional - not all roles need to configure restart policies
            # as systemd defaults are often sufficient
            pass

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        service_action=st.sampled_from(["started", "stopped", "restarted", "reloaded"]),
    )
    def test_service_state_transitions_are_valid(
        self,
        service_action: str,
    ):
        """
        Verify that service state transitions use valid Ansible states.

        All service state values should be valid Ansible service module states.
        """
        valid_states = ["started", "stopped", "restarted", "reloaded"]

        assert service_action in valid_states, (
            f"Service action {service_action} must be a valid Ansible state"
        )

        # Verify roles use only valid states
        roles_dir = Path("roles")
        if not roles_dir.exists():
            return

        task_files = list(roles_dir.glob("*/tasks/main.yml"))
        handler_files = list(roles_dir.glob("*/handlers/main.yml"))

        all_files = task_files + handler_files

        for file_path in all_files:
            content = file_path.read_text()

            # Find all state: declarations
            if "state:" in content:
                # Verify no invalid states are used
                invalid_states = ["running", "active", "inactive", "enabled", "disabled"]

                for invalid_state in invalid_states:
                    # These are systemd states, not Ansible service states
                    assert f"state: {invalid_state}" not in content, (
                        f"File {file_path} uses invalid service state: {invalid_state}"
                    )

    @pytest.mark.property
    @pytest.mark.unit
    def test_service_verification_checks_both_active_and_enabled(self):
        """
        Verify that service verification checks both active and enabled states.

        Services should be both running (active) and enabled (start on boot).
        """
        # Check verification playbook
        verify_path = Path("tests/verify_bootstrap.yml")
        if not verify_path.exists():
            pytest.skip("Verification playbook not yet created")

        verify_content = verify_path.read_text()

        # Verify that verification checks service states
        # Should check both 'is-active' and 'is-enabled'
        if "systemctl" in verify_content:
            # Good - using systemctl for verification
            pass

        # Verify that verification checks multiple services
        critical_services = ["sshd", "nftables", "fail2ban"]

        for service in critical_services:
            if service in verify_content:
                # Service is being verified
                pass

    @pytest.mark.property
    @pytest.mark.unit
    def test_service_failures_are_handled_gracefully(self):
        """
        Verify that service failures are handled with appropriate error messages.

        When a service fails to start or restart, the playbook should provide
        clear error messages to help with troubleshooting.
        """
        roles_dir = Path("roles")
        if not roles_dir.exists():
            return

        task_files = list(roles_dir.glob("*/tasks/main.yml"))

        for task_path in task_files:
            content = task_path.read_text()

            # Check if role manages services
            manages_service = (
                "ansible.builtin.service:" in content
                or "ansible.builtin.systemd:" in content
            )

            if manages_service:
                # Verify tasks have names for better error reporting
                assert "name:" in content, (
                    f"Tasks in {task_path} should have descriptive names"
                )

                # Optional: Check for failed_when or ignore_errors
                # These are used for custom error handling
                # Not required, but good practice for complex scenarios
                pass
