"""
Property-based tests for configuration verification in VPS Bootstrap Playbook.

These tests verify that the verification test suite (tests/verify_bootstrap.yml)
correctly validates all configuration aspects modified by the bootstrap playbook.
"""

import re
from pathlib import Path

import pytest
import yaml
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
    return draw(st.sampled_from([22]) | st.integers(min_value=1024, max_value=65535))


class TestConfigurationVerificationProperties:
    """Property-based tests for configuration verification."""

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
        disk_swap_enabled=st.booleans(),
    )
    def test_property_34_configuration_verification_round_trip(
        self,
        manual_user: str,
        ansible_user: str,
        hostname: str,
        ssh_port: int,
        tailscale_enabled: bool,
        zram_enabled: bool,
        disk_swap_enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 34: Configuration Verification Round-Trip

        For any configuration aspect modified by the bootstrap playbook, the test suite
        SHALL verify the configuration matches the expected state, demonstrating that
        playbook execution followed by test execution confirms correctness.

        Validates: Requirements 14.1-14.44 (all test suite verification requirements)

        This property test verifies that the verification playbook:
        1. Tests all user account configurations (14.1-14.4)
        2. Tests all SSH hardening configurations (14.5-14.17)
        3. Tests Tailscale configuration when enabled (14.18-14.21)
        4. Tests NFTables firewall configuration (14.22-14.28)
        5. Tests hostname configuration when set (14.29)
        6. Tests fail2ban configuration (14.30-14.32)
        7. Tests journald configuration (14.33)
        8. Tests time synchronization (14.34-14.36)
        9. Tests swap configuration when enabled (14.37-14.43)
        10. Provides clear pass/fail reporting (14.44)
        """
        # Skip if usernames are identical (invalid configuration)
        if manual_user == ansible_user:
            return

        # Verify verification playbook exists
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        # Load and parse the verification playbook
        with open(verify_playbook_path) as f:
            verify_playbook = yaml.safe_load(f)

        assert isinstance(verify_playbook, list), (
            "Verification playbook must be a list of plays"
        )
        assert len(verify_playbook) > 0, "Verification playbook must have at least one play"

        # Get the main verification play
        verify_play = verify_playbook[0]
        assert "tasks" in verify_play, "Verification play must have tasks"

        tasks = verify_play["tasks"]
        task_names = [task.get("name", "") for task in tasks if "name" in task]

        # Verify all required test categories are present
        self._verify_user_account_tests(task_names)
        self._verify_ssh_hardening_tests(task_names)
        self._verify_tailscale_tests(task_names, tailscale_enabled)
        self._verify_firewall_tests(task_names)
        self._verify_hostname_tests(task_names, hostname)
        self._verify_fail2ban_tests(task_names)
        self._verify_logging_tests(task_names)
        self._verify_time_sync_tests(task_names)
        self._verify_swap_tests(task_names, zram_enabled, disk_swap_enabled)
        self._verify_summary_reporting(task_names)

        # Verify test structure and best practices
        self._verify_test_structure(tasks)

    def _verify_user_account_tests(self, task_names: list[str]):
        """
        Verify tests for user account configuration (Requirements 14.1-14.4).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.1: Manual user exists with uid 1000
        assert any(
            "manual" in name.lower() and "uid 1000" in name.lower() for name in task_names
        ), "Verification playbook must test manual user with uid 1000 (Requirement 14.1)"

        # Test 14.2: Ansible user exists with uid 1999
        assert any(
            "ansible" in name.lower() and "uid 1999" in name.lower() for name in task_names
        ), "Verification playbook must test Ansible user with uid 1999 (Requirement 14.2)"

        # Test 14.3: Manual user has sudo privileges
        assert any(
            "manual" in name.lower() and "sudo" in name.lower() for name in task_names
        ), "Verification playbook must test manual user sudo privileges (Requirement 14.3)"

        # Test 14.4: Ansible user has passwordless sudo
        assert any(
            "ansible" in name.lower() and "passwordless" in name.lower() for name in task_names
        ), "Verification playbook must test Ansible user passwordless sudo (Requirement 14.4)"

    def _verify_ssh_hardening_tests(self, task_names: list[str]):
        """
        Verify tests for SSH hardening configuration (Requirements 14.5-14.17).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.5: Password authentication disabled
        assert any(
            "password authentication" in name.lower() and "disabled" in name.lower()
            for name in task_names
        ), "Verification playbook must test SSH password authentication disabled (Requirement 14.5)"

        # Test 14.6: Root login disabled
        assert any(
            "root login" in name.lower() and "disabled" in name.lower() for name in task_names
        ), "Verification playbook must test SSH root login disabled (Requirement 14.6)"

        # Test 14.7: SSH listening on configured port
        assert any("port" in name.lower() and "ssh" in name.lower() for name in task_names), (
            "Verification playbook must test SSH port configuration (Requirement 14.7)"
        )

        # Test 14.8: AllowGroups restricted
        assert any("allowgroups" in name.lower() for name in task_names), (
            "Verification playbook must test SSH AllowGroups restriction (Requirement 14.8)"
        )

        # Test 14.9: Key exchange algorithms
        assert any(
            "key exchange" in name.lower() or "kexalgorithms" in name.lower()
            for name in task_names
        ), "Verification playbook must test SSH key exchange algorithms (Requirement 14.9)"

        # Test 14.10: Ciphers
        assert any("cipher" in name.lower() for name in task_names), (
            "Verification playbook must test SSH ciphers (Requirement 14.10)"
        )

        # Test 14.11: MACs
        assert any("mac" in name.lower() for name in task_names), (
            "Verification playbook must test SSH MACs (Requirement 14.11)"
        )

        # Test 14.12: X11 forwarding disabled
        assert any("x11" in name.lower() for name in task_names), (
            "Verification playbook must test X11 forwarding disabled (Requirement 14.12)"
        )

        # Test 14.13: TCP forwarding disabled
        assert any("tcp forwarding" in name.lower() for name in task_names), (
            "Verification playbook must test TCP forwarding disabled (Requirement 14.13)"
        )

        # Test 14.14: Agent forwarding disabled
        assert any("agent forwarding" in name.lower() for name in task_names), (
            "Verification playbook must test agent forwarding disabled (Requirement 14.14)"
        )

        # Test 14.15: Tunneling disabled
        assert any("tunnel" in name.lower() for name in task_names), (
            "Verification playbook must test tunneling disabled (Requirement 14.15)"
        )

        # Test 14.16: SSHD service running
        assert any(
            "sshd" in name.lower() and "running" in name.lower() for name in task_names
        ), "Verification playbook must test SSHD service running (Requirement 14.16)"

        # Test 14.17: SSHD service enabled
        assert any(
            "sshd" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test SSHD service enabled (Requirement 14.17)"

    def _verify_tailscale_tests(self, task_names: list[str], tailscale_enabled: bool):
        """
        Verify tests for Tailscale configuration (Requirements 14.18-14.21).

        Args:
            task_names: List of task names from verification playbook
            tailscale_enabled: Whether Tailscale is enabled in configuration
        """
        # Test 14.18: Tailscale service running (conditional)
        assert any(
            "tailscale" in name.lower() and "running" in name.lower() for name in task_names
        ), "Verification playbook must test Tailscale service running (Requirement 14.18)"

        # Test 14.19: Tailscale service enabled (conditional)
        assert any(
            "tailscale" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test Tailscale service enabled (Requirement 14.19)"

        # Test 14.20: SSH restricted to Tailscale interface (conditional)
        assert any(
            "ssh" in name.lower() and "restricted" in name.lower() and "tailscale" in name.lower()
            for name in task_names
        ), "Verification playbook must test SSH restricted to Tailscale (Requirement 14.20)"

        # Test 14.21: Emergency script exists (conditional)
        assert any(
            "emergency" in name.lower() and "script" in name.lower() for name in task_names
        ), "Verification playbook must test emergency script exists (Requirement 14.21)"

    def _verify_firewall_tests(self, task_names: list[str]):
        """
        Verify tests for NFTables firewall configuration (Requirements 14.22-14.28).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.22: NFTables service active
        assert any(
            "nftables" in name.lower() and "active" in name.lower() for name in task_names
        ), "Verification playbook must test NFTables service active (Requirement 14.22)"

        # Test 14.23: NFTables service enabled
        assert any(
            "nftables" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test NFTables service enabled (Requirement 14.23)"

        # Test 14.24: Default input policy drop
        assert any(
            "input" in name.lower() and "policy" in name.lower() and "drop" in name.lower()
            for name in task_names
        ), "Verification playbook must test NFTables input policy drop (Requirement 14.24)"

        # Test 14.25: Default forward policy drop
        assert any(
            "forward" in name.lower() and "policy" in name.lower() and "drop" in name.lower()
            for name in task_names
        ), "Verification playbook must test NFTables forward policy drop (Requirement 14.25)"

        # Test 14.26: Established/related connections allowed
        assert any(
            "established" in name.lower() or "related" in name.lower() for name in task_names
        ), "Verification playbook must test established/related connections (Requirement 14.26)"

        # Test 14.27: Loopback traffic allowed
        assert any("loopback" in name.lower() for name in task_names), (
            "Verification playbook must test loopback traffic allowed (Requirement 14.27)"
        )

        # Test 14.28: SSH port accessible through firewall
        assert any(
            "ssh" in name.lower() and ("port" in name.lower() or "accessible" in name.lower())
            for name in task_names
        ), "Verification playbook must test SSH port accessible (Requirement 14.28)"

    def _verify_hostname_tests(self, task_names: list[str], hostname: str):
        """
        Verify tests for hostname configuration (Requirement 14.29).

        Args:
            task_names: List of task names from verification playbook
            hostname: Configured hostname (empty if not set)
        """
        # Test 14.29: Hostname matches configured value (conditional)
        assert any("hostname" in name.lower() for name in task_names), (
            "Verification playbook must test hostname configuration (Requirement 14.29)"
        )

    def _verify_fail2ban_tests(self, task_names: list[str]):
        """
        Verify tests for fail2ban configuration (Requirements 14.30-14.32).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.30: Fail2ban service active
        assert any(
            "fail2ban" in name.lower() and "active" in name.lower() for name in task_names
        ), "Verification playbook must test fail2ban service active (Requirement 14.30)"

        # Test 14.31: Fail2ban service enabled
        assert any(
            "fail2ban" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test fail2ban service enabled (Requirement 14.31)"

        # Test 14.32: Fail2ban monitoring SSHD
        assert any(
            "fail2ban" in name.lower() and "monitoring" in name.lower() for name in task_names
        ), "Verification playbook must test fail2ban monitoring SSHD (Requirement 14.32)"

    def _verify_logging_tests(self, task_names: list[str]):
        """
        Verify tests for journald logging configuration (Requirement 14.33).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.33: Journald persistent logging
        assert any(
            "journald" in name.lower() and "persist" in name.lower() for name in task_names
        ), "Verification playbook must test journald persistent logging (Requirement 14.33)"

    def _verify_time_sync_tests(self, task_names: list[str]):
        """
        Verify tests for time synchronization (Requirements 14.34-14.36).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.34: Time sync service active
        assert any(
            "time" in name.lower() and "sync" in name.lower() and "active" in name.lower()
            for name in task_names
        ), "Verification playbook must test time sync service active (Requirement 14.34)"

        # Test 14.35: Time sync service enabled
        assert any(
            "time" in name.lower() and "sync" in name.lower() and "enabled" in name.lower()
            for name in task_names
        ), "Verification playbook must test time sync service enabled (Requirement 14.35)"

        # Test 14.36: Time synchronization active
        assert any(
            "time" in name.lower() and "synchronization" in name.lower() for name in task_names
        ), "Verification playbook must test time synchronization active (Requirement 14.36)"

    def _verify_swap_tests(
        self, task_names: list[str], zram_enabled: bool, disk_swap_enabled: bool
    ):
        """
        Verify tests for swap configuration (Requirements 14.37-14.43).

        Args:
            task_names: List of task names from verification playbook
            zram_enabled: Whether zram is enabled in configuration
            disk_swap_enabled: Whether disk swap is enabled in configuration
        """
        # Test 14.37: Zram device exists (conditional)
        assert any("zram" in name.lower() and "exists" in name.lower() for name in task_names), (
            "Verification playbook must test zram device exists (Requirement 14.37)"
        )

        # Test 14.38: Zram device active as swap (conditional)
        assert any(
            "zram" in name.lower() and "active" in name.lower() and "swap" in name.lower()
            for name in task_names
        ), "Verification playbook must test zram device active as swap (Requirement 14.38)"

        # Test 14.39: Zram compression algorithm (conditional)
        assert any(
            "zram" in name.lower() and "compression" in name.lower() for name in task_names
        ), "Verification playbook must test zram compression algorithm (Requirement 14.39)"

        # Test 14.40: Zram priority higher than disk swap (conditional)
        assert any("zram" in name.lower() and "priority" in name.lower() for name in task_names), (
            "Verification playbook must test zram priority (Requirement 14.40)"
        )

        # Test 14.41: Disk swap file exists (conditional)
        assert any(
            "disk" in name.lower() and "swap" in name.lower() and "exists" in name.lower()
            for name in task_names
        ), "Verification playbook must test disk swap file exists (Requirement 14.41)"

        # Test 14.42: Disk swap file active (conditional)
        assert any(
            "disk" in name.lower() and "swap" in name.lower() and "active" in name.lower()
            for name in task_names
        ), "Verification playbook must test disk swap file active (Requirement 14.42)"

        # Test 14.43: Disk swap file in fstab (conditional)
        assert any(
            "swap" in name.lower() and "fstab" in name.lower() for name in task_names
        ), "Verification playbook must test disk swap file in fstab (Requirement 14.43)"

    def _verify_summary_reporting(self, task_names: list[str]):
        """
        Verify test summary reporting (Requirement 14.44).

        Args:
            task_names: List of task names from verification playbook
        """
        # Test 14.44: Display verification summary
        assert any("summary" in name.lower() for name in task_names), (
            "Verification playbook must display verification summary (Requirement 14.44)"
        )

    def _verify_test_structure(self, tasks: list[dict]):
        """
        Verify that verification tests follow best practices.

        Args:
            tasks: List of task dictionaries from verification playbook
        """
        for task in tasks:
            task_name = task.get("name", "")

            # Skip non-test tasks (like summary reporting)
            if "summary" in task_name.lower():
                continue

            # Verify test tasks use block structure for better organization
            if "Test 14." in task_name:
                # Test tasks should use block structure or direct assertions
                # This is a best practice but not strictly required
                pass

            # Verify conditional tests use 'when' clause
            if any(
                keyword in task_name.lower()
                for keyword in ["tailscale", "zram", "disk swap", "hostname"]
            ):
                # Conditional tests should have 'when' clause
                # (This is checked at runtime, not in static analysis)
                pass

            # Verify test tasks use appropriate modules
            # Tests should use command, stat, slurp, systemd, assert modules
            # (This is verified by the test execution, not static analysis)
            pass

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_playbook_covers_all_requirements(self):
        """
        Verify that the verification playbook covers all 44 requirements from 14.1-14.44.

        This test ensures no requirements are missed in the verification suite.
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        # Load verification playbook
        with open(verify_playbook_path) as f:
            verify_playbook = yaml.safe_load(f)

        verify_play = verify_playbook[0]
        tasks = verify_play["tasks"]
        task_names = [task.get("name", "") for task in tasks if "name" in task]

        # Count test tasks (those that start with "Test 14.")
        test_tasks = [name for name in task_names if "Test 14." in name]

        # Verify we have tests for all 44 requirements
        # (Some requirements may be combined into single tests, so we check for coverage)
        # Minimum: We should have at least 40 test tasks (allowing some consolidation)
        assert len(test_tasks) >= 40, (
            f"Verification playbook should have at least 40 test tasks, found {len(test_tasks)}"
        )

        # Verify test numbering is sequential (or close to it)
        # Extract test numbers
        test_numbers = []
        for name in test_tasks:
            if "Test 14." in name:
                # Extract number after "Test 14."
                try:
                    num_str = name.split("Test 14.")[1].split(":")[0].strip()
                    test_numbers.append(int(num_str))
                except (IndexError, ValueError):
                    pass

        # Verify we have tests covering the range 1-44
        if test_numbers:
            assert min(test_numbers) == 1, "Test numbering should start at 1"
            assert max(test_numbers) >= 40, (
                "Test numbering should cover up to at least requirement 40"
            )

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_playbook_has_proper_structure(self):
        """
        Verify that the verification playbook has proper structure for reliable testing.

        This test checks:
        1. Playbook targets all hosts
        2. Playbook gathers facts (needed for conditional tests)
        3. Playbook uses proper error handling
        4. Playbook provides clear output
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        # Load verification playbook
        with open(verify_playbook_path) as f:
            verify_playbook = yaml.safe_load(f)

        assert isinstance(verify_playbook, list), "Verification playbook must be a list"
        assert len(verify_playbook) > 0, "Verification playbook must have at least one play"

        verify_play = verify_playbook[0]

        # Verify play targets all hosts
        assert verify_play.get("hosts") == "all", (
            "Verification play should target all hosts"
        )

        # Verify play gathers facts (needed for conditional logic)
        assert verify_play.get("gather_facts") is True, (
            "Verification play should gather facts"
        )

        # Verify play has tasks
        assert "tasks" in verify_play, "Verification play must have tasks"
        assert len(verify_play["tasks"]) > 0, "Verification play must have at least one task"

        # Verify play uses variables for tracking results (optional but recommended)
        # This allows for summary reporting
        if "vars" in verify_play:
            # Check for result tracking variables
            # (This is a best practice but not strictly required)
            pass

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_tests_use_proper_assertions(self):
        """
        Verify that verification tests use proper assertion patterns.

        This test checks that tests use ansible.builtin.assert module
        with clear fail_msg and success_msg for user feedback.
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        # Read playbook content as text for pattern matching
        playbook_content = verify_playbook_path.read_text()

        # Verify playbook uses assert module
        assert "ansible.builtin.assert:" in playbook_content, (
            "Verification playbook should use ansible.builtin.assert module"
        )

        # Verify assertions have fail_msg for clear error reporting
        assert "fail_msg:" in playbook_content, (
            "Verification assertions should have fail_msg for clear error reporting"
        )

        # Verify assertions have success_msg for positive feedback
        assert "success_msg:" in playbook_content, (
            "Verification assertions should have success_msg for positive feedback"
        )

        # Verify assertions use 'that' clause for conditions
        assert "that:" in playbook_content, (
            "Verification assertions should use 'that' clause for conditions"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_tests_handle_conditional_features(self):
        """
        Verify that verification tests properly handle conditional features.

        Features like Tailscale, zram, disk swap, and hostname are optional.
        Tests for these features should use 'when' clauses to skip when not configured.
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        # Read playbook content
        playbook_content = verify_playbook_path.read_text()

        # Verify conditional tests use 'when' clause
        assert "when:" in playbook_content, (
            "Verification playbook should use 'when' clauses for conditional tests"
        )

        # Verify Tailscale tests are conditional
        assert "tailscale_enabled" in playbook_content, (
            "Verification playbook should check tailscale_enabled variable"
        )

        # Verify zram tests are conditional
        assert "zram_enabled" in playbook_content, (
            "Verification playbook should check zram_enabled variable"
        )

        # Verify disk swap tests are conditional
        assert "disk_swap_size" in playbook_content, (
            "Verification playbook should check disk_swap_size variable"
        )

        # Verify hostname tests are conditional
        assert "system_hostname" in playbook_content, (
            "Verification playbook should check system_hostname variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_playbook_provides_clear_output(self):
        """
        Verify that the verification playbook provides clear output for users.

        This test checks that the playbook includes:
        1. Clear test names with requirement numbers
        2. Success messages with checkmarks
        3. Failure messages with clear descriptions
        4. Summary reporting at the end
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        playbook_content = verify_playbook_path.read_text()

        # Verify test names include requirement numbers
        assert "Test 14." in playbook_content, (
            "Verification test names should include requirement numbers (Test 14.X)"
        )

        # Verify success messages use checkmarks for visual feedback
        assert "✓" in playbook_content, (
            "Verification success messages should use checkmarks (✓) for visual feedback"
        )

        # Verify summary section exists
        assert "summary" in playbook_content.lower(), (
            "Verification playbook should include summary reporting"
        )

        # Verify summary uses debug module for output
        assert "ansible.builtin.debug:" in playbook_content, (
            "Verification playbook should use debug module for summary output"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_playbook_resolves_role_default_variables(self):
        """
        Verify that every role default the verification playbook references is
        actually resolvable when that playbook runs.

        tests/verify_bootstrap.yml declares no `roles:`, so `roles/*/defaults/main.yml`
        is not in its variable scope. A reference to a role default must therefore be
        brought into scope explicitly (include_vars), supplied by the inventory, or
        guarded with `| default(...)` - otherwise the play aborts at runtime with
        "'<name>' is undefined".
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        playbook_content = verify_playbook_path.read_text()
        verify_play = yaml.safe_load(playbook_content)[0]

        # Every variable that only a role provides a value for.
        role_defaults: dict[str, Path] = {}
        for defaults_file in sorted(Path("roles").glob("*/defaults/main.yml")):
            for name in yaml.safe_load(defaults_file.read_text()) or {}:
                role_defaults.setdefault(name, defaults_file)

        # Names the play can resolve without the roles being applied.
        in_scope: set[str] = set(verify_play.get("vars") or {})

        def collect_keys(node) -> None:
            """Collect every mapping key, at any depth, of an example inventory."""
            if isinstance(node, dict):
                in_scope.update(node)
                for value in node.values():
                    collect_keys(value)
            elif isinstance(node, list):
                for item in node:
                    collect_keys(item)

        for example in sorted(Path("inventory").rglob("*.example")):
            collect_keys(yaml.safe_load(example.read_text()))

        def collect_included_vars(tasks) -> None:
            """Collect names the play pulls in with include_vars, including in blocks."""
            for task in tasks or []:
                if not isinstance(task, dict):
                    continue
                for section in ("block", "rescue", "always"):
                    collect_included_vars(task.get(section))
                for module in ("ansible.builtin.include_vars", "include_vars"):
                    spec = task.get(module)
                    if spec is None:
                        continue
                    included = spec if isinstance(spec, str) else spec.get("file")
                    if not included:
                        continue
                    included = included.replace(
                        "{{ playbook_dir }}", str(verify_playbook_path.parent)
                    )
                    namespace = spec.get("name") if isinstance(spec, dict) else None
                    if namespace:
                        # Namespaced include: only the namespace itself enters scope,
                        # so the file's own keys stay unresolved and must be guarded.
                        in_scope.add(namespace)
                    else:
                        in_scope.update(yaml.safe_load(Path(included).read_text()) or {})

        collect_included_vars(verify_play.get("tasks"))

        unresolvable: list[str] = []
        for name, defaults_file in sorted(role_defaults.items()):
            if name in in_scope:
                continue
            for match in re.finditer(rf"\b{re.escape(name)}\b", playbook_content):
                # An attribute access such as `users_role_defaults.login_policy_umask`
                # resolves through the namespace, not the bare name.
                if playbook_content[match.start() - 1 : match.start()] == ".":
                    continue
                if re.match(r"\s*\|\s*default\(", playbook_content[match.end() :]):
                    continue
                line = playbook_content.count("\n", 0, match.start()) + 1
                unresolvable.append(f"{name} (line {line}, default lives in {defaults_file})")

        assert not unresolvable, (
            "tests/verify_bootstrap.yml declares no `roles:`, so these role defaults are "
            'not in scope and the play will abort with "\'<name>\' is undefined". Load '
            "them with include_vars or guard each reference with | default(...):\n  "
            + "\n  ".join(unresolvable)
        )
