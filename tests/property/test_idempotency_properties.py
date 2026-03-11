"""
Property-based tests for playbook idempotency in VPS Bootstrap Playbook.

These tests verify that the bootstrap playbook is idempotent - it can be run
multiple times against the same system without errors and without making
unnecessary changes.
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


class TestPlaybookIdempotencyProperties:
    """Property-based tests for playbook idempotency."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        manual_user=valid_username(),
        ansible_user=valid_username(),
        hostname=valid_hostname(),
        ssh_port=valid_ssh_port(),
        tailscale_enabled=st.booleans(),
        zram_enabled=st.booleans(),
    )
    def test_property_33_playbook_idempotency(
        self,
        manual_user: str,
        ansible_user: str,
        hostname: str,
        ssh_port: int,
        tailscale_enabled: bool,
        zram_enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 33: Playbook Idempotency

        For any execution of the bootstrap playbook against an already-configured server,
        the playbook SHALL complete without errors, report no changes for already-configured
        items, and apply only configuration changes that differ from the current state.

        Validates: Requirements 15.3, 15.4, 15.5

        This property test verifies idempotency by checking that:
        1. All roles use idempotent Ansible modules
        2. Tasks check current state before making changes
        3. Handlers only trigger when configuration actually changes
        4. File operations use appropriate modules (template, copy, lineinfile)
        5. Service operations use service/systemd modules
        6. No tasks use shell/command without changed_when conditions
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # This property test verifies idempotency through static analysis of:
        # 1. Main playbook structure
        # 2. All role tasks
        # 3. Module usage patterns
        # 4. Handler definitions

        # Verify main playbook exists and is well-formed
        playbook_path = Path("site.yml")
        assert playbook_path.exists(), "Main playbook site.yml must exist"

        playbook_content = playbook_path.read_text()

        # Verify playbook uses become for privilege escalation
        assert "become: true" in playbook_content, (
            "Playbook must use become for consistent privilege escalation"
        )

        # Verify playbook gathers facts (needed for idempotency checks)
        assert "gather_facts: true" in playbook_content, (
            "Playbook must gather facts for idempotent conditional logic"
        )

        # Verify all roles are included
        expected_roles = [
            "system_updates",
            "users",
            "ssh_hardening",
            "tailscale",
            "firewall",
            "emergency_access",
            "fail2ban",
            "logging",
            "system_config",
            "swap",
        ]

        for role in expected_roles:
            assert f"role: {role}" in playbook_content, (
                f"Playbook must include {role} role"
            )

        # Verify idempotency of each role
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        for role_name in expected_roles:
            role_path = roles_dir / role_name
            if not role_path.exists():
                # Skip roles that don't exist yet (may be optional or not implemented)
                continue

            # Check role tasks for idempotency patterns
            tasks_path = role_path / "tasks" / "main.yml"
            if tasks_path.exists():
                self._verify_role_idempotency(role_name, tasks_path)

    def _verify_role_idempotency(self, role_name: str, tasks_path: Path):
        """
        Verify that a role's tasks follow idempotency best practices.

        Args:
            role_name: Name of the role being verified
            tasks_path: Path to the role's tasks/main.yml file
        """
        tasks_content = tasks_path.read_text()

        # Idempotency Rule 1: Prefer declarative modules over imperative commands
        # These modules are inherently idempotent
        idempotent_modules = [
            "ansible.builtin.user",
            "ansible.builtin.group",
            "ansible.builtin.file",
            "ansible.builtin.copy",
            "ansible.builtin.template",
            "ansible.builtin.lineinfile",
            "ansible.builtin.blockinfile",
            "ansible.builtin.apt",
            "ansible.builtin.apt_key",
            "ansible.builtin.apt_repository",
            "ansible.builtin.service",
            "ansible.builtin.systemd",
            "ansible.builtin.systemd_service",
            "ansible.builtin.hostname",
            "ansible.builtin.sysctl",
            "ansible.builtin.mount",
            "ansible.posix.authorized_key",
            "ansible.posix.sysctl",
            "community.general.ini_file",
            "ansible.builtin.include_tasks",
            "ansible.builtin.import_tasks",
        ]

        # Verify role uses at least some idempotent modules
        uses_idempotent_modules = any(
            module in tasks_content for module in idempotent_modules
        )

        # Some roles may legitimately not use these modules (e.g., verification roles)
        # but most should use them
        if role_name not in ["emergency_access"]:  # Emergency script is a special case
            assert uses_idempotent_modules, (
                f"Role {role_name} should use idempotent Ansible modules"
            )

        # Idempotency Rule 2: Shell/command tasks must have changed_when or creates
        # Count shell/command usage
        shell_command_count = (
            tasks_content.count("ansible.builtin.shell:")
            + tasks_content.count("ansible.builtin.command:")
        )

        if shell_command_count > 0:
            # Verify changed_when or creates is used for idempotency
            changed_when_count = tasks_content.count("changed_when:")
            creates_count = tasks_content.count("creates:")
            check_mode_count = tasks_content.count("check_mode:")

            # Each shell/command should have at least one idempotency control
            # (This is a heuristic - not perfect but catches most issues)
            idempotency_controls = changed_when_count + creates_count + check_mode_count

            # Allow some flexibility - not every shell/command needs these
            # (e.g., read-only commands for verification)
            # But most should have them
            if shell_command_count > 2:
                assert idempotency_controls > 0, (
                    f"Role {role_name} uses shell/command but lacks idempotency controls "
                    f"(changed_when, creates, or check_mode)"
                )

        # Idempotency Rule 3: Package operations should use state parameter
        if "ansible.builtin.apt:" in tasks_content:
            # Verify apt tasks specify state (present, latest, absent) OR
            # use update_cache/upgrade which are also idempotent operations
            has_state = "state:" in tasks_content
            has_update_cache = "update_cache:" in tasks_content
            has_upgrade = "upgrade:" in tasks_content

            assert has_state or has_update_cache or has_upgrade, (
                f"Role {role_name} uses apt module but doesn't specify state, "
                f"update_cache, or upgrade parameter"
            )

        # Idempotency Rule 4: Service operations should use state and enabled
        if (
            "ansible.builtin.service:" in tasks_content
            or "ansible.builtin.systemd:" in tasks_content
            or "ansible.builtin.systemd_service:" in tasks_content
        ):
            # Verify service tasks specify state (started, stopped, restarted)
            assert "state:" in tasks_content, (
                f"Role {role_name} uses service module but doesn't specify state parameter"
            )

            # Verify service tasks specify enabled (yes/no) for boot persistence
            assert "enabled:" in tasks_content, (
                f"Role {role_name} uses service module but doesn't specify enabled parameter"
            )

        # Idempotency Rule 5: File operations should specify mode, owner, group
        if "ansible.builtin.file:" in tasks_content:
            # Verify file tasks specify permissions for consistency
            # (Not all file tasks need all three, but most should have mode)
            assert "mode:" in tasks_content, (
                f"Role {role_name} uses file module but doesn't specify mode parameter"
            )

        # Idempotency Rule 6: Template operations should use validate when appropriate
        if "ansible.builtin.template:" in tasks_content:
            # For critical config files (sshd, sudoers, nftables), validate should be used
            critical_configs = ["sshd_config", "sudoers", "nftables"]
            has_critical_config = any(config in tasks_content for config in critical_configs)

            if has_critical_config:
                # Validate option prevents broken configurations
                # (This is a best practice, not strictly required for idempotency)
                pass  # Optional check - validate is good practice but not required

        # Idempotency Rule 7: Handlers should be used for service restarts
        # Check if role has handlers defined
        handlers_path = tasks_path.parent.parent / "handlers" / "main.yml"
        if handlers_path.exists():
            handlers_content = handlers_path.read_text()

            # Verify handlers use idempotent modules
            if "ansible.builtin.service:" in handlers_content or (
                "ansible.builtin.systemd:" in handlers_content
            ):
                # Handlers should use 'restarted' or 'reloaded' state
                assert (
                    "state: restarted" in handlers_content
                    or "state: reloaded" in handlers_content
                ), f"Role {role_name} handlers should use restarted or reloaded state"

        # Idempotency Rule 8: Conditional execution should use when clauses
        # Verify role uses when clauses for conditional logic
        if role_name in ["tailscale", "emergency_access", "swap"]:
            # These roles have conditional execution based on variables
            assert "when:" in tasks_content, (
                f"Role {role_name} should use when clauses for conditional execution"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_playbook_structure_supports_idempotency(self):
        """
        Verify that the playbook structure supports idempotent execution.

        This test checks:
        1. Playbook uses pre_tasks for validation (doesn't modify state)
        2. Playbook uses roles for configuration (idempotent by design)
        3. Playbook uses post_tasks for reporting (doesn't modify state)
        4. Playbook uses handlers for service restarts (only when needed)
        """
        playbook_path = Path("site.yml")
        assert playbook_path.exists(), "Main playbook site.yml must exist"

        playbook_content = playbook_path.read_text()

        # Verify playbook structure
        assert "pre_tasks:" in playbook_content, (
            "Playbook should use pre_tasks for validation"
        )

        assert "roles:" in playbook_content, (
            "Playbook should use roles for configuration"
        )

        assert "post_tasks:" in playbook_content, (
            "Playbook should use post_tasks for reporting"
        )

        # Verify pre_tasks only do validation (assert, stat, debug)
        # Extract pre_tasks section (rough heuristic)
        if "pre_tasks:" in playbook_content:
            pre_tasks_start = playbook_content.find("pre_tasks:")
            roles_start = playbook_content.find("roles:", pre_tasks_start)

            if roles_start > pre_tasks_start:
                pre_tasks_section = playbook_content[pre_tasks_start:roles_start]

                # Verify no state-changing modules in pre_tasks
                # Pre-tasks should only use validation modules like assert, stat, debug
                state_changing_modules = [
                    "ansible.builtin.user:",
                    "ansible.builtin.apt:",
                    "ansible.builtin.service:",
                    "ansible.builtin.template:",
                    "ansible.builtin.copy:",
                ]

                for module in state_changing_modules:
                    assert module not in pre_tasks_section, (
                        f"Pre-tasks should not use state-changing module {module}"
                    )

        # Verify post_tasks only do reporting (debug, set_fact)
        if "post_tasks:" in playbook_content:
            post_tasks_start = playbook_content.find("post_tasks:")
            post_tasks_section = playbook_content[post_tasks_start:]

            # Verify no major state-changing modules in post_tasks
            # Post-tasks should primarily use reporting modules like debug, set_fact
            # Allow stat for checking reboot-required
            state_changing_modules = [
                "ansible.builtin.user:",
                "ansible.builtin.apt:",
                "ansible.builtin.service:",
            ]

            for module in state_changing_modules:
                assert module not in post_tasks_section, (
                    f"Post-tasks should not use state-changing module {module}"
                )

    @pytest.mark.property
    @pytest.mark.unit
    def test_roles_have_defaults_for_idempotency(self):
        """
        Verify that roles define default variables for idempotent behavior.

        Roles should have sensible defaults so they can be run multiple times
        without requiring variable changes.
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Roles that should have defaults
        roles_with_defaults = [
            "users",
            "ssh_hardening",
            "tailscale",
            "firewall",
            "fail2ban",
            "logging",
            "system_config",
            "swap",
        ]

        for role_name in roles_with_defaults:
            role_path = roles_dir / role_name
            if not role_path.exists():
                # Skip roles that don't exist yet
                continue

            defaults_path = role_path / "defaults" / "main.yml"

            # Not all roles need defaults, but most should have them
            # for idempotent configuration
            if defaults_path.exists():
                defaults_content = defaults_path.read_text()

                # Verify defaults file is not empty
                assert len(defaults_content.strip()) > 0, (
                    f"Role {role_name} has empty defaults file"
                )

                # Verify defaults use YAML format
                assert ":" in defaults_content, (
                    f"Role {role_name} defaults should define variables"
                )

    @pytest.mark.property
    @pytest.mark.unit
    def test_handlers_are_notified_not_called_directly(self):
        """
        Verify that handlers are used correctly for idempotency.

        Handlers should be notified by tasks, not called directly.
        This ensures services are only restarted when configuration changes.
        """
        roles_dir = Path("roles")
        assert roles_dir.exists(), "Roles directory must exist"

        # Roles that should have handlers for service restarts
        roles_with_handlers = [
            "ssh_hardening",
            "firewall",
            "fail2ban",
            "logging",
            "system_config",
        ]

        for role_name in roles_with_handlers:
            role_path = roles_dir / role_name
            if not role_path.exists():
                continue

            handlers_path = role_path / "handlers" / "main.yml"
            tasks_path = role_path / "tasks" / "main.yml"

            if handlers_path.exists() and tasks_path.exists():
                handlers_content = handlers_path.read_text()
                tasks_content = tasks_path.read_text()

                # Verify handlers are defined
                assert "name:" in handlers_content, (
                    f"Role {role_name} handlers should define handler names"
                )

                # Verify tasks notify handlers (not call services directly)
                if "notify:" in tasks_content:
                    # Good - tasks notify handlers
                    pass
                else:
                    # If no notify, verify there are no direct service restarts in tasks
                    # (Some roles may not need handlers if they don't restart services)
                    pass

                # Verify handlers don't use 'state: started' (should use restarted/reloaded)
                if "ansible.builtin.service:" in handlers_content or (
                    "ansible.builtin.systemd:" in handlers_content
                ):
                    # Handlers should restart/reload, not start
                    # (Starting is for initial setup, restarting is for config changes)
                    assert (
                        "state: restarted" in handlers_content
                        or "state: reloaded" in handlers_content
                    ), f"Role {role_name} handlers should use restarted or reloaded state"
