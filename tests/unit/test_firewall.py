"""
Unit tests for the firewall role.

Tests NFTables rule structure, IPv4/IPv6 dual-stack parity, conditional SSH
access rules based on Tailscale status, and default drop policies.

Approach: render the nftables.conf.j2 Jinja2 template with known variable sets
and assert on the rendered output content.

Requirements: FW-2, FW-3, FW-4, FW-5, FW-6, FW-7, FW-8, FW-9, FW-10,
FW-11, FW-12, FW-13, FW-14, FW-15
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


def _ansible_bool(value: object) -> bool:
    """Mimic Ansible's ``bool`` Jinja2 filter for unit-test rendering."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return bool(value)


@pytest.fixture
def fw_env() -> Environment:
    template_dir = ROLES_DIR / "firewall" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.filters["bool"] = _ansible_bool
    return env


@pytest.fixture
def base_vars() -> dict:
    """Default firewall variables — Tailscale disabled, port knocking disabled."""
    return {
        "firewall_ssh_port": 22,
        "firewall_tailscale_enabled": False,
        "firewall_tailscale_interface": "tailscale0",
        "firewall_tailscale_ipv4": "",
        "firewall_wireguard_port": 41641,
        "firewall_port_knocking_enabled": False,
        "firewall_port_knocking_sequence": [7000, 8500, 9100],
        "firewall_port_knocking_timeout": 30,
        "firewall_port_knocking_stage_timeout": 5,
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
    """Tests for NFTables rule structure and syntax: FW-2, FW-3, FW-4, FW-5, FW-15."""

    def test_uses_inet_family(self, fw_env, base_vars):
        """FW-2: the inet family covers both IPv4 and IPv6 in one table."""
        config = render_nftables(fw_env, base_vars)
        assert "table inet filter" in config

    def test_input_chain_defined(self, fw_env, base_vars):
        """FW-3: an input chain must be defined for the policy to sit on."""
        config = render_nftables(fw_env, base_vars)
        assert "chain input {" in config

    def test_forward_chain_defined(self, fw_env, base_vars):
        """FW-4: a forward chain must be defined for the policy to sit on."""
        config = render_nftables(fw_env, base_vars)
        assert "chain forward {" in config

    def test_flush_ruleset_present(self, fw_env, base_vars):
        """FW-15: the ruleset replaces what is loaded rather than adding to it."""
        config = render_nftables(fw_env, base_vars)
        assert "flush ruleset" in config

    def test_output_chain_defined(self, fw_env, base_vars):
        """FW-5: an output chain must be defined. Its policy is checked by the
        property suite, not here."""
        config = render_nftables(fw_env, base_vars)
        assert "chain output {" in config


class TestDefaultPolicies:
    """Tests for the default policies and the unconditional accepts: FW-3, FW-4,
    FW-6, FW-7."""

    def test_input_chain_default_drop(self, fw_env, base_vars):
        """FW-3: the input chain default policy must be drop."""
        config = render_nftables(fw_env, base_vars)
        assert "hook input priority 0; policy drop;" in config

    def test_forward_chain_default_drop(self, fw_env, base_vars):
        """FW-4: the forward chain default policy must be drop."""
        config = render_nftables(fw_env, base_vars)
        assert "hook forward priority 0; policy drop;" in config

    def test_established_related_accepted(self, fw_env, base_vars):
        """FW-6: established and related connections must be accepted."""
        config = render_nftables(fw_env, base_vars)
        assert "ct state established,related accept" in config

    def test_loopback_accepted(self, fw_env, base_vars):
        """FW-7: loopback interface traffic must be accepted."""
        config = render_nftables(fw_env, base_vars)
        assert "iif lo accept" in config


class TestDualStackRules:
    """Tests for IPv4 and IPv6 rule parity: FW-2, FW-8, FW-9."""

    def test_inet_table_covers_both_stacks(self, fw_env, base_vars):
        """FW-2: a single inet table handles both families, with no second table."""
        config = render_nftables(fw_env, base_vars)
        # inet family is the nftables way to handle both stacks in one table
        assert "table inet filter" in config
        # Should NOT have separate ip and ip6 tables
        assert "table ip filter" not in config
        assert "table ip6 filter" not in config

    def test_icmp_rules_for_both_stacks(self, fw_env, base_vars):
        """FW-8, FW-9: ICMPv4 and ICMPv6 are both accepted."""
        config = render_nftables(fw_env, base_vars)
        assert "ip protocol icmp accept" in config
        assert "ip6 nexthdr icmpv6 accept" in config


class TestSSHAccessRules:
    """Tests for the conditional SSH and WireGuard rules: FW-10, FW-11, FW-12,
    FW-13, FW-14."""

    def test_ssh_allowed_from_all_when_tailscale_disabled(self, fw_env, base_vars):
        """FW-13: with Tailscale and knocking off, SSH is accepted on every interface."""
        config = render_nftables(fw_env, base_vars)
        assert "tcp dport 22 accept" in config
        # Must NOT restrict to a specific interface
        assert 'iifname "tailscale0" tcp dport 22 accept' not in config

    def test_ssh_restricted_to_tailscale_when_enabled(self, fw_env, tailscale_vars):
        """FW-10: with Tailscale on, SSH is accepted only on the tailnet interface."""
        config = render_nftables(fw_env, tailscale_vars)
        assert 'iifname "tailscale0" tcp dport 22 accept' in config

    def test_ssh_not_allowed_from_all_when_tailscale_enabled(self, fw_env, tailscale_vars):
        """FW-10: with Tailscale on, no unrestricted SSH rule may appear."""
        config = render_nftables(fw_env, tailscale_vars)
        lines = config.splitlines()
        # The bare "tcp dport 22 accept" without iifname must not exist
        bare_ssh = [
            line for line in lines
            if "tcp dport 22 accept" in line and "iifname" not in line
        ]
        assert len(bare_ssh) == 0, f"Found unrestricted SSH rule: {bare_ssh}"

    def test_custom_ssh_port_in_rules(self, fw_env, base_vars):
        """FW-14: the configured SSH port is the one the rule names."""
        base_vars["firewall_ssh_port"] = 2222
        config = render_nftables(fw_env, base_vars)
        assert "tcp dport 2222 accept" in config
        assert "tcp dport 22 accept" not in config

    def test_custom_ssh_port_with_tailscale(self, fw_env, tailscale_vars):
        """FW-14: the configured SSH port is used on the tailnet branch too."""
        tailscale_vars["firewall_ssh_port"] = 2222
        config = render_nftables(fw_env, tailscale_vars)
        assert 'iifname "tailscale0" tcp dport 2222 accept' in config

    def test_wireguard_allowed_when_tailscale_enabled(self, fw_env, tailscale_vars):
        """FW-12: WireGuard UDP traffic is accepted when Tailscale is enabled."""
        config = render_nftables(fw_env, tailscale_vars)
        assert "udp dport 41641 accept" in config

    def test_wireguard_not_present_when_tailscale_disabled(self, fw_env, base_vars):
        """FW-12: the WireGuard rule is absent when Tailscale is disabled."""
        config = render_nftables(fw_env, base_vars)
        assert "udp dport 41641 accept" not in config

    def test_custom_wireguard_port(self, fw_env, tailscale_vars):
        """FW-12: a configured WireGuard port is the one the rule names."""
        tailscale_vars["firewall_wireguard_port"] = 51820
        config = render_nftables(fw_env, tailscale_vars)
        assert "udp dport 51820 accept" in config

    def test_custom_tailscale_interface_name(self, fw_env, tailscale_vars):
        """FW-11: the configured interface name is the one the SSH rule matches."""
        tailscale_vars["firewall_tailscale_interface"] = "ts0"
        config = render_nftables(fw_env, tailscale_vars)
        assert 'iifname "ts0" tcp dport 22 accept' in config
