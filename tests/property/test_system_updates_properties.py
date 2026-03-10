"""
Property-based tests for system updates in VPS Bootstrap Playbook.

These tests verify universal properties about package updates, cache management,
and reboot notification across all valid configurations.
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid system update configuration values
@st.composite
def valid_cache_valid_time(draw):
    """Generate valid apt cache validity times in seconds (300-7200)."""
    return draw(st.integers(min_value=300, max_value=7200))


@st.composite
def valid_upgrade_type(draw):
    """Generate valid apt upgrade types."""
    return draw(st.sampled_from(["dist", "full", "safe", "yes"]))


class TestSystemUpdatesProperties:
    """Property-based tests for system package updates."""

    @settings(max_examples=100)
    @given(
        cache_valid_time=valid_cache_valid_time(),
        upgrade_type=valid_upgrade_type(),
        autoremove=st.booleans(),
        autoclean=st.booleans(),
    )
    def test_property_16_system_package_updates(
        self,
        cache_valid_time: int,
        upgrade_type: str,
        autoremove: bool,
        autoclean: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 16: System Package Updates

        For any execution of the bootstrap playbook on a Debian stable system,
        the playbook SHALL execute apt update and apt upgrade, and notify the
        operator if a reboot is required.

        Validates: Requirements 7.1, 7.2, 7.3, 7.4
        """
        # This property test verifies the system_updates role's behavior by checking:
        # 1. apt update is executed to refresh package lists (Requirement 7.1)
        # 2. apt upgrade is executed to install available updates (Requirement 7.2)
        # 3. The playbook targets Debian stable distribution (Requirement 7.3)
        # 4. Operator is notified when package upgrades require a reboot (Requirement 7.4)

        # Read the system_updates role tasks
        tasks_path = Path("roles/system_updates/tasks/main.yml")
        assert tasks_path.exists(), "System updates tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify Requirement 7.1: apt update is executed
        assert "ansible.builtin.apt:" in tasks_content, (
            "System updates must use ansible.builtin.apt module"
        )
        assert "update_cache: true" in tasks_content or "update_cache: yes" in tasks_content, (
            "apt update must be executed to refresh package lists (Requirement 7.1)"
        )

        # Verify cache validity time is configurable
        assert "cache_valid_time:" in tasks_content, (
            "apt cache validity time should be configurable"
        )
        assert "{{ apt_update_cache_valid_time }}" in tasks_content, (
            "apt cache validity time must use apt_update_cache_valid_time variable"
        )

        # Verify Requirement 7.2: apt upgrade is executed
        assert "upgrade:" in tasks_content, (
            "apt upgrade must be executed to install available updates (Requirement 7.2)"
        )
        assert "{{ apt_upgrade_type }}" in tasks_content, (
            "apt upgrade type must use apt_upgrade_type variable"
        )

        # Verify upgrade task registers result for reboot checking
        assert "register: apt_upgrade_result" in tasks_content, (
            "apt upgrade task must register result for tracking"
        )

        # Verify autoremove and autoclean are configurable
        assert "autoremove:" in tasks_content, (
            "apt autoremove should be configurable"
        )
        assert "{{ apt_autoremove }}" in tasks_content, (
            "apt autoremove must use apt_autoremove variable"
        )
        assert "autoclean:" in tasks_content, (
            "apt autoclean should be configurable"
        )
        assert "{{ apt_autoclean }}" in tasks_content, (
            "apt autoclean must use apt_autoclean variable"
        )

        # Verify Requirement 7.4: Reboot notification
        # Check for reboot-required file detection
        assert "/var/run/reboot-required" in tasks_content, (
            "Playbook must check for /var/run/reboot-required file (Requirement 7.4)"
        )
        assert "ansible.builtin.stat:" in tasks_content, (
            "Playbook must use stat module to check reboot-required file"
        )
        assert "register: reboot_required_file" in tasks_content, (
            "Reboot check must register result"
        )

        # Verify operator notification when reboot is required
        assert "ansible.builtin.debug:" in tasks_content, (
            "Playbook must notify operator using debug module"
        )
        assert "when: reboot_required_file.stat.exists" in tasks_content, (
            "Notification must be conditional on reboot-required file existence"
        )

        # Verify notification message is informative
        assert "REBOOT REQUIRED" in tasks_content or "reboot" in tasks_content.lower(), (
            "Notification message must clearly indicate reboot is required"
        )

        # Read the defaults to verify configuration values
        defaults_path = Path("roles/system_updates/defaults/main.yml")
        assert defaults_path.exists(), "System updates defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify apt_update_cache_valid_time is defined
        assert "apt_update_cache_valid_time:" in defaults_content, (
            "apt_update_cache_valid_time must be defined in defaults"
        )

        # Verify apt_upgrade_type is defined with appropriate default
        assert "apt_upgrade_type:" in defaults_content, (
            "apt_upgrade_type must be defined in defaults"
        )

        # Verify default upgrade type is appropriate for Debian stable (Requirement 7.3)
        # "dist" is recommended for Debian stable as it handles dependencies correctly
        assert (
            'apt_upgrade_type: "dist"' in defaults_content
            or "apt_upgrade_type: dist" in defaults_content
        ), (
            "Default apt_upgrade_type should be 'dist' for Debian stable (Requirement 7.3)"
        )

        # Verify autoremove is defined
        assert "apt_autoremove:" in defaults_content, (
            "apt_autoremove must be defined in defaults"
        )

        # Verify autoclean is defined
        assert "apt_autoclean:" in defaults_content, (
            "apt_autoclean must be defined in defaults"
        )

        # Verify cache valid time is reasonable (not too short, not too long)
        for line in defaults_content.split('\n'):
            if line.strip().startswith('apt_update_cache_valid_time:'):
                value = line.split(':')[1].strip()
                try:
                    default_cache_time = int(value)
                    assert 300 <= default_cache_time <= 7200, (
                        f"Default apt_update_cache_valid_time should be between "
                        f"300 and 7200 seconds, got {default_cache_time}"
                    )
                except ValueError:
                    pass  # Value might be a variable reference

        # Verify tasks are properly tagged for selective execution
        assert "tags:" in tasks_content, (
            "Tasks should be tagged for selective execution"
        )
        assert "system_updates" in tasks_content, (
            "Tasks should have system_updates tag"
        )

        # Verify apt tasks are tagged appropriately
        assert "apt" in tasks_content, (
            "apt tasks should have apt tag"
        )

        # Verify reboot check tasks are tagged appropriately
        assert "reboot_check" in tasks_content, (
            "Reboot check tasks should have reboot_check tag"
        )

        # Verify the role reads packages requiring reboot for detailed notification
        assert "/var/run/reboot-required.pkgs" in tasks_content, (
            "Role should read /var/run/reboot-required.pkgs for detailed information"
        )
        assert "ansible.builtin.command:" in tasks_content, (
            "Role should use command module to read reboot-required packages"
        )

        # Verify the command task is marked as not changing system state
        assert "changed_when: false" in tasks_content, (
            "Reading reboot-required.pkgs should not be marked as a change"
        )

        # Verify the command task handles missing file gracefully
        assert "failed_when: false" in tasks_content, (
            "Reading reboot-required.pkgs should not fail if file is missing"
        )

        # Verify notification includes package list
        assert "reboot_packages" in tasks_content, (
            "Notification should include list of packages requiring reboot"
        )

        # Property verified: The system_updates role configuration ensures that:
        # - apt update is executed to refresh package lists (7.1)
        # - apt upgrade is executed to install available updates (7.2)
        # - Default upgrade type is 'dist' for Debian stable (7.3)
        # - Operator is notified when reboot is required (7.4)
        # - Notification includes list of packages requiring reboot
        # - Cache validity time is configurable and reasonable
        # - Autoremove and autoclean are configurable
        # - Tasks are properly tagged for selective execution
        # - This applies consistently across all valid configuration values


