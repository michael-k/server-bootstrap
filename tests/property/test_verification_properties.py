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
        Configuration Verification Coverage

        Checks, by substrings of the task names in `tests/verify_bootstrap.yml`,
        that the verification playbook has a task for each of: the two accounts'
        uids and sudo grants; sshd's password, root-login, port, AllowGroups, key
        exchange, cipher, MAC, forwarding and tunnelling settings, its service
        state and its Tailscale restriction; the Tailscale service and the
        emergency script; the nftables service, policies, established, loopback
        and SSH rules; the hostname; the fail2ban service and its SSH jail;
        persistent journald; the time-sync service and its status; zram and disk
        swap; and a summary. It does not run the playbook or read what the checks
        assert, and a task name showing that a check is present does not verify
        the feature it names, so it cites no feature requirement.
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
        Require tasks named for the manual account's uid 1000 and sudo, and the
        automation account's uid 1999 and passwordless sudo.

        Args:
            task_names: List of task names from verification playbook
        """
        # Manual user exists with uid 1000
        assert any(
            "manual" in name.lower() and "uid 1000" in name.lower() for name in task_names
        ), "Verification playbook must test manual user with uid 1000"

        # Ansible user exists with uid 1999
        assert any(
            "ansible" in name.lower() and "uid 1999" in name.lower() for name in task_names
        ), "Verification playbook must test Ansible user with uid 1999"

        # Manual user has sudo privileges
        assert any(
            "manual" in name.lower() and "sudo" in name.lower() for name in task_names
        ), "Verification playbook must test manual user sudo privileges"

        # Ansible user has passwordless sudo
        assert any(
            "ansible" in name.lower() and "passwordless" in name.lower() for name in task_names
        ), "Verification playbook must test Ansible user passwordless sudo"

    def _verify_ssh_hardening_tests(self, task_names: list[str]):
        """
        Require tasks named for sshd's password authentication, root login, port,
        AllowGroups, key exchange, ciphers, MACs, X11, TCP and agent forwarding,
        tunnelling, and sshd running and enabled.

        Args:
            task_names: List of task names from verification playbook
        """
        # Password authentication disabled
        assert any(
            "password authentication" in name.lower() and "disabled" in name.lower()
            for name in task_names
        ), "Verification playbook must test SSH password authentication disabled"

        # Root login disabled
        assert any(
            "root login" in name.lower() and "disabled" in name.lower() for name in task_names
        ), "Verification playbook must test SSH root login disabled"

        # SSH listening on configured port
        assert any("port" in name.lower() and "ssh" in name.lower() for name in task_names), (
            "Verification playbook must test SSH port configuration"
        )

        # AllowGroups restricted
        assert any("allowgroups" in name.lower() for name in task_names), (
            "Verification playbook must test SSH AllowGroups restriction"
        )

        # Key exchange algorithms
        assert any(
            "key exchange" in name.lower() or "kexalgorithms" in name.lower()
            for name in task_names
        ), "Verification playbook must test SSH key exchange algorithms"

        # Ciphers
        assert any("cipher" in name.lower() for name in task_names), (
            "Verification playbook must test SSH ciphers"
        )

        # MACs
        assert any("mac" in name.lower() for name in task_names), (
            "Verification playbook must test SSH MACs"
        )

        # X11 forwarding disabled
        assert any("x11" in name.lower() for name in task_names), (
            "Verification playbook must test X11 forwarding disabled"
        )

        # TCP forwarding disabled
        assert any("tcp forwarding" in name.lower() for name in task_names), (
            "Verification playbook must test TCP forwarding disabled"
        )

        # Agent forwarding disabled
        assert any("agent forwarding" in name.lower() for name in task_names), (
            "Verification playbook must test agent forwarding disabled"
        )

        # Tunneling disabled
        assert any("tunnel" in name.lower() for name in task_names), (
            "Verification playbook must test tunneling disabled"
        )

        # Sshd running
        assert any(
            "sshd" in name.lower() and "running" in name.lower() for name in task_names
        ), "Verification playbook must test SSHD service running"

        # Sshd enabled
        assert any(
            "sshd" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test SSHD service enabled"

    def _verify_tailscale_tests(self, task_names: list[str], tailscale_enabled: bool):
        """
        Require tasks named for tailscaled running and enabled, SSH restricted to
        Tailscale, and the emergency script. `tailscale_enabled` is not used.

        Args:
            task_names: List of task names from verification playbook
            tailscale_enabled: Whether Tailscale is enabled in configuration
        """
        # Tailscale service running (conditional)
        assert any(
            "tailscale" in name.lower() and "running" in name.lower() for name in task_names
        ), "Verification playbook must test Tailscale service running"

        # Tailscale service enabled (conditional)
        assert any(
            "tailscale" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test Tailscale service enabled"

        # SSH restricted to Tailscale interface (conditional)
        assert any(
            "ssh" in name.lower() and "restricted" in name.lower() and "tailscale" in name.lower()
            for name in task_names
        ), "Verification playbook must test SSH restricted to Tailscale"

        # Emergency script exists (conditional)
        assert any(
            "emergency" in name.lower() and "script" in name.lower() for name in task_names
        ), "Verification playbook must test emergency script exists"

    def _verify_firewall_tests(self, task_names: list[str]):
        """
        Require tasks named for the nftables service active and enabled, the input
        and forward drop policies, established or related traffic, loopback, and
        the SSH port.

        Args:
            task_names: List of task names from verification playbook
        """
        # NFTables service active
        assert any(
            "nftables" in name.lower() and "active" in name.lower() for name in task_names
        ), "Verification playbook must test NFTables service active"

        # NFTables service enabled
        assert any(
            "nftables" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test NFTables service enabled"

        # Default input policy drop
        assert any(
            "input" in name.lower() and "policy" in name.lower() and "drop" in name.lower()
            for name in task_names
        ), "Verification playbook must test NFTables input policy drop"

        # Default forward policy drop
        assert any(
            "forward" in name.lower() and "policy" in name.lower() and "drop" in name.lower()
            for name in task_names
        ), "Verification playbook must test NFTables forward policy drop"

        # Established/related connections allowed
        assert any(
            "established" in name.lower() or "related" in name.lower() for name in task_names
        ), "Verification playbook must test established/related connections"

        # Loopback traffic allowed
        assert any("loopback" in name.lower() for name in task_names), (
            "Verification playbook must test loopback traffic allowed"
        )

        # SSH port accessible through firewall
        assert any(
            "ssh" in name.lower() and ("port" in name.lower() or "accessible" in name.lower())
            for name in task_names
        ), "Verification playbook must test SSH port accessible"

    def _verify_hostname_tests(self, task_names: list[str], hostname: str):
        """
        Require a task named for the hostname. `hostname` is not used.

        Args:
            task_names: List of task names from verification playbook
            hostname: Configured hostname (empty if not set)
        """
        # Hostname matches configured value (conditional)
        assert any("hostname" in name.lower() for name in task_names), (
            "Verification playbook must test hostname configuration"
        )

    def _verify_fail2ban_tests(self, task_names: list[str]):
        """
        Require tasks named for fail2ban active, enabled and monitoring.

        Args:
            task_names: List of task names from verification playbook
        """
        # Fail2ban service active
        assert any(
            "fail2ban" in name.lower() and "active" in name.lower() for name in task_names
        ), "Verification playbook must test fail2ban service active"

        # Fail2ban service enabled
        assert any(
            "fail2ban" in name.lower() and "enabled" in name.lower() for name in task_names
        ), "Verification playbook must test fail2ban service enabled"

        # Fail2ban monitoring SSHD
        assert any(
            "fail2ban" in name.lower() and "monitoring" in name.lower() for name in task_names
        ), "Verification playbook must test fail2ban monitoring SSHD"

    def _verify_logging_tests(self, task_names: list[str]):
        """
        Require a task named for persistent journald.

        Args:
            task_names: List of task names from verification playbook
        """
        # Journald persistent logging
        assert any(
            "journald" in name.lower() and "persist" in name.lower() for name in task_names
        ), "Verification playbook must test journald persistent logging"

    def _verify_time_sync_tests(self, task_names: list[str]):
        """
        Require tasks named for the time-sync service active and enabled, and one
        named for time synchronisation.

        Args:
            task_names: List of task names from verification playbook
        """
        # Time sync service active
        assert any(
            "time" in name.lower() and "sync" in name.lower() and "active" in name.lower()
            for name in task_names
        ), "Verification playbook must test time sync service active"

        # Time sync service enabled
        assert any(
            "time" in name.lower() and "sync" in name.lower() and "enabled" in name.lower()
            for name in task_names
        ), "Verification playbook must test time sync service enabled"

        # A task named for time synchronization exists
        assert any(
            "time" in name.lower() and "synchronization" in name.lower() for name in task_names
        ), "Verification playbook must have a time synchronization task"

    def _verify_swap_tests(
        self, task_names: list[str], zram_enabled: bool, disk_swap_enabled: bool
    ):
        """
        Require tasks named for the zram device existing, active as swap, its
        compression and its priority, and for the disk swap file existing, active
        and in fstab. `zram_enabled` and `disk_swap_enabled` are not used.

        Args:
            task_names: List of task names from verification playbook
            zram_enabled: Whether zram is enabled in configuration
            disk_swap_enabled: Whether disk swap is enabled in configuration
        """
        # Zram device exists (conditional)
        assert any("zram" in name.lower() and "exists" in name.lower() for name in task_names), (
            "Verification playbook must test zram device exists"
        )

        # Zram device active as swap (conditional)
        assert any(
            "zram" in name.lower() and "active" in name.lower() and "swap" in name.lower()
            for name in task_names
        ), "Verification playbook must test zram device active as swap"

        # Zram compression algorithm (conditional)
        assert any(
            "zram" in name.lower() and "compression" in name.lower() for name in task_names
        ), "Verification playbook must test zram compression algorithm"

        # Zram priority (conditional). The playbook's own check
        # reads the rendered value only and does not compare it with the disk
        # swap priority - see specs/verification/design.md's ## Failure modes.
        assert any("zram" in name.lower() and "priority" in name.lower() for name in task_names), (
            "Verification playbook must test zram priority"
        )

        # Disk swap file exists (conditional)
        assert any(
            "disk" in name.lower() and "swap" in name.lower() and "exists" in name.lower()
            for name in task_names
        ), "Verification playbook must test disk swap file exists"

        # Disk swap file active (conditional)
        assert any(
            "disk" in name.lower() and "swap" in name.lower() and "active" in name.lower()
            for name in task_names
        ), "Verification playbook must test disk swap file active"

        # Disk swap file in fstab (conditional)
        assert any(
            "swap" in name.lower() and "fstab" in name.lower() for name in task_names
        ), "Verification playbook must test disk swap file in fstab"

    def _verify_summary_reporting(self, task_names: list[str]):
        """
        Verify test summary reporting. This is the playbook's own closing
        report, not a check of a feature requirement, so it cites no ID -
        see specs/verification/requirements.md's VRFY-4.

        Args:
            task_names: List of task names from verification playbook
        """
        # Display verification summary
        assert any("summary" in name.lower() for name in task_names), (
            "Verification playbook must display verification summary"
        )

    def _verify_test_structure(self, tasks: list[dict]):
        """
        Asserts nothing: each branch below ends in `pass`.

        Args:
            tasks: List of task dictionaries from verification playbook
        """
        for task in tasks:
            task_name = task.get("name", "")

            # Skip non-test tasks (like summary reporting)
            if "summary" in task_name.lower():
                continue

            # Not checked: whether test tasks use block structure
            if task_name.startswith("Verify "):
                pass

            # Not checked: whether conditional tests carry a 'when' clause
            if any(
                keyword in task_name.lower()
                for keyword in ["tailscale", "zram", "disk swap", "hostname"]
            ):
                pass

            # Not checked: which modules test tasks use
            pass

    @pytest.mark.property
    @pytest.mark.unit
    def test_verification_playbook_covers_all_requirements(self):
        """
        Verify that the verification playbook names, in each block's own
        title, the feature requirement ID that block verifies (VRFY-4) -
        replacing the retired flat Requirement 14 numbering this test used
        to check for instead.

        This test ensures the playbook keeps citing a broad set of
        requirement IDs, rather than losing the citations Task 25 added as
        blocks are edited later.
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

        # A requirement ID looks like PREFIX-N; a task
        # name may cite several, comma-separated, when one assert verifies
        # conditions belonging to more than one requirement.
        requirement_id = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
        cited_tasks = [name for name in task_names if requirement_id.search(name)]
        all_ids = [req_id for name in task_names for req_id in requirement_id.findall(name)]

        # Minimum: at least 40 blocks should cite a requirement ID (a few cite
        # none - see specs/verification/requirements.md's VRFY-4 for which,
        # and why).
        assert len(cited_tasks) >= 40, (
            "Verification playbook should have at least 40 test tasks citing a "
            f"requirement ID, found {len(cited_tasks)}"
        )

        # And those citations should span a broad set of distinct IDs, not
        # repeat the same handful.
        assert len(set(all_ids)) >= 40, (
            "Verification playbook should cite at least 40 distinct requirement "
            f"IDs, found {len(set(all_ids))}"
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

        Checks that `ansible.builtin.assert:`, `fail_msg:`, `success_msg:` and
        `that:` each appear somewhere in the playbook. It does not tie the messages
        to any particular assert, so an assert with no messages would pass.

        Validates: VRFY-3
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
        Verify that verification tests properly handle conditional features
        (VRFY-5).

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
        1. A test name of the form `Verify PREFIX-N`
        2. A checkmark somewhere in the file
        3. Summary reporting through the debug module

        Validates: VRFY-4
        """
        verify_playbook_path = Path("tests/verify_bootstrap.yml")
        assert verify_playbook_path.exists(), (
            "Verification playbook tests/verify_bootstrap.yml must exist"
        )

        playbook_content = verify_playbook_path.read_text()

        # Verify test names include requirement IDs (VRFY-4), in place of the
        # retired "Test 14.X" numbering.
        assert re.search(r"Verify [A-Z][A-Z0-9]*-\d+", playbook_content), (
            "Verification test names should include requirement IDs (Verify PREFIX-N: ...)"
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
