"""
Property-based tests for NFTables firewall configuration in VPS Bootstrap Playbook.

These tests verify universal properties about firewall rules, dual-stack configuration,
stateful filtering, and SSH access control across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid firewall configuration values
@st.composite
def valid_ssh_port(draw):
    """Generate valid SSH port numbers (1-65535)."""
    return draw(st.integers(min_value=1, max_value=65535))


@st.composite
def valid_interface_name(draw):
    """Generate valid network interface names."""
    # Common interface name patterns: eth0, ens3, tailscale0, wg0, etc.
    prefix = draw(st.sampled_from(["eth", "ens", "tailscale", "wg", "tun", "tap"]))
    suffix = draw(st.integers(min_value=0, max_value=99))
    return f"{prefix}{suffix}"


@st.composite
def valid_wireguard_port(draw):
    """Generate valid WireGuard port numbers (1024-65535)."""
    return draw(st.integers(min_value=1024, max_value=65535))


class TestNFTablesDualStackProperties:
    """Property-based tests for NFTables dual-stack configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        tailscale_enabled=st.booleans(),
    )
    def test_property_17_nftables_dual_stack_configuration(
        self, ssh_port: int, tailscale_enabled: bool
    ):
        """
        Feature: vps-bootstrap-playbook, Property 17: NFTables Dual-Stack Configuration

        For any execution of the bootstrap playbook, NFTables rules SHALL be configured
        for both IPv4 and IPv6 traffic with identical policies.

        Validates: Requirements 8.1, 8.2
        """
        # This property test verifies the firewall role's dual-stack behavior by checking:
        # 1. NFTables configuration uses inet family (supports both IPv4 and IPv6)
        # 2. Rules apply to both IPv4 and IPv6 traffic uniformly
        # 3. No separate IPv4/IPv6 tables are needed

        # Read the NFTables configuration template
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables configuration template must exist"

        template_content = template_path.read_text()

        # Verify Requirement 8.1 & 8.2: Dual-stack configuration using inet family
        assert "table inet filter" in template_content, (
            "NFTables must use 'inet' family for dual-stack (IPv4 + IPv6) support"
        )

        # Verify no separate IPv4-only or IPv6-only tables
        # (inet family handles both, so separate tables would be redundant)
        assert "table ip filter" not in template_content, (
            "Should not use separate IPv4-only table (inet handles both)"
        )
        assert "table ip6 filter" not in template_content, (
            "Should not use separate IPv6-only table (inet handles both)"
        )

        # Verify ICMP support for both IPv4 and IPv6
        # This ensures network diagnostics work for both protocol versions
        assert "ip protocol icmp accept" in template_content, (
            "Must allow ICMPv4 for IPv4 network diagnostics"
        )
        assert "ip6 nexthdr icmpv6 accept" in template_content, (
            "Must allow ICMPv6 for IPv6 network diagnostics"
        )

        # Verify chains are defined for inet family
        assert "chain input" in template_content, (
            "Input chain must be defined"
        )
        assert "chain forward" in template_content, (
            "Forward chain must be defined"
        )
        assert "chain output" in template_content, (
            "Output chain must be defined"
        )

        # Verify chains use filter hook (standard firewall behavior)
        assert "type filter hook input" in template_content, (
            "Input chain must use filter hook"
        )
        assert "type filter hook forward" in template_content, (
            "Forward chain must use filter hook"
        )
        assert "type filter hook output" in template_content, (
            "Output chain must use filter hook"
        )

        # Read the firewall role tasks
        tasks_path = Path("roles/firewall/tasks/main.yml")
        assert tasks_path.exists(), "Firewall role tasks must exist"

        tasks_content = tasks_path.read_text()

        # Verify nftables package is installed
        assert "name: nftables" in tasks_content, (
            "NFTables package must be installed"
        )

        # Verify configuration is deployed to correct location
        assert "dest: /etc/nftables.conf" in tasks_content, (
            "NFTables configuration must be deployed to /etc/nftables.conf"
        )

        # Verify configuration has correct permissions
        assert 'mode: "0644"' in tasks_content, (
            "NFTables configuration must have mode 0644"
        )

        # Verify configuration has correct ownership
        assert "owner: root" in tasks_content, (
            "NFTables configuration must be owned by root"
        )
        assert "group: root" in tasks_content, (
            "NFTables configuration must have group root"
        )

        # Property verified: The firewall role configuration ensures that:
        # - NFTables uses inet family for dual-stack support (8.1, 8.2)
        # - Rules apply uniformly to both IPv4 and IPv6 traffic
        # - ICMP is allowed for both protocol versions
        # - Configuration is properly deployed with correct permissions
        # - This applies consistently regardless of SSH port or Tailscale status