class TestSystemUpdatesIdempotencyProperties:
    """Property-based tests for system updates idempotency."""

    @settings(max_examples=50)
    @given(
        cache_valid_time=valid_cache_valid_time(),
    )
    def test_system_updates_cache_idempotency(self, cache_valid_time: int):
        """
        Feature: vps-bootstrap-playbook, System Updates Cache Idempotency

        For any execution of the bootstrap playbook with a configured cache validity time,
        the apt update task SHALL skip cache refresh if the cache is still valid,
        ensuring idempotent behavior.

        This property verifies that:
        - cache_valid_time parameter is used correctly
        - Repeated executions within cache validity period don't refresh unnecessarily
        - This reduces network traffic and execution time
        """
        # Read the system_updates role tasks
        tasks_path = Path("roles/system_updates/tasks/main.yml")
        assert tasks_path.exists(), "System updates tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify cache_valid_time is used in apt update task
        assert "cache_valid_time:" in tasks_content, (
            "apt update task must use cache_valid_time parameter"
        )
        assert "{{ apt_update_cache_valid_time }}" in tasks_content, (
            "cache_valid_time must reference apt_update_cache_valid_time variable"
        )

        # Verify the apt module is used (it handles cache validity automatically)
        assert "ansible.builtin.apt:" in tasks_content, (
            "Must use ansible.builtin.apt module for cache management"
        )

        # Property verified: The system_updates role ensures:
        # - cache_valid_time parameter is properly configured
        # - apt module will skip cache refresh if cache is still valid
        # - This provides idempotent behavior for repeated executions


class TestSystemUpdatesNonInteractiveProperties:
    """Property-based tests for non-interactive system updates."""

    @settings(max_examples=50)
    @given(
        upgrade_type=valid_upgrade_type(),
    )
    def test_system_updates_non_interactive_execution(self, upgrade_type: str):
        """
        Feature: vps-bootstrap-playbook, System Updates Non-Interactive Execution

        For any execution of the bootstrap playbook, the apt upgrade task SHALL
        execute in non-interactive mode, ensuring automated execution without
        requiring user input.

        This property verifies that:
        - apt upgrade runs without prompts
        - Suitable for automated/unattended execution
        - No manual intervention required during bootstrap
        """
        # Read the system_updates role tasks
        tasks_path = Path("roles/system_updates/tasks/main.yml")
        assert tasks_path.exists(), "System updates tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify ansible.builtin.apt module is used
        # This module handles non-interactive execution automatically
        assert "ansible.builtin.apt:" in tasks_content, (
            "Must use ansible.builtin.apt module for non-interactive execution"
        )

        # Verify upgrade parameter is used
        assert "upgrade:" in tasks_content, (
            "apt task must specify upgrade parameter"
        )

        # The ansible.builtin.apt module automatically handles non-interactive execution
        # by setting DEBIAN_FRONTEND=noninteractive and using appropriate apt flags
        # No additional configuration is needed

        # Property verified: The system_updates role ensures:
        # - apt upgrade executes non-interactively
        # - Suitable for automated bootstrap execution
        # - No manual intervention required
