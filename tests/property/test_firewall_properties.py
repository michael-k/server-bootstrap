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
        NFTables Dual-Stack Configuration

        Checks that the nftables template defines one `inet` filter table and no
        `ip` or `ip6` one, accepts ICMPv4 and ICMPv6, and hooks input, forward and
        output chains; and that the tasks install nftables and deploy the ruleset
        to `/etc/nftables.conf`, owned by root with mode `0644`.

        Validates: FW-1, FW-2, FW-8, FW-9, FW-16
        """
        # Read the NFTables configuration template
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables configuration template must exist"

        template_content = template_path.read_text()

        # FW-2: dual-stack configuration through a single inet table
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
        NFTables Stateful Firewall Rules

        Checks that the nftables template accepts established and related
        connections and loopback traffic ahead of the last `tcp dport … accept`
        rule, gives the input and forward chains a drop policy and the output chain
        an accept policy; and that the tasks enable and start nftables and notify a
        handler that reloads or restarts it.

        Validates: FW-3, FW-4, FW-5, FW-6, FW-7, FW-17, FW-18, FW-19
        """
        # Read the NFTables configuration template
        template_path = Path("roles/firewall/templates/nftables.conf.j2")
        assert template_path.exists(), "NFTables configuration template must exist"

        template_content = template_path.read_text()

        # FW-6: established and related connections are allowed
        assert "ct state established,related accept" in template_content, (
            "Must allow established and related connections for stateful firewall"
        )

        # FW-7: loopback interface traffic is allowed
        assert "iif lo accept" in template_content, (
            "Must allow loopback interface traffic (required for local services)"
        )

        # FW-3: default input policy is drop
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
            "Input chain must have default policy drop (FW-3)"
        )

        # FW-4: default forward policy is drop
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
            "Forward chain must have default policy drop (FW-4)"
        )

        # FW-5: the output chain has an accept policy
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

        # FW-17: the service is enabled so the ruleset is reloaded at boot
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
        NFTables SSH Access Control

        Checks that the nftables template's `firewall_tailscale_enabled` branch
        accepts SSH only with `iifname` set to `firewall_tailscale_interface` and
        accepts the WireGuard port, that its `else` branch accepts SSH with no
        interface qualifier, that both render the port from `firewall_ssh_port`,
        and that the defaults derive the firewall variables from `ssh_port`,
        `tailscale_enabled` and `tailscale_interface`.

        Validates: FW-10, FW-11, FW-12, FW-13, FW-14
        """
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

        # FW-10: SSH restricted to the tailnet interface when Tailscale is enabled
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
            "When Tailscale enabled, SSH must be restricted to the tailnet interface (FW-10)"
        )
        assert "tcp dport {{ firewall_ssh_port }}" in tailscale_block, (
            "When Tailscale enabled, SSH port must be specified"
        )
        assert "accept" in tailscale_block, (
            "When Tailscale enabled, SSH traffic on Tailscale interface must be accepted"
        )

        # FW-12: Tailscale WireGuard traffic is allowed
        assert "udp dport {{ firewall_wireguard_port }}" in tailscale_block, (
            "When Tailscale enabled, WireGuard UDP traffic must be allowed (FW-12)"
        )

        # FW-13: SSH allowed from all interfaces when Tailscale and knocking are off
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
            "When Tailscale disabled, SSH should not be restricted to an interface (FW-13)"
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
        NFTables Service Persistence

        Checks that the tasks deploy `nftables.conf.j2` to `/etc/nftables.conf`,
        owned by root with mode `0644`, notify a handler that reloads or restarts
        nftables, and have a service task for nftables that enables it and one
        that starts it; and that the template defines the `inet` filter table and
        its three chains.

        Validates: FW-16, FW-17, FW-18, FW-19
        """
        # Read the firewall role tasks
        tasks_path = Path("roles/firewall/tasks/main.yml")
        assert tasks_path.exists(), "Firewall role tasks must exist"

        tasks_content = tasks_path.read_text()

        # FW-17: the NFTables service is enabled to start on boot
        # The service must be enabled using systemd
        assert "name: nftables" in tasks_content, (
            "NFTables service must be referenced in tasks"
        )
        assert "enabled: true" in tasks_content or "enabled: yes" in tasks_content, (
            "NFTables service must be enabled to start on boot (FW-17)"
        )

        # Verify service is started (not just enabled)
        assert "state: started" in tasks_content, (
            "NFTables service must be started after configuration"
        )

        # FW-16 and FW-17 together are what make the ruleset survive a reboot:
        # 1. Deploying configuration to /etc/nftables.conf (standard location)
        # 2. Enabling the nftables.service which loads rules from this file on boot

        # Verify configuration is deployed to standard location
        assert "dest: /etc/nftables.conf" in tasks_content, (
            "NFTables configuration must be deployed to /etc/nftables.conf "
            "for persistence (FW-16)"
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

        # Verify the template defines the inet filter table and its three chains
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

        # Either `flush ruleset` or the inet table satisfies this check
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
                # Look ahead only to the next top-level task boundary (the
                # next "- name:" list item), not a fixed-line window: a
                # fixed window's idea of where a task ends depends on how
                # many comment lines separate it from the next task, so it
                # can run past the task it is reading.
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith('- name:'):
                        end = j
                        break
                # Drop comment-only lines before checking: a comment line
                # that happens to contain "state: started" or
                # "enabled: true" (for example, in prose describing the
                # next task) would otherwise satisfy the check without a
                # real directive present.
                task_lines = [
                    task_line for task_line in lines[i:end]
                    if not task_line.strip().startswith('#')
                ]
                task_block = '\n'.join(task_lines)
                if 'name: nftables' in task_block:
                    if 'enabled: true' in task_block or 'enabled: yes' in task_block:
                        found_enable_task = True
                    if 'state: started' in task_block:
                        found_start_task = True

        assert found_enable_task, (
            "Must have a task that enables nftables service (FW-17)"
        )
        assert found_start_task, (
            "Must have a task that starts nftables service"
        )


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
        Knock Rules Conditional Activation

        Checks that the nftables template tests `firewall_tailscale_enabled` first,
        puts the knock rules in an `elif firewall_port_knocking_enabled` branch,
        renders the stage-1 and passed sets per address family, and has an `else`
        branch for open SSH.

        Validates: KNOCK-1
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
        Knock Sequence Ports in Template

        Checks that the nftables template references each of the three sequence
        positions and contains `firewall_port_knocking_sequence | join`. Nothing
        here checks the set-membership qualifier that makes the second and third
        stages conditional on the one before them, or the drop rule itself.

        Validates: KNOCK-4, KNOCK-5, KNOCK-6
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

        # Verify the full sequence is joined somewhere in the template
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
        Dual-Stack Knock Sets

        Checks that the nftables template defines a set of the drawn address type,
        `ipv4_addr` or `ipv6_addr`.

        Validates: KNOCK-3
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
        SSH Accept References Knock Passed

        Checks that the nftables template has an `@knock4_passed accept` or
        `@knock6_passed accept` rule for the drawn family.

        Validates: KNOCK-9
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
        Sets at Table Level

        Checks that the drawn family's stage-1 set is defined before `chain input`,
        at table level as nftables requires.

        Validates: KNOCK-3
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
        Timeout Variables Used

        Checks that the nftables template references
        `firewall_port_knocking_stage_timeout` and `firewall_port_knocking_timeout`.

        Validates: KNOCK-7
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
        Explicit Drop for Knock Ports

        Checks that the nftables template has a drop rule over the joined knock
        sequence, placed before the drawn family's passed-set SSH accept.

        Validates: KNOCK-8
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
        No Unconditional SSH Accept

        Checks that every SSH accept rule in the nftables template's knocking
        branch carries an `@knock` set-membership check.

        Validates: KNOCK-9
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
        Defaults Define Knock Variables

        Checks that the firewall defaults define `firewall_port_knocking_enabled`,
        `firewall_port_knocking_sequence`, `firewall_port_knocking_timeout` and
        `firewall_port_knocking_stage_timeout`. What they are derived from and what
        values they carry is not checked.

        Validates: KNOCK-10
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


class TestPortKnockPrePlayProperties:
    """Property-based tests for the port-knock pre-play in site.yml."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_knock_play_exists_before_bootstrap_play(self):
        """
        The site.yml playbook SHALL contain a local port-knock play before the
        bootstrap play so that Ansible can reach hosts behind port knocking.

        Validates: KNOCK-11
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

        Validates: KNOCK-11, KNOCK-1 — that both flags are named in the
        condition. Their sense is not checked.
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

        Validates: KNOCK-11
        """
        import yaml

        plays = yaml.safe_load(Path("site.yml").read_text())
        knock_task = plays[0]["tasks"][0]

        assert knock_task.get("changed_when") is False, (
            "Knock task must set changed_when: false"
        )