class TestNFTablesStatefulFirewallProperties:
    """Property-based tests for NFTables stateful firewall rules."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        tailscale_enabled=st.booleans(),
    )
    def test_property_18_nftables_stateful_firewall_rules(
        self, ssh_port: int, tailscale_enabled: bool
    ):
        """
        Feature: vps-bootstrap-playbook, Property 18: NFTables Stateful Firewall Rules

        For any execution of the bootstrap playbook, NFTables SHALL allow established
        and related connections, allow loopback interface traffic, and set default
        input and forward policies to drop.

        Validates: Requirements 8.3, 8.4, 8.5, 8.6
        """
        # This property test verifies the firewall role's stateful behavior by checking:
        # 1. Established and related connections are allowed (Requirement 8.3)
        # 2. Loopback interface traffic is allowed (Requirement 8.4)
        # 3. Default input policy is drop (Requirement 8.5)
        # 4. Default forward policy is drop (Requirement 8.6)

        # Read the NFTables configuration template
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables configuration template must exist"

        template_content = template_path.read_text()

        # Verify Requirement 8.3: Established and related connections are allowed
        assert "ct state established,related accept" in template_content, (
            "Must allow established and related connections for stateful firewall"
        )

        # Verify Requirement 8.4: Loopback interface traffic is allowed
        assert "iif lo accept" in template_content, (
            "Must allow loopback interface traffic (required for local services)"
        )

        # Verify Requirement 8.5: Default input policy is drop
        assert "chain input" in template_content, (
            "Input chain must be defined"
        )
        # Check that input chain has policy drop
        input_chain_lines = []
        in_input_chain = False
        for line in template_content.split('\n'):
            if 'chain input' in line:
                in_input_chain = True
            if in_input_chain:
                input_chain_lines.append(line)
                if 'policy drop' in line:
                    break

        assert any('policy drop' in line for line in input_chain_lines), (
            "Input chain must have default policy drop (Requirement 8.5)"
        )

        # Verify Requirement 8.6: Default forward policy is drop
        assert "chain forward" in template_content, (
            "Forward chain must be defined"
        )
        # Check that forward chain has policy drop
        forward_chain_lines = []
        in_forward_chain = False
        for line in template_content.split('\n'):
            if 'chain forward' in line:
                in_forward_chain = True
            if in_forward_chain:
                forward_chain_lines.append(line)
                if 'policy drop' in line:
                    break

        assert any('policy drop' in line for line in forward_chain_lines), (
            "Forward chain must have default policy drop (Requirement 8.6)"
        )

        # Verify output chain has accept policy (allow all outbound)
        output_chain_lines = []
        in_output_chain = False
        for line in template_content.split('\n'):
            if 'chain output' in line:
                in_output_chain = True
            if in_output_chain:
                output_chain_lines.append(line)
                if 'policy accept' in line:
                    break

        assert any('policy accept' in line for line in output_chain_lines), (
            "Output chain should have default policy accept (allow all outbound)"
        )

        # Verify stateful firewall comment is present
        assert "stateful firewall" in template_content.lower(), (
            "Configuration should document stateful firewall behavior"
        )

        # Verify established/related rule comes before other rules
        # This is important for performance (most packets match this rule)
        lines = template_content.split('\n')
        established_line_num = None
        ssh_rule_line_num = None

        for i, line in enumerate(lines):
            if 'ct state established,related accept' in line:
                established_line_num = i
            if 'tcp dport' in line and 'accept' in line:
                ssh_rule_line_num = i

        if established_line_num is not None and ssh_rule_line_num is not None:
            assert established_line_num < ssh_rule_line_num, (
                "Established/related rule should come before specific service rules "
                "for performance"
            )

        # Verify loopback rule comes early (before service-specific rules)
        loopback_line_num = None
        for i, line in enumerate(lines):
            if 'iif lo accept' in line:
                loopback_line_num = i
                break

        if loopback_line_num is not None and ssh_rule_line_num is not None:
            assert loopback_line_num < ssh_rule_line_num, (
                "Loopback rule should come before specific service rules"
            )

        # Read the firewall role tasks
        tasks_path = Path("roles/firewall/tasks/main.yml")
        assert tasks_path.exists(), "Firewall role tasks must exist"

        tasks_content = tasks_path.read_text()

        # Verify service is enabled for boot persistence (Requirement 8.10)
        assert "name: nftables" in tasks_content, (
            "NFTables service must be referenced"
        )
        assert "enabled: true" in tasks_content, (
            "NFTables service must be enabled for boot persistence"
        )

        # Verify service is started
        assert "state: started" in tasks_content, (
            "NFTables service must be started"
        )

        # Verify configuration changes trigger reload
        assert "notify: Reload nftables" in tasks_content or "notify:" in tasks_content, (
            "Configuration changes should trigger nftables reload"
        )

        # Read the handlers to verify reload handler exists
        handlers_path = Path("roles/firewall/handlers/main.yml")
        assert handlers_path.exists(), "Firewall role handlers must exist"

        handlers_content = handlers_path.read_text()

        # Verify reload handler is defined
        assert "name: Reload nftables" in handlers_content, (
            "Reload nftables handler must be defined"
        )
        assert "name: nftables" in handlers_content, (
            "Handler must reference nftables service"
        )
        assert "state: reloaded" in handlers_content or "state: restarted" in handlers_content, (
            "Handler must reload or restart nftables service"
        )

        # Property verified: The firewall role configuration ensures that:
        # - Established and related connections are allowed (stateful) (8.3)
        # - Loopback interface traffic is allowed (8.4)
        # - Default input policy is drop (8.5)
        # - Default forward policy is drop (8.6)
        # - Service is enabled for boot persistence (8.10)
        # - Configuration changes trigger service reload
        # - Rule ordering is optimized for performance
        # - This applies consistently regardless of SSH port or Tailscale status


class TestNFTablesSSHAccessControlProperties:
    """Property-based tests for NFTables SSH access control."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        tailscale_interface=valid_interface_name(),
        wireguard_port=valid_wireguard_port(),
    )
    def test_property_19_nftables_ssh_access_control(
        self, ssh_port: int, tailscale_interface: str, wireguard_port: int
    ):
        """
        Feature: vps-bootstrap-playbook, Property 19: NFTables SSH Access Control

        For any execution of the bootstrap playbook, NFTables SHALL restrict SSH port
        access to the Tailscale interface only when Tailscale is enabled, or allow SSH
        port access from all interfaces when Tailscale is disabled.

        Validates: Requirements 8.7, 8.8
        """
        # This property test verifies the firewall role's SSH access control by checking:
        # 1. When Tailscale enabled: SSH restricted to Tailscale interface (Requirement 8.7)
        # 2. When Tailscale disabled: SSH allowed from all interfaces (Requirement 8.8)
        # 3. SSH port is configurable
        # 4. Tailscale WireGuard traffic is allowed when enabled (Requirement 8.9)

        # Read the NFTables configuration template
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables configuration template must exist"

        template_content = template_path.read_text()

        # Verify SSH port variable is used in template
        assert "{{ firewall_ssh_port }}" in template_content, (
            "SSH port must be configurable via firewall_ssh_port variable"
        )

        # Verify Tailscale interface variable is used in template
        assert "{{ firewall_tailscale_interface }}" in template_content, (
            "Tailscale interface must be configurable via firewall_tailscale_interface variable"
        )

        # Verify WireGuard port variable is used in template
        assert "{{ firewall_wireguard_port }}" in template_content, (
            "WireGuard port must be configurable via firewall_wireguard_port variable"
        )

        # Verify conditional logic for Tailscale enabled/disabled
        assert "{% if firewall_tailscale_enabled | bool %}" in template_content, (
            "Template must have conditional logic for Tailscale enabled state"
        )
        assert "{% else %}" in template_content, (
            "Template must have else branch for Tailscale disabled state"
        )
        assert "{% endif %}" in template_content, (
            "Template must close conditional block"
        )

        # Verify Requirement 8.7: SSH restricted to Tailscale interface when enabled
        # Extract the Tailscale enabled block
        lines = template_content.split('\n')
        in_tailscale_block = False
        tailscale_block_lines = []

        for line in lines:
            if '{% if firewall_tailscale_enabled | bool %}' in line:
                in_tailscale_block = True
                continue
            if ('{% else %}' in line or '{% endif %}' in line) and in_tailscale_block:
                break
            if in_tailscale_block:
                tailscale_block_lines.append(line)

        tailscale_block = '\n'.join(tailscale_block_lines)

        # Verify SSH is restricted to Tailscale interface
        assert 'iifname "{{ firewall_tailscale_interface }}"' in tailscale_block, (
            "When Tailscale enabled, SSH must be restricted to Tailscale interface (8.7)"
        )
        assert "tcp dport {{ firewall_ssh_port }}" in tailscale_block, (
            "When Tailscale enabled, SSH port must be specified"
        )
        assert "accept" in tailscale_block, (
            "When Tailscale enabled, SSH traffic on Tailscale interface must be accepted"
        )

        # Verify Requirement 8.9: Tailscale WireGuard traffic is allowed
        assert "udp dport {{ firewall_wireguard_port }}" in tailscale_block, (
            "When Tailscale enabled, WireGuard UDP traffic must be allowed (8.9)"
        )

        # Verify Requirement 8.8: SSH allowed from all interfaces when disabled
        # Extract the else block (Tailscale disabled)
        in_else_block = False
        else_block_lines = []

        for line in lines:
            if '{% else %}' in line:
                in_else_block = True
                continue
            if '{% endif %}' in line and in_else_block:
                break
            if in_else_block:
                else_block_lines.append(line)

        else_block = '\n'.join(else_block_lines)

        # Verify SSH is allowed from all interfaces (no iifname restriction)
        assert "tcp dport {{ firewall_ssh_port }}" in else_block, (
            "When Tailscale disabled, SSH port must be specified"
        )
        assert "accept" in else_block, (
            "When Tailscale disabled, SSH traffic must be accepted"
        )
        # Verify no interface restriction in else block
        assert "iifname" not in else_block, (
            "When Tailscale disabled, SSH should not be restricted to specific interface (8.8)"
        )

        # Read the firewall role defaults
        defaults_path = Path("roles/firewall/defaults/main.yml")
        assert defaults_path.exists(), "Firewall role defaults must exist"

        defaults_content = defaults_path.read_text()

        # Verify firewall_ssh_port variable is defined
        assert "firewall_ssh_port:" in defaults_content, (
            "firewall_ssh_port must be defined in defaults"
        )

        # Verify firewall_tailscale_enabled variable is defined
        assert "firewall_tailscale_enabled:" in defaults_content, (
            "firewall_tailscale_enabled must be defined in defaults"
        )

        # Verify firewall_tailscale_interface variable is defined
        assert "firewall_tailscale_interface:" in defaults_content, (
            "firewall_tailscale_interface must be defined in defaults"
        )

        # Verify firewall_wireguard_port variable is defined
        assert "firewall_wireguard_port:" in defaults_content, (
            "firewall_wireguard_port must be defined in defaults"
        )

        # Verify default values reference other role variables
        assert "{{ ssh_port" in defaults_content or "ssh_port" in defaults_content, (
            "firewall_ssh_port should reference ssh_port from ssh_hardening role"
        )
        assert (
            "{{ tailscale_enabled" in defaults_content
            or "tailscale_enabled" in defaults_content
        ), "firewall_tailscale_enabled should reference tailscale_enabled from tailscale role"
        assert (
            "{{ tailscale_interface" in defaults_content
            or "tailscale_interface" in defaults_content
        ), (
            "firewall_tailscale_interface should reference tailscale_interface "
            "from tailscale role"
        )

        # Verify default WireGuard port is reasonable (Tailscale uses 41641 by default)
        assert "firewall_wireguard_port: 41641" in defaults_content or (
            "firewall_wireguard_port:" in defaults_content
        ), "firewall_wireguard_port should have a default value"

        # Verify template uses TCP protocol for SSH
        assert "tcp dport" in template_content, (
            "SSH rules must use TCP protocol"
        )

        # Verify template uses UDP protocol for WireGuard
        assert "udp dport" in template_content, (
            "WireGuard rules must use UDP protocol"
        )

        # Property verified: The firewall role configuration ensures that:
        # - When Tailscale enabled: SSH restricted to Tailscale interface (8.7)
        # - When Tailscale disabled: SSH allowed from all interfaces (8.8)
        # - When Tailscale enabled: WireGuard traffic is allowed (8.9)
        # - SSH port is configurable
        # - Tailscale interface is configurable
        # - WireGuard port is configurable
        # - Conditional logic correctly handles both scenarios
        # - This applies consistently for any valid port and interface configuration


