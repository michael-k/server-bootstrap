"""
Unit tests for emergency access script generation.

Tests the Jinja2 template rendering with specific variables, verifies the
sed command patterns used for unrestrict/restore modes, and checks that
service restart commands are present.

The existing test_emergency_script_edge_cases.py covers runtime execution
(missing files, service failures, idempotency). This module focuses on
template generation correctness.

Requirements: 9.1-9.8
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


@pytest.fixture
def ea_env() -> Environment:
    template_dir = ROLES_DIR / "emergency_access" / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)))


@pytest.fixture
def base_vars() -> dict:
    return {
        "emergency_access_ssh_port": "22",
        "emergency_access_tailscale_interface": "tailscale0",
        "emergency_access_tailscale_ipv4": "100.64.0.1",
    }


def render_script(env: Environment, variables: dict) -> str:
    template = env.get_template("emergency-ssh-access.sh.j2")
    return template.render(**variables)


class TestScriptGeneration:
    """Tests for script generation with specific variable values (Requirement 9.1)."""

    def test_script_is_bash(self, ea_env, base_vars):
        """Generated script must start with bash shebang."""
        script = render_script(ea_env, base_vars)
        assert script.strip().startswith("#!/bin/bash")

    def test_ssh_port_embedded(self, ea_env, base_vars):
        """SSH port variable is rendered into the script."""
        script = render_script(ea_env, base_vars)
        assert 'SSH_PORT="22"' in script

    def test_tailscale_interface_embedded(self, ea_env, base_vars):
        """Tailscale interface variable is rendered into the script."""
        script = render_script(ea_env, base_vars)
        assert 'TAILSCALE_INTERFACE="tailscale0"' in script

    def test_tailscale_ipv4_embedded(self, ea_env, base_vars):
        """Tailscale IPv4 address variable is rendered into the script."""
        script = render_script(ea_env, base_vars)
        assert 'TAILSCALE_IPV4="100.64.0.1"' in script

    def test_custom_port_rendered(self, ea_env, base_vars):
        """Custom SSH port is correctly embedded."""
        base_vars["emergency_access_ssh_port"] = "2222"
        script = render_script(ea_env, base_vars)
        assert 'SSH_PORT="2222"' in script
        assert 'SSH_PORT="22"' not in script

    def test_custom_interface_rendered(self, ea_env, base_vars):
        """Custom Tailscale interface name is correctly embedded."""
        base_vars["emergency_access_tailscale_interface"] = "ts0"
        script = render_script(ea_env, base_vars)
        assert 'TAILSCALE_INTERFACE="ts0"' in script

    def test_custom_tailscale_ip_rendered(self, ea_env, base_vars):
        """Custom Tailscale IP is correctly embedded."""
        base_vars["emergency_access_tailscale_ipv4"] = "100.100.42.7"
        script = render_script(ea_env, base_vars)
        assert 'TAILSCALE_IPV4="100.100.42.7"' in script

    def test_sshd_config_path_hardcoded(self, ea_env, base_vars):
        """SSHD config path must be /etc/ssh/sshd_config."""
        script = render_script(ea_env, base_vars)
        assert 'SSHD_CONFIG="/etc/ssh/sshd_config"' in script

    def test_nftables_config_path_hardcoded(self, ea_env, base_vars):
        """NFTables config path must be /etc/nftables.conf."""
        script = render_script(ea_env, base_vars)
        assert 'NFTABLES_CONFIG="/etc/nftables.conf"' in script

    def test_script_deployed_to_root(self, ea_env, base_vars):
        """Script is generated (deployment path is /root/ per requirement 9.1)."""
        # Verify the template renders without error — deployment path is in the
        # Ansible task, not the script itself. Just confirm it renders cleanly.
        script = render_script(ea_env, base_vars)
        assert len(script) > 0

    def test_usage_comment_present(self, ea_env, base_vars):
        """Script includes usage documentation."""
        script = render_script(ea_env, base_vars)
        assert "--restore" in script
        assert "Usage:" in script


class TestUnrestrictModeSedCommands:
    """Tests for sed commands in unrestrict mode (Requirement 9.2)."""

    def test_unrestrict_replaces_tailscale_ip_with_all_interfaces(self, ea_env, base_vars):
        """Req 9.2: Unrestrict mode sed replaces Tailscale IP with 0.0.0.0."""
        script = render_script(ea_env, base_vars)
        # The sed command should replace the Tailscale IP ListenAddress
        assert "ListenAddress 0.0.0.0" in script
        assert "ListenAddress ::" in script

    def test_unrestrict_sed_uses_tailscale_ipv4_var(self, ea_env, base_vars):
        """Req 9.2: Unrestrict sed pattern references TAILSCALE_IPV4 variable."""
        script = render_script(ea_env, base_vars)
        # The sed command in unrestrict_ssh function uses ${TAILSCALE_IPV4}
        assert "${TAILSCALE_IPV4}" in script

    def test_unrestrict_removes_interface_restriction_from_nftables(self, ea_env, base_vars):
        """Req 9.2: Unrestrict mode sed removes iifname restriction from nftables."""
        script = render_script(ea_env, base_vars)
        # sed replaces the iifname-restricted rule with a bare tcp dport rule
        assert 'iifname \\"${TAILSCALE_INTERFACE}\\" tcp dport ${SSH_PORT} accept' in script
        # The replacement target (bare rule) should also appear
        assert "tcp dport ${SSH_PORT} accept" in script

    def test_unrestrict_idempotency_check_present(self, ea_env, base_vars):
        """Req 9.7: Unrestrict mode checks current state before making changes."""
        script = render_script(ea_env, base_vars)
        assert "already unrestricted" in script

    def test_unrestrict_function_defined(self, ea_env, base_vars):
        """Req 9.2: unrestrict_ssh function must be defined."""
        script = render_script(ea_env, base_vars)
        assert "unrestrict_ssh()" in script


class TestRestoreModeSedCommands:
    """Tests for sed commands in restore mode (Requirement 9.3)."""

    def test_restore_removes_all_listen_address_lines(self, ea_env, base_vars):
        """Req 9.3: Restore mode sed deletes all ListenAddress directives."""
        script = render_script(ea_env, base_vars)
        # sed -i '/^ListenAddress /d' removes all ListenAddress lines
        assert "'/^ListenAddress /d'" in script

    def test_restore_adds_tailscale_listen_address(self, ea_env, base_vars):
        """Req 9.3: Restore mode adds Tailscale IP as ListenAddress after Port."""
        script = render_script(ea_env, base_vars)
        # sed inserts ListenAddress after the Port directive
        assert "ListenAddress ${TAILSCALE_IPV4}" in script
        assert "/^Port ${SSH_PORT}/a" in script

    def test_restore_adds_interface_restriction_to_nftables(self, ea_env, base_vars):
        """Req 9.3: Restore mode sed adds iifname restriction to nftables SSH rule."""
        script = render_script(ea_env, base_vars)
        # sed replaces bare tcp dport rule with iifname-restricted rule
        assert 'iifname \\"${TAILSCALE_INTERFACE}\\" tcp dport ${SSH_PORT} accept' in script

    def test_restore_idempotency_check_present(self, ea_env, base_vars):
        """Req 9.7: Restore mode checks current state before making changes."""
        script = render_script(ea_env, base_vars)
        assert "already restricted" in script

    def test_restore_function_defined(self, ea_env, base_vars):
        """Req 9.3: restore_ssh function must be defined."""
        script = render_script(ea_env, base_vars)
        assert "restore_ssh()" in script


class TestServiceRestartCommands:
    """Tests for service restart commands (Requirements 9.5, 9.6)."""

    def test_sshd_restart_command_present(self, ea_env, base_vars):
        """Req 9.5: Script must restart SSHD after configuration changes."""
        script = render_script(ea_env, base_vars)
        assert "systemctl restart sshd" in script

    def test_nftables_reload_command_present(self, ea_env, base_vars):
        """Req 9.6: Script must reload NFTables after configuration changes."""
        script = render_script(ea_env, base_vars)
        assert "systemctl reload nftables" in script

    def test_sshd_restart_failure_handled(self, ea_env, base_vars):
        """Req 9.5: Script handles SSHD restart failure with error message."""
        script = render_script(ea_env, base_vars)
        assert "Failed to restart SSH daemon" in script

    def test_nftables_reload_failure_handled(self, ea_env, base_vars):
        """Req 9.6: Script handles NFTables reload failure with error message."""
        script = render_script(ea_env, base_vars)
        assert "Failed to reload NFTables rules" in script

    def test_both_services_restarted_in_unrestrict(self, ea_env, base_vars):
        """Req 9.5, 9.6: Both services are restarted in unrestrict mode."""
        script = render_script(ea_env, base_vars)
        # Both restart commands appear (at least twice — once per mode)
        assert script.count("systemctl restart sshd") >= 2
        assert script.count("systemctl reload nftables") >= 2

    def test_root_check_present(self, ea_env, base_vars):
        """Script must check for root privileges before executing."""
        script = render_script(ea_env, base_vars)
        assert "check_root" in script
        assert "EUID" in script

    def test_file_validation_present(self, ea_env, base_vars):
        """Script must validate config files exist before proceeding."""
        script = render_script(ea_env, base_vars)
        assert "validate_files" in script

    def test_backup_function_present(self, ea_env, base_vars):
        """Script must back up config files before making changes."""
        script = render_script(ea_env, base_vars)
        assert "backup_configs" in script
