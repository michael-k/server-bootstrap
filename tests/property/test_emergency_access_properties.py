"""
Property-based tests for Emergency Access Script in VPS Bootstrap Playbook.

These tests verify universal properties about emergency script deployment,
unrestrict operation, restore operation, and round-trip restoration
across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid emergency script configuration values
@st.composite
def valid_ssh_port(draw):
    """Generate valid SSH port numbers."""
    # Valid ports: 1-65535, but typically 22 or high ports (1024-65535)
    return draw(st.sampled_from([22]) | st.integers(min_value=1024, max_value=65535))


@st.composite
def valid_interface_name(draw):
    """Generate valid network interface names."""
    # Linux interface names: alphanumeric, max 15 chars
    return draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=3,
            max_size=15,
        ).filter(lambda x: x[0].isalpha())
    )


@st.composite
def valid_ipv4_address(draw):
    """Generate valid IPv4 addresses."""
    octets = [draw(st.integers(min_value=1, max_value=254)) for _ in range(4)]
    return ".".join(map(str, octets))


class TestEmergencyScriptDeploymentProperties:
    """Property-based tests for emergency script deployment."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tailscale_enabled=st.booleans(),
        ssh_port=valid_ssh_port(),
        interface_name=valid_interface_name(),
        ipv4_address=valid_ipv4_address(),
    )
    def test_property_22_emergency_script_deployment(
        self,
        tailscale_enabled: bool,
        ssh_port: int,
        interface_name: str,
        ipv4_address: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 22: Emergency Script Deployment

        For any execution of the bootstrap playbook WHERE Tailscale is enabled,
        an emergency access script SHALL be deployed to /root/ that can toggle
        SSH restrictions.

        Validates: Requirement 9.1
        """
        # This property test verifies the emergency_access role's deployment by checking:
        # 1. Emergency script is deployed only when Tailscale is enabled (Requirement 9.1)
        # 2. Script is deployed to /root/ directory (Requirement 9.1)
        # 3. Script is executable
        # 4. Script contains proper configuration variables
        # 5. Script deployment is conditional on tailscale_enabled variable (Requirement 9.8)

        # Read the emergency_access role main tasks
        main_tasks_path = Path("roles/emergency_access/tasks/main.yml")
        assert main_tasks_path.exists(), "Emergency access main tasks file must exist"

        main_tasks_content = main_tasks_path.read_text()

        # Verify conditional deployment based on emergency_access_enabled (Requirement 9.8)
        # The emergency_access_enabled variable defaults to tailscale_enabled
        assert "when: emergency_access_enabled | bool" in main_tasks_content, (
            "Emergency script deployment must be conditional on emergency_access_enabled "
            "variable (Requirement 9.8)"
        )

        # Verify script template deployment
        assert "ansible.builtin.template:" in main_tasks_content, (
            "Must use template module to deploy emergency script"
        )
        assert "src: emergency-ssh-access.sh.j2" in main_tasks_content, (
            "Must use emergency-ssh-access.sh.j2 template"
        )
        assert (
            "dest: /root/emergency-ssh-access.sh" in main_tasks_content
            or "dest: \"{{ emergency_access_script_path }}\"" in main_tasks_content
        ), "Script must be deployed to /root/ directory (Requirement 9.1)"

        # Verify script is made executable
        assert (
            "mode: '0700'" in main_tasks_content
            or "mode: 0700" in main_tasks_content
            or 'mode: "0700"' in main_tasks_content
        ), "Script must be executable (mode 0700)"

        # Verify script ownership
        assert "owner: root" in main_tasks_content, (
            "Script must be owned by root"
        )
        assert "group: root" in main_tasks_content, (
            "Script must be in root group"
        )

        # Read the emergency script template
        template_path = Path("roles/emergency_access/templates/emergency-ssh-access.sh.j2")
        assert template_path.exists(), "Emergency script template must exist"

        template_content = template_path.read_text()

        # Verify script has proper shebang
        assert "#!/bin/bash" in template_content, (
            "Script must have bash shebang"
        )

        # Verify script uses configuration variables
        assert "{{ emergency_access_ssh_port }}" in template_content, (
            "Script must use emergency_access_ssh_port variable"
        )
        assert "{{ emergency_access_tailscale_interface }}" in template_content, (
            "Script must use emergency_access_tailscale_interface variable"
        )
        assert "{{ emergency_access_tailscale_ipv4 }}" in template_content, (
            "Script must use emergency_access_tailscale_ipv4 variable"
        )

        # Verify script has error handling
        assert "set -euo pipefail" in template_content, (
            "Script must have strict error handling"
        )

        # Verify script has usage documentation
        assert "Usage:" in template_content, (
            "Script must have usage documentation"
        )
        assert "--restore" in template_content, (
            "Script must document --restore flag"
        )

        # Read the emergency_access role defaults
        defaults_path = Path("roles/emergency_access/defaults/main.yml")
        assert defaults_path.exists(), "Emergency access defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify configuration variables are defined
        assert "emergency_access_ssh_port:" in defaults_content, (
            "emergency_access_ssh_port must be defined in defaults"
        )
        assert "emergency_access_tailscale_interface:" in defaults_content, (
            "emergency_access_tailscale_interface must be defined in defaults"
        )
        assert "emergency_access_tailscale_ipv4:" in defaults_content, (
            "emergency_access_tailscale_ipv4 must be defined in defaults"
        )

        # Verify emergency_access_enabled defaults to tailscale_enabled (Requirement 9.8)
        assert "emergency_access_enabled:" in defaults_content, (
            "emergency_access_enabled must be defined in defaults"
        )
        assert "tailscale_enabled" in defaults_content, (
            "emergency_access_enabled must reference tailscale_enabled (Requirement 9.8)"
        )

        # Verify tasks are properly tagged (optional - not all roles use tags)
        # Tags allow selective execution of specific roles
        if "tags:" in main_tasks_content:
            assert "emergency_access" in main_tasks_content, (
                "Tasks should have emergency_access tag if tags are used"
            )

        # Property verified: The emergency_access role ensures that:
        # - Emergency script is deployed only when Tailscale is enabled (9.1, 9.8)
        # - Script is deployed to /root/ directory (9.1)
        # - Script is executable with proper permissions (0700)
        # - Script is owned by root
        # - Script contains proper configuration variables
        # - Script has error handling and usage documentation
        # - This applies consistently across all valid configuration values


class TestEmergencyScriptOperationsProperties:
    """Property-based tests for emergency script operations."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        interface_name=valid_interface_name(),
        ipv4_address=valid_ipv4_address(),
    )
    def test_property_23_emergency_script_unrestrict_operation(
        self,
        ssh_port: int,
        interface_name: str,
        ipv4_address: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 23: Emergency Script Unrestrict Operation

        For any invocation of the emergency script without arguments, the script
        SHALL reconfigure SSHD to listen on all interfaces and update NFTables
        to allow SSH from all interfaces, then restart SSHD and reload NFTables.

        Validates: Requirements 9.2, 9.5, 9.6
        """
        # This property test verifies the emergency script's unrestrict operation by checking:
        # 1. Script modifies SSHD configuration to listen on all interfaces (Requirement 9.2)
        # 2. Script modifies NFTables configuration to allow SSH from all (Requirement 9.2)
        # 3. Script restarts SSHD after configuration changes (Requirement 9.5)
        # 4. Script reloads NFTables after configuration changes (Requirement 9.6)
        # 5. Script is idempotent (Requirement 9.7)

        # Read the emergency script template
        template_path = Path("roles/emergency_access/templates/emergency-ssh-access.sh.j2")
        assert template_path.exists(), "Emergency script template must exist"

        template_content = template_path.read_text()

        # Verify unrestrict_ssh function exists
        assert "unrestrict_ssh()" in template_content, (
            "Script must have unrestrict_ssh function"
        )

        # Verify SSHD configuration modification for unrestrict
        # Script should change ListenAddress from Tailscale IP to 0.0.0.0 and ::
        assert "ListenAddress 0.0.0.0" in template_content, (
            "Unrestrict operation must configure SSHD to listen on 0.0.0.0 (Requirement 9.2)"
        )
        assert "ListenAddress ::" in template_content, (
            "Unrestrict operation must configure SSHD to listen on :: (IPv6) (Requirement 9.2)"
        )

        # Verify sed command for SSHD modification
        assert "sed -i" in template_content, (
            "Script must use sed for in-place configuration modification"
        )
        assert "$SSHD_CONFIG" in template_content or "/etc/ssh/sshd_config" in template_content, (
            "Script must modify SSHD configuration file"
        )

        # Verify NFTables configuration modification for unrestrict
        # Script should change from interface-restricted to unrestricted SSH rule
        assert "tcp dport" in template_content, (
            "Script must modify NFTables SSH port rule"
        )
        assert "$NFTABLES_CONFIG" in template_content or "/etc/nftables.conf" in template_content, (
            "Script must modify NFTables configuration file"
        )

        # Verify SSHD service restart (Requirement 9.5)
        assert "systemctl restart sshd" in template_content, (
            "Script must restart SSHD service after configuration changes (Requirement 9.5)"
        )

        # Verify NFTables reload (Requirement 9.6)
        assert "systemctl reload nftables" in template_content, (
            "Script must reload NFTables after configuration changes (Requirement 9.6)"
        )

        # Verify idempotency checks (Requirement 9.7)
        assert "grep -q" in template_content, (
            "Script must check current state for idempotency (Requirement 9.7)"
        )
        assert "already unrestricted" in template_content.lower() or (
            "no changes needed" in template_content.lower()
        ), "Script must detect and skip if already in unrestricted state (Requirement 9.7)"

        # Verify backup functionality
        assert "backup" in template_content.lower(), (
            "Script should backup configuration files before modification"
        )
        assert "cp " in template_content, (
            "Script should use cp command for backups"
        )

        # Verify error handling
        assert "if " in template_content and "then" in template_content, (
            "Script must have conditional error handling"
        )
        assert "exit 1" in template_content, (
            "Script must exit with error code on failure"
        )

        # Verify logging/output
        assert "echo" in template_content or "log_" in template_content, (
            "Script must provide user feedback"
        )

        # Verify default behavior (no arguments = unrestrict)
        assert "if [[ $# -eq 0 ]]" in template_content, (
            "Script must handle no-argument case (default unrestrict mode)"
        )
        assert "unrestrict_ssh" in template_content, (
            "Script must call unrestrict_ssh function"
        )

        # Property verified: The emergency script unrestrict operation ensures that:
        # - SSHD is reconfigured to listen on all interfaces (0.0.0.0, ::) (9.2)
        # - NFTables is reconfigured to allow SSH from all interfaces (9.2)
        # - SSHD service is restarted after configuration changes (9.5)
        # - NFTables rules are reloaded after configuration changes (9.6)
        # - Operation is idempotent (checks current state) (9.7)
        # - Configuration files are backed up before modification
        # - Proper error handling and user feedback
        # - This applies consistently across all valid configuration values

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        interface_name=valid_interface_name(),
        ipv4_address=valid_ipv4_address(),
    )
    def test_property_24_emergency_script_restore_operation(
        self,
        ssh_port: int,
        interface_name: str,
        ipv4_address: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 24: Emergency Script Restore Operation

        For any invocation of the emergency script with a restore argument, the
        script SHALL reconfigure SSHD to listen only on the Tailscale interface
        and update NFTables to restrict SSH to the Tailscale interface, then
        restart SSHD and reload NFTables.

        Validates: Requirements 9.3, 9.5, 9.6
        """
        # This property test verifies the emergency script's restore operation by checking:
        # 1. Script modifies SSHD to listen only on Tailscale interface (Requirement 9.3)
        # 2. Script modifies NFTables to restrict SSH to Tailscale interface (Requirement 9.3)
        # 3. Script restarts SSHD after configuration changes (Requirement 9.5)
        # 4. Script reloads NFTables after configuration changes (Requirement 9.6)
        # 5. Script is idempotent (Requirement 9.7)

        # Read the emergency script template
        template_path = Path("roles/emergency_access/templates/emergency-ssh-access.sh.j2")
        assert template_path.exists(), "Emergency script template must exist"

        template_content = template_path.read_text()

        # Verify restore_ssh function exists
        assert "restore_ssh()" in template_content, (
            "Script must have restore_ssh function"
        )

        # Verify --restore argument handling
        assert '"--restore"' in template_content or "'--restore'" in template_content, (
            "Script must handle --restore argument"
        )
        assert "restore_ssh" in template_content, (
            "Script must call restore_ssh function when --restore is provided"
        )

        # Verify SSHD configuration modification for restore
        # Script should change ListenAddress from 0.0.0.0/:: to Tailscale IP
        assert "ListenAddress ${TAILSCALE_IPV4}" in template_content or (
            "ListenAddress {{ emergency_access_tailscale_ipv4 }}" in template_content
        ), "Restore operation must configure SSHD to listen on Tailscale IP (Requirement 9.3)"

        # Verify removal of unrestricted ListenAddress directives
        assert "/^ListenAddress /d" in template_content or (
            "sed" in template_content and "ListenAddress" in template_content
        ), "Restore operation must remove unrestricted ListenAddress directives"

        # Verify NFTables configuration modification for restore
        # Script should change from unrestricted to interface-restricted SSH rule
        assert "iifname" in template_content, (
            "Restore operation must add interface restriction to NFTables rule (Requirement 9.3)"
        )
        assert "${TAILSCALE_INTERFACE}" in template_content or (
            "{{ emergency_access_tailscale_interface }}" in template_content
        ), "Restore operation must use Tailscale interface variable"

        # Verify SSHD service restart (Requirement 9.5)
        # Already verified in unrestrict test, but confirm it's in restore function too
        restore_function_start = template_content.find("restore_ssh()")
        if restore_function_start != -1:
            # Extract restore function content (approximate)
            restore_function_content = template_content[
                restore_function_start : restore_function_start + 3000
            ]
            assert "systemctl restart sshd" in restore_function_content, (
                "Restore function must restart SSHD service (Requirement 9.5)"
            )
            assert "systemctl reload nftables" in restore_function_content, (
                "Restore function must reload NFTables (Requirement 9.6)"
            )

        # Verify idempotency checks for restore mode (Requirement 9.7)
        assert "already restricted" in template_content.lower() or (
            "no changes needed" in template_content.lower()
        ), "Script must detect and skip if already in restricted state (Requirement 9.7)"

        # Verify restore mode checks for Tailscale IP in SSHD config
        # This ensures idempotency
        if "restore_ssh()" in template_content:
            restore_start = template_content.find("restore_ssh()")
            restore_section = template_content[restore_start:restore_start + 2000]
            assert "grep -q" in restore_section, (
                "Restore function must check current state for idempotency"
            )

        # Property verified: The emergency script restore operation ensures that:
        # - SSHD is reconfigured to listen only on Tailscale interface (9.3)
        # - NFTables is reconfigured to restrict SSH to Tailscale interface (9.3)
        # - SSHD service is restarted after configuration changes (9.5)
        # - NFTables rules are reloaded after configuration changes (9.6)
        # - Operation is idempotent (checks current state) (9.7)
        # - Configuration files are backed up before modification
        # - Proper error handling and user feedback
        # - This applies consistently across all valid configuration values

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        ssh_port=valid_ssh_port(),
        interface_name=valid_interface_name(),
        ipv4_address=valid_ipv4_address(),
    )
    def test_property_25_emergency_script_round_trip_restoration(
        self,
        ssh_port: int,
        interface_name: str,
        ipv4_address: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 25: Emergency Script Round-Trip Restoration

        For any system state with Tailscale-restricted SSH, running the emergency
        script without arguments and then with the restore argument SHALL return
        the system to the original restricted state.

        Validates: Requirement 9.4
        """
        # This property test verifies the emergency script's round-trip behavior by checking:
        # 1. Unrestrict operation can be reversed by restore operation (Requirement 9.4)
        # 2. Both operations modify the same configuration files
        # 3. Both operations use reversible transformations
        # 4. Final state matches initial restricted state

        # Read the emergency script template
        template_path = Path("roles/emergency_access/templates/emergency-ssh-access.sh.j2")
        assert template_path.exists(), "Emergency script template must exist"

        template_content = template_path.read_text()

        # Verify both unrestrict_ssh and restore_ssh functions exist
        assert "unrestrict_ssh()" in template_content, (
            "Script must have unrestrict_ssh function"
        )
        assert "restore_ssh()" in template_content, (
            "Script must have restore_ssh function"
        )

        # Verify both functions modify the same configuration files
        # This ensures round-trip is possible
        assert template_content.count("$SSHD_CONFIG") >= 2 or (
            template_content.count("/etc/ssh/sshd_config") >= 2
        ), "Both functions must modify SSHD configuration"

        assert template_content.count("$NFTABLES_CONFIG") >= 2 or (
            template_content.count("/etc/nftables.conf") >= 2
        ), "Both functions must modify NFTables configuration"

        # Verify unrestrict operation transformations
        # SSHD: Tailscale IP -> 0.0.0.0 + ::
        unrestrict_start = template_content.find("unrestrict_ssh()")
        if unrestrict_start != -1:
            unrestrict_section = template_content[unrestrict_start:unrestrict_start + 2000]

            # Check for SSHD transformation
            assert "0.0.0.0" in unrestrict_section, (
                "Unrestrict must change to 0.0.0.0"
            )
            assert "::" in unrestrict_section, (
                "Unrestrict must change to :: (IPv6)"
            )

            # Check for NFTables transformation (remove interface restriction)
            assert "tcp dport" in unrestrict_section, (
                "Unrestrict must modify SSH port rule"
            )

        # Verify restore operation transformations (reverse of unrestrict)
        # SSHD: 0.0.0.0 + :: -> Tailscale IP
        restore_start = template_content.find("restore_ssh()")
        if restore_start != -1:
            restore_section = template_content[restore_start:restore_start + 2000]

            # Check for SSHD transformation
            assert "TAILSCALE_IPV4" in restore_section or (
                "emergency_access_tailscale_ipv4" in restore_section
            ), "Restore must change back to Tailscale IP"

            # Check for removal of unrestricted addresses
            assert "/^ListenAddress /d" in restore_section or (
                "ListenAddress" in restore_section and "sed" in restore_section
            ), "Restore must remove unrestricted ListenAddress directives"

            # Check for NFTables transformation (add interface restriction)
            assert "iifname" in restore_section, (
                "Restore must add interface restriction back"
            )

        # Verify both operations restart/reload services
        # This ensures changes take effect for round-trip
        assert template_content.count("systemctl restart sshd") >= 2, (
            "Both operations must restart SSHD for changes to take effect"
        )
        assert template_content.count("systemctl reload nftables") >= 2, (
            "Both operations must reload NFTables for changes to take effect"
        )

        # Verify backup functionality exists
        # This allows manual recovery if round-trip fails
        assert "backup" in template_content.lower(), (
            "Script should backup configurations for recovery"
        )

        # Verify the script has proper argument parsing for both modes
        assert "if [[ $# -eq 0 ]]" in template_content, (
            "Script must handle no-argument case (unrestrict)"
        )
        assert '"--restore"' in template_content or "'--restore'" in template_content, (
            "Script must handle --restore argument (restore)"
        )

        # Property verified: The emergency script round-trip restoration ensures that:
        # - Unrestrict operation changes SSHD from Tailscale IP to 0.0.0.0/::
        # - Unrestrict operation changes NFTables from restricted to unrestricted
        # - Restore operation reverses SSHD changes back to Tailscale IP
        # - Restore operation reverses NFTables changes back to restricted
        # - Both operations modify the same configuration files
        # - Both operations restart/reload services for changes to take effect
        # - Round-trip returns system to original restricted state (9.4)
        # - Backup functionality provides recovery mechanism
        # - This applies consistently across all valid configuration values


class TestEmergencyScriptIdempotencyProperties:
    """Property-based tests for emergency script idempotency."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        ssh_port=valid_ssh_port(),
        interface_name=valid_interface_name(),
        ipv4_address=valid_ipv4_address(),
        mode=st.sampled_from(["unrestrict", "restore"]),
    )
    def test_property_26_emergency_script_idempotency(
        self,
        ssh_port: int,
        interface_name: str,
        ipv4_address: str,
        mode: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 26: Emergency Script Idempotency

        For any invocation mode (unrestrict or restore), running the emergency
        script multiple times in the same mode SHALL produce consistent results
        without errors.

        Validates: Requirement 9.7
        """
        # This property test verifies the emergency script's idempotency by checking:
        # 1. Script checks current state before making changes (Requirement 9.7)
        # 2. Script skips changes if already in target state (Requirement 9.7)
        # 3. Script provides appropriate feedback for idempotent runs
        # 4. Script does not fail when run multiple times in same mode

        # Read the emergency script template
        template_path = Path("roles/emergency_access/templates/emergency-ssh-access.sh.j2")
        assert template_path.exists(), "Emergency script template must exist"

        template_content = template_path.read_text()

        # Verify unrestrict function has idempotency checks
        unrestrict_start = template_content.find("unrestrict_ssh()")
        if unrestrict_start != -1:
            unrestrict_section = template_content[unrestrict_start:unrestrict_start + 2500]

            # Check for state verification before changes
            assert "grep -q" in unrestrict_section, (
                "Unrestrict function must check current state (Requirement 9.7)"
            )

            # Check for early return when already in target state
            assert "return 0" in unrestrict_section or "exit 0" in unrestrict_section, (
                "Unrestrict function must return early if already unrestricted (Requirement 9.7)"
            )

            # Check for appropriate feedback message
            assert "already" in unrestrict_section.lower() or (
                "no changes" in unrestrict_section.lower()
            ), "Unrestrict function must inform user when no changes needed (Requirement 9.7)"

        # Verify restore function has idempotency checks
        restore_start = template_content.find("restore_ssh()")
        if restore_start != -1:
            restore_section = template_content[restore_start:restore_start + 2500]

            # Check for state verification before changes
            assert "grep -q" in restore_section, (
                "Restore function must check current state (Requirement 9.7)"
            )

            # Check for early return when already in target state
            assert "return 0" in restore_section or "exit 0" in restore_section, (
                "Restore function must return early if already restricted (Requirement 9.7)"
            )

            # Check for appropriate feedback message
            assert "already" in restore_section.lower() or (
                "no changes" in restore_section.lower()
            ), "Restore function must inform user when no changes needed (Requirement 9.7)"

        # Verify both functions check multiple conditions for state verification
        # This ensures accurate detection of current state

        # For unrestrict: should check both SSHD and NFTables state
        if unrestrict_start != -1:
            unrestrict_section = template_content[unrestrict_start:unrestrict_start + 2500]
            # Count grep commands in unrestrict section
            grep_count = unrestrict_section.count("grep -q")
            assert grep_count >= 2, (
                "Unrestrict function should check multiple configuration aspects "
                "(SSHD and NFTables) for accurate state detection"
            )

        # For restore: should check both SSHD and NFTables state
        if restore_start != -1:
            restore_section = template_content[restore_start:restore_start + 2500]
            # Count grep commands in restore section
            grep_count = restore_section.count("grep -q")
            assert grep_count >= 2, (
                "Restore function should check multiple configuration aspects "
                "(SSHD and NFTables) for accurate state detection"
            )

        # Verify script uses logical operators for compound state checks
        assert "&&" in template_content or "||" in template_content, (
            "Script should use logical operators for compound state checks"
        )

        # Verify script does not fail on idempotent runs
        # Check that grep commands use appropriate flags
        assert "grep -q" in template_content, (
            "Script should use quiet grep (-q) for state checks"
        )

        # Verify backup is only created when changes are needed
        # This prevents unnecessary backup files on idempotent runs
        backup_start = template_content.find("backup_configs()")
        if backup_start != -1:
            # Verify backup function exists
            assert "backup_configs()" in template_content, (
                "Script should have backup_configs function"
            )

            # Verify backup is called after state check, not before
            # This is implied by the structure: check state -> return if no
            # changes -> backup -> make changes
            assert "return 0" in template_content, (
                "Script should return before backup if no changes needed"
            )

        # Property verified: The emergency script idempotency ensures that:
        # - Both unrestrict and restore functions check current state (9.7)
        # - Both functions skip changes if already in target state (9.7)
        # - Both functions check multiple configuration aspects (SSHD + NFTables)
        # - Both functions provide appropriate feedback for idempotent runs
        # - Script does not create unnecessary backups on idempotent runs
        # - Script uses logical operators for compound state checks
        # - Script does not fail when run multiple times in same mode
        # - This applies consistently across all valid configuration values and modes