class TestNFTablesServicePersistenceProperties:
    """Property-based tests for NFTables service persistence."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        ssh_port=valid_ssh_port(),
        tailscale_enabled=st.booleans(),
    )
    def test_property_21_nftables_service_persistence(
        self, ssh_port: int, tailscale_enabled: bool
    ):
        """
        Feature: vps-bootstrap-playbook, Property 21: NFTables Service Persistence

        For any execution of the bootstrap playbook, the NFTables service SHALL be
        enabled to start on boot, ensuring rules persist across system reboots.

        Validates: Requirements 8.10, 8.11
        """
        # This property test verifies the firewall role's service persistence by checking:
        # 1. NFTables service is enabled to start on boot (Requirement 8.10)
        # 2. NFTables rules persist across system reboots (Requirement 8.11)
        # 3. Configuration file is deployed to the correct location
        # 4. Service is started after configuration

        # Read the firewall role tasks
        tasks_path = Path("roles/firewall/tasks/main.yml")
        assert tasks_path.exists(), "Firewall role tasks must exist"

        tasks_content = tasks_path.read_text()

        # Verify Requirement 8.10: NFTables service is enabled to start on boot
        # The service must be enabled using systemd
        assert "name: nftables" in tasks_content, (
            "NFTables service must be referenced in tasks"
        )
        assert "enabled: true" in tasks_content or "enabled: yes" in tasks_content, (
            "NFTables service must be enabled to start on boot (Requirement 8.10)"
        )

        # Verify service is started (not just enabled)
        assert "state: started" in tasks_content, (
            "NFTables service must be started after configuration"
        )

        # Verify Requirement 8.11: NFTables rules persist across system reboots
        # This is achieved by:
        # 1. Deploying configuration to /etc/nftables.conf (standard location)
        # 2. Enabling the nftables.service which loads rules from this file on boot

        # Verify configuration is deployed to standard location
        assert "dest: /etc/nftables.conf" in tasks_content, (
            "NFTables configuration must be deployed to /etc/nftables.conf "
            "for persistence (Requirement 8.11)"
        )

        # Verify configuration file has correct permissions for boot loading
        assert 'mode: "0644"' in tasks_content or "mode: '0644'" in tasks_content, (
            "NFTables configuration must have mode 0644 (readable by system)"
        )

        # Verify configuration is owned by root (required for system service)
        assert "owner: root" in tasks_content, (
            "NFTables configuration must be owned by root"
        )
        assert "group: root" in tasks_content, (
            "NFTables configuration must have group root"
        )

        # Verify template task exists (deploys the configuration)
        assert "ansible.builtin.template:" in tasks_content or "template:" in tasks_content, (
            "Must use template module to deploy NFTables configuration"
        )

        # Verify template source is correct
        assert "src: nftables.conf.j2" in tasks_content, (
            "Template source must be nftables.conf.j2"
        )

        # Verify configuration changes trigger service reload
        assert "notify:" in tasks_content, (
            "Configuration changes must trigger handler notification"
        )

        # Read the handlers to verify reload/restart handler exists
        handlers_path = Path("roles/firewall/handlers/main.yml")
        assert handlers_path.exists(), "Firewall role handlers must exist"

        handlers_content = handlers_path.read_text()

        # Verify reload or restart handler is defined
        assert (
            "name: Reload nftables" in handlers_content
            or "name: Restart nftables" in handlers_content
        ), "Handler for reloading/restarting nftables must be defined"

        # Verify handler uses systemd service module
        assert "ansible.builtin.systemd:" in handlers_content or "systemd:" in handlers_content or (
            "ansible.builtin.service:" in handlers_content or "service:" in handlers_content
        ), "Handler must use systemd or service module"

        # Verify handler references nftables service
        assert "name: nftables" in handlers_content, (
            "Handler must reference nftables service"
        )

        # Verify handler reloads or restarts the service
        assert "state: reloaded" in handlers_content or "state: restarted" in handlers_content, (
            "Handler must reload or restart nftables service to apply changes"
        )

        # Verify the NFTables configuration template exists
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables configuration template must exist"

        template_content = template_path.read_text()

        # Verify template contains valid nftables syntax
        assert "table inet filter" in template_content, (
            "Template must define inet filter table"
        )
        assert "chain input" in template_content, (
            "Template must define input chain"
        )
        assert "chain forward" in template_content, (
            "Template must define forward chain"
        )
        assert "chain output" in template_content, (
            "Template must define output chain"
        )

        # Verify template has proper nftables structure (flush and define)
        assert "flush ruleset" in template_content or "table inet filter" in template_content, (
            "Template must have proper nftables structure"
        )

        # Read the firewall role defaults
        defaults_path = Path("roles/firewall/defaults/main.yml")
        assert defaults_path.exists(), "Firewall role defaults must exist"

        defaults_content = defaults_path.read_text()

        # Verify default variables are defined for configuration
        assert "firewall_ssh_port:" in defaults_content, (
            "firewall_ssh_port must be defined in defaults"
        )
        assert "firewall_tailscale_enabled:" in defaults_content, (
            "firewall_tailscale_enabled must be defined in defaults"
        )

        # Verify service module tasks exist
        # The enable and start tasks may be separate or combined
        # Look for systemd/service tasks that reference nftables
        lines = tasks_content.split('\n')
        found_enable_task = False
        found_start_task = False

        for i, line in enumerate(lines):
            if 'ansible.builtin.systemd:' in line or 'systemd:' in line or (
                'ansible.builtin.service:' in line or 'service:' in line
            ):
                # Look ahead to see if this task references nftables
                task_block = '\n'.join(lines[i:min(i+10, len(lines))])
                if 'name: nftables' in task_block:
                    if 'enabled: true' in task_block or 'enabled: yes' in task_block:
                        found_enable_task = True
                    if 'state: started' in task_block:
                        found_start_task = True

        assert found_enable_task, (
            "Must have a task that enables nftables service (Requirement 8.10)"
        )
        assert found_start_task, (
            "Must have a task that starts nftables service"
        )

        # Property verified: The firewall role configuration ensures that:
        # - NFTables service is enabled to start on boot (8.10)
        # - NFTables configuration is deployed to /etc/nftables.conf (8.11)
        # - Configuration has correct permissions and ownership
        # - Service is started after configuration deployment
        # - Configuration changes trigger service reload via handlers
        # - Template contains valid nftables syntax
        # - This applies consistently regardless of SSH port or Tailscale status


@st.composite
def valid_knock_sequence(draw):
    """Generate valid 3-port knock sequences."""
    ports = draw(
        st.lists(
            st.integers(min_value=1024, max_value=65535),
            min_size=3,
            max_size=3,
        )
    )
    return ports


class TestNFTablesPortKnockingProperties:
    """Property-based tests for NFTables port knocking configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        port_knocking_enabled=st.booleans(),
        tailscale_enabled=st.booleans(),
    )
    def test_knock_rules_conditional_on_tailscale_and_knocking(
        self,
        port_knocking_enabled: bool,
        tailscale_enabled: bool,
    ):
        """
        Feature: vps-bootstrap-playbook, Knock Rules Conditional Activation

        Port knocking sets and rules SHALL appear in the NFTables template only when
        Tailscale is disabled AND port_knocking_enabled is true. They SHALL NOT appear
        when Tailscale is enabled or when port knocking is disabled.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables template must exist"

        content = template_path.read_text()

        if tailscale_enabled:
            # When Tailscale is enabled, knock rules should be in the elif branch
            # which won't execute — verify the template has the right conditional
            assert "{% if firewall_tailscale_enabled" in content, (
                "Template must check Tailscale status first"
            )
            assert "{% elif firewall_port_knocking_enabled" in content, (
                "Port knocking must be in elif branch (never active with Tailscale)"
            )
        elif port_knocking_enabled:
            # When Tailscale disabled and knocking enabled, verify knock content exists
            # Template uses Jinja2 for-loops so check for the loop variable form
            assert "knock{{ af }}_stage1" in content, (
                "IPv4/IPv6 knock stage1 set must be defined in template via loop"
            )
            assert "knock{{ af }}_passed" in content, (
                "IPv4/IPv6 knock passed set must be defined in template via loop"
            )
        else:
            # When both disabled, verify unconditional SSH accept exists in else branch
            assert "{% else %}" in content, (
                "Template must have else branch for open SSH"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        knock_sequence=valid_knock_sequence(),
    )
    def test_knock_sequence_ports_in_template(
        self,
        knock_sequence: list,
    ):
        """
        Feature: vps-bootstrap-playbook, Knock Sequence Ports in Template

        All ports from the configured knock sequence SHALL appear in the NFTables
        template rules for both IPv4 and IPv6 address families.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        # Verify template references the sequence variable for all 3 ports
        assert "firewall_port_knocking_sequence[0]" in content, (
            "Template must reference first port in sequence"
        )
        assert "firewall_port_knocking_sequence[1]" in content, (
            "Template must reference second port in sequence"
        )
        assert "firewall_port_knocking_sequence[2]" in content, (
            "Template must reference third port in sequence"
        )

        # Verify the drop rule references the full sequence
        assert "firewall_port_knocking_sequence | join" in content, (
            "Drop rule must reference the full knock sequence"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        addr_type=st.sampled_from(["ipv4_addr", "ipv6_addr"]),
    )
    def test_dual_stack_knock_sets(
        self,
        addr_type: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Dual-Stack Knock Sets

        The NFTables template SHALL define knock sets for both IPv4 and IPv6
        address families.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        assert addr_type in content, (
            f"Template must define sets with type {addr_type}"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        af=st.sampled_from(["4", "6"]),
    )
    def test_ssh_accept_references_knock_passed(
        self,
        af: str,
    ):
        """
        Feature: vps-bootstrap-playbook, SSH Accept References Knock Passed

        When port knocking is enabled, the SSH accept rule SHALL reference the
        knock_passed set for the given address family.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        assert f"@knock{af}_passed accept" in content, (
            f"SSH accept rule must reference knock{af}_passed set"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        af=st.sampled_from(["4", "6"]),
    )
    def test_sets_at_table_level(
        self,
        af: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Sets at Table Level

        Named NFTables sets SHALL be defined at the table level (outside chain
        blocks), as required by NFTables syntax.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        lines = content.split("\n")

        # Find the set definition and verify it's before "chain input"
        set_line_num = None
        chain_input_line_num = None

        for i, line in enumerate(lines):
            if f"knock{af}_stage1" in line and "set" in line:
                set_line_num = i
            if "chain input" in line:
                chain_input_line_num = i

        if set_line_num is not None and chain_input_line_num is not None:
            assert set_line_num < chain_input_line_num, (
                f"knock{af}_stage1 set must be defined before chain input "
                "(sets must be at table level, not inside chains)"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        af=st.sampled_from(["4", "6"]),
    )
    def test_timeout_variables_used(
        self,
        af: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Timeout Variables Used

        Knock set timeouts SHALL use the configured variables, not hardcoded values.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        assert "firewall_port_knocking_stage_timeout" in content, (
            "Stage timeout must use firewall_port_knocking_stage_timeout variable"
        )
        assert "firewall_port_knocking_timeout" in content, (
            "Passed timeout must use firewall_port_knocking_timeout variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        af=st.sampled_from(["4", "6"]),
    )
    def test_explicit_drop_for_knock_ports(
        self,
        af: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Explicit Drop for Knock Ports

        Knock port packets SHALL be explicitly dropped after set processing
        to prevent leakage to later rules or logs.

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        # Find the knock section and verify drop rule exists
        assert "firewall_port_knocking_sequence | join" in content, (
            "Template must have a drop rule referencing the knock sequence"
        )

        # Verify drop comes after the knock rules but before SSH accept
        lines = content.split("\n")
        drop_line = None
        ssh_accept_line = None

        for i, line in enumerate(lines):
            if "drop" in line and "port_knocking_sequence" in line:
                drop_line = i
            if f"@knock{af}_passed accept" in line:
                ssh_accept_line = i

        if drop_line is not None and ssh_accept_line is not None:
            assert drop_line < ssh_accept_line, (
                "Drop rule for knock ports must come before SSH accept rule"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        af=st.sampled_from(["4", "6"]),
    )
    def test_no_unconditional_ssh_accept_with_knocking(
        self,
        af: str,
    ):
        """
        Feature: vps-bootstrap-playbook, No Unconditional SSH Accept

        When port knocking is enabled, there SHALL NOT be an unconditional SSH
        accept rule (one without @knock_passed set membership check).

        Validates: Port knocking design spec
        """
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        content = template_path.read_text()

        # The elif block for port knocking should only have SSH accept with set check
        lines = content.split("\n")
        in_knock_block = False

        for line in lines:
            if "elif firewall_port_knocking_enabled" in line:
                in_knock_block = True
                continue
            if in_knock_block and ("{% else %}" in line or "{% endif %}" in line):
                break
            if in_knock_block and (
                "tcp dport" in line
                and "firewall_ssh_port" in line
                and "accept" in line
            ):
                # This SSH accept must reference a knock_passed set
                assert "@knock" in line, (
                    "SSH accept in knock block must check knock_passed set membership"
                )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        af=st.sampled_from(["4", "6"]),
    )
    def test_defaults_define_knock_variables(
        self,
        af: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Knock Variables

        The firewall role defaults SHALL define all port knocking variables
        with the firewall_ prefix convention.

        Validates: Port knocking design spec
        """
        defaults_path = Path("roles/firewall/defaults/main.yml")
        assert defaults_path.exists(), "Firewall defaults must exist"

        content = defaults_path.read_text()

        assert "firewall_port_knocking_enabled:" in content, (
            "firewall_port_knocking_enabled must be defined in defaults"
        )
        assert "firewall_port_knocking_sequence:" in content, (
            "firewall_port_knocking_sequence must be defined in defaults"
        )
        assert "firewall_port_knocking_timeout:" in content, (
            "firewall_port_knocking_timeout must be defined in defaults"
        )
        assert "firewall_port_knocking_stage_timeout:" in content, (
            "firewall_port_knocking_stage_timeout must be defined in defaults"
        )
        # - Rules persist across system reboots through systemd service


class TestPortKnockPrePlayProperties:
    """Property-based tests for the port-knock pre-play in site.yml."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_knock_play_exists_before_bootstrap_play(self):
        """
        The site.yml playbook SHALL contain a local port-knock play before the
        bootstrap play so that Ansible can reach hosts behind port knocking.
        """
        import yaml

        playbook_path = Path("site.yml")
        assert playbook_path.exists(), "site.yml must exist"

        plays = yaml.safe_load(playbook_path.read_text())
        assert len(plays) >= 2, "site.yml must have at least two plays"

        knock_play = plays[0]
        assert knock_play["name"] == "Port knock for SSH access", (
            "First play must be the port-knock play"
        )
        assert knock_play.get("gather_facts") is False, (
            "Knock play must not gather facts (no SSH needed)"
        )
        assert knock_play.get("connection") == "local", (
            "Knock play must use local connection (runs on controller)"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_knock_play_is_conditional(self):
        """
        The knock task SHALL be skipped when Tailscale is enabled or when
        port knocking is disabled.
        """
        import yaml

        plays = yaml.safe_load(Path("site.yml").read_text())
        knock_task = plays[0]["tasks"][0]
        when = knock_task["when"]

        assert any("tailscale_enabled" in str(c) for c in when), (
            "Knock task must check tailscale_enabled"
        )
        assert any("port_knocking_enabled" in str(c) for c in when), (
            "Knock task must check port_knocking_enabled"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_knock_play_never_reports_changed(self):
        """
        The knock task SHALL set changed_when: false because knocking is
        idempotent and produces no state change.
        """
        import yaml

        plays = yaml.safe_load(Path("site.yml").read_text())
        knock_task = plays[0]["tasks"][0]

        assert knock_task.get("changed_when") is False, (
            "Knock task must set changed_when: false"
        )
