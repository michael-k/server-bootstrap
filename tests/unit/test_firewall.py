"""
Unit tests for the firewall role.

Tests NFTables rule structure, IPv4/IPv6 dual-stack parity, conditional SSH
access rules based on Tailscale status, and default drop policies.

Approach: render the nftables.conf.j2 Jinja2 template with known variable sets
and assert on the rendered output content.

Requirements: 8.1-8.11
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


@pytest.fixture
def fw_env() -> Environment:
    template_dir = ROLES_DIR / "firewall" / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)))


@pytest.fixture
def base_vars() -> dict:
    """Default firewall variables — Tailscale disabled."""
    return {
        "firewall_ssh_port": 22,
        "firewall_tailscale_enabled": False,
        "firewall_tailscale_interface": "tailscale0",
        "firewall_tailscale_ipv4": "",
        "firewall_wireguard_port": 41641,
    }


@pytest.fixture
def tailscale_vars(base_vars) -> dict:
    """Firewall variables with Tailscale enabled."""
    return {
        **base_vars,
        "firewall_tailscale_enabled": True,
        "firewall_tailscale_ipv4": "100.64.0.1",
    }


def render_nftables(env: Environment, variables: dict) -> str:
    template = env.get_template("nftables.conf.j2")
    return template.render(**variables)


class TestNFTablesRuleStructure:
    """Tests for NFTables rule structure and syntax (Requirements 8.1, 8.2)."""

    def test_uses_inet_family(self, fw_env, base_vars):
        """Req 8.1, 8.2: inet family covers both IPv4 and IPv6."""
        config = render_nftables(fw_env, base_vars)
        assert "table inet filter" in config

    def test_input_chain_defined(self, fw_env, base_vars):
        """Req 8.5: input chain must be defined."""
        config = render_nftables(fw_env, base_vars)
        assert "chain input {" in config

    def test_forward_chain_defined(self, fw_env, base_vars):
        """Req 8.6: forward chain must be defined."""
        config = render_nftables(fw_env, base_vars)
        assert "chain forward {" in config

    def test_flush_ruleset_present(self, fw_env, base_vars):
        """Config starts with flush ruleset to ensure clean state."""
        config = render_nftables(fw_env, base_vars)
        assert "flush ruleset" in config

    def test_output_chain_defined(self, fw_env, base_vars):
        """Output chain should be defined (accept all outbound)."""
        config = render_nftables(fw_env, base_vars)
        assert "chain output {" in config


class TestDefaultPolicies:
    """Tests for default drop policies (Requirements 8.5, 8.6)."""

    def test_input_chain_default_drop(self, fw_env, base_vars):
        """Req 8.5: input chain default policy must be drop."""
        config = render_nftables(fw_env, base_vars)
        assert "hook input priority 0; policy drop;" in config

    def test_forward_chain_default_drop(self, fw_env, base_vars):
        """Req 8.6: forward chain default policy must be drop."""
        config = render_nftables(fw_env, base_vars)
        assert "hook forward priority 0; policy drop;" in config

    def test_established_related_accepted(self, fw_env, base_vars):
        """Req 8.3: established and related connections must be accepted."""
        config = render_nftables(fw_env, base_vars)
        assert "ct state established,related accept" in config

    def test_loopback_accepted(self, fw_env, base_vars):
        """Req 8.4: loopback interface traffic must be accepted."""
        config = render_nftables(fw_env, base_vars)
        assert "iif lo accept" in config


class TestDualStackRules:
    """Tests for IPv4 and IPv6 rule parity (Requirements 8.1, 8.2)."""

    def test_inet_table_covers_both_stacks(self, fw_env, base_vars):
        """Req 8.1, 8.2: Single inet table handles both IPv4 and IPv6."""
        config = render_nftables(fw_env, base_vars)
        # inet family is the nftables way to handle both stacks in one table
        assert "table inet filter" in config
        # Should NOT have separate ip and ip6 tables
        assert "table ip filter" not in config
        assert "table ip6 filter" not in config

    def test_icmp_rules_for_both_stacks(self, fw_env, base_vars):
        """Both ICMPv4 and ICMPv6 should be allowed for network diagnostics."""
        config = render_nftables(fw_env, base_vars)
        assert "ip protocol icmp accept" in config
        assert "ip6 nexthdr icmpv6 accept" in config


class TestSSHAccessRules:
    """Tests for conditional SSH access rules (Requirements 8.7, 8.8)."""

    def test_ssh_allowed_from_all_when_tailscale_disabled(self, fw_env, base_vars):
        """Req 8.8: When Tailscale disabled, SSH is allowed from all interfaces."""
        config = render_nftables(fw_env, base_vars)
        assert "tcp dport 22 accept" in config
        # Must NOT restrict to a specific interface
        assert 'iifname "tailscale0" tcp dport 22 accept' not in config

    def test_ssh_restricted_to_tailscale_when_enabled(self, fw_env, tailscale_vars):
        """Req 8.7: When Tailscale enabled, SSH is restricted to Tailscale interface."""
        config = render_nftables(fw_env, tailscale_vars)
        assert 'iifname "tailscale0" tcp dport 22 accept' in config

    def test_ssh_not_allowed_from_all_when_tailscale_enabled(self, fw_env, tailscale_vars):
        """Req 8.7: When Tailscale enabled, unrestricted SSH rule must not appear."""
        config = render_nftables(fw_env, tailscale_vars)
        lines = config.splitlines()
        # The bare "tcp dport 22 accept" without iifname must not exist
        bare_ssh = [
            line for line in lines
            if "tcp dport 22 accept" in line and "iifname" not in line
        ]
        assert len(bare_ssh) == 0, f"Found unrestricted SSH rule: {bare_ssh}"

    def test_custom_ssh_port_in_rules(self, fw_env, base_vars):
        """Req 8.7, 8.8: Custom SSH port is reflected in firewall rules."""
        base_vars["firewall_ssh_port"] = 2222
        config = render_nftables(fw_env, base_vars)
        assert "tcp dport 2222 accept" in config
        assert "tcp dport 22 accept" not in config

    def test_custom_ssh_port_with_tailscale(self, fw_env, tailscale_vars):
        """Req 8.7: Custom SSH port is restricted to Tailscale interface."""
        tailscale_vars["firewall_ssh_port"] = 2222
        config = render_nftables(fw_env, tailscale_vars)
        assert 'iifname "tailscale0" tcp dport 2222 accept' in config

    def test_wireguard_allowed_when_tailscale_enabled(self, fw_env, tailscale_vars):
        """Req 8.9: Tailscale WireGuard UDP traffic must be allowed when enabled."""
        config = render_nftables(fw_env, tailscale_vars)
        assert "udp dport 41641 accept" in config

    def test_wireguard_not_present_when_tailscale_disabled(self, fw_env, base_vars):
        """Req 8.9: WireGuard rule must not appear when Tailscale is disabled."""
        config = render_nftables(fw_env, base_vars)
        assert "udp dport 41641 accept" not in config

    def test_custom_wireguard_port(self, fw_env, tailscale_vars):
        """Req 8.9: Custom WireGuard port is reflected in firewall rules."""
        tailscale_vars["firewall_wireguard_port"] = 51820
        config = render_nftables(fw_env, tailscale_vars)
        assert "udp dport 51820 accept" in config

    def test_custom_tailscale_interface_name(self, fw_env, tailscale_vars):
        """Req 8.7: Custom Tailscale interface name is used in SSH restriction rule."""
        tailscale_vars["firewall_tailscale_interface"] = "ts0"
        config = render_nftables(fw_env, tailscale_vars)
        assert 'iifname "ts0" tcp dport 22 accept' in config
