"""
Unit tests for the ssh_hardening role.

Tests specific SSHD configuration directives, algorithm restriction lists,
AllowGroups directive content, and SSH interface restriction based on Tailscale status.

Approach: render the sshd_config.j2 Jinja2 template with known variable sets
and assert on the rendered output content.

Requirements: SSH-1, SSH-2, SSH-3, SSH-4, SSH-5, SSH-6, SSH-7, SSH-8, SSH-9,
SSH-10, SSH-11, SSH-12, SSH-13, SSH-14, SSH-15, SSH-16, SSH-18
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


@pytest.fixture
def ssh_env() -> Environment:
    template_dir = ROLES_DIR / "ssh_hardening" / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)))


@pytest.fixture
def base_vars() -> dict:
    return {
        "ssh_port": 22,
        "ssh_max_auth_tries": 3,
        "ssh_login_grace_time": "30s",
        "ssh_client_alive_interval": 300,
        "ssh_client_alive_count_max": 2,
        "ssh_kex_algorithms": [
            "sntrup761x25519-sha512",
            "curve25519-sha256",
            "curve25519-sha256@libssh.org",
            "diffie-hellman-group16-sha512",
            "diffie-hellman-group18-sha512",
        ],
        "ssh_ciphers": [
            "chacha20-poly1305@openssh.com",
            "aes256-gcm@openssh.com",
            "aes128-gcm@openssh.com",
        ],
        "ssh_macs": [
            "hmac-sha2-512-etm@openssh.com",
            "hmac-sha2-256-etm@openssh.com",
        ],
        "ssh_access_group": "ssh-users",
        "ssh_listen_address_ipv4": "0.0.0.0",
        "ssh_listen_address_ipv6": "::",
        "tailscale_enabled": False,
        "tailscale_ipv4": "",
    }


def render_sshd_config(env: Environment, variables: dict) -> str:
    template = env.get_template("sshd_config.j2")
    return template.render(**variables)


class TestSSHDConfigDirectives:
    """SSHD directives: SSH-1, SSH-2, SSH-3, SSH-4, SSH-8, SSH-9, SSH-10, SSH-11, SSH-13."""

    def test_password_authentication_disabled(self, ssh_env, base_vars):
        """SSH-1: PasswordAuthentication must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "PasswordAuthentication no" in config

    def test_root_login_disabled(self, ssh_env, base_vars):
        """SSH-2: PermitRootLogin must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "PermitRootLogin no" in config

    def test_pubkey_authentication_enabled(self, ssh_env, base_vars):
        """SSH-3: PubkeyAuthentication must be yes.

        Covers only the positive half of SSH-3. Nothing in this repository
        asserts ChallengeResponseAuthentication is off, which is the half that
        keeps PAM from offering a password over the network.
        """
        config = render_sshd_config(ssh_env, base_vars)
        assert "PubkeyAuthentication yes" in config

    def test_empty_passwords_disabled(self, ssh_env, base_vars):
        """SSH-4: PermitEmptyPasswords must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "PermitEmptyPasswords no" in config

    def test_x11_forwarding_disabled(self, ssh_env, base_vars):
        """SSH-8: X11Forwarding must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "X11Forwarding no" in config

    def test_tcp_forwarding_disabled(self, ssh_env, base_vars):
        """SSH-9: AllowTcpForwarding must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "AllowTcpForwarding no" in config

    def test_agent_forwarding_disabled(self, ssh_env, base_vars):
        """SSH-10: AllowAgentForwarding must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "AllowAgentForwarding no" in config

    def test_tunneling_disabled(self, ssh_env, base_vars):
        """SSH-11: PermitTunnel must be no."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "PermitTunnel no" in config

    def test_ssh_port_rendered(self, ssh_env, base_vars):
        """SSH-13: Port directive must reflect the configured port."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "Port 22" in config

    def test_custom_ssh_port(self, ssh_env, base_vars):
        """SSH-13: a custom port is rendered, and the default is not left behind."""
        base_vars["ssh_port"] = 2222
        config = render_sshd_config(ssh_env, base_vars)
        assert "Port 2222" in config
        assert "Port 22\n" not in config


class TestAlgorithmRestrictions:
    """Cryptographic algorithm restriction lists: SSH-5, SSH-6, SSH-7."""

    def test_kex_algorithms_present(self, ssh_env, base_vars):
        """SSH-5: every configured key exchange algorithm is rendered.

        Presence only. Nothing here asserts the order, and nothing needs to:
        the client's preference, not the server's, decides what is negotiated.
        """
        config = render_sshd_config(ssh_env, base_vars)
        assert "sntrup761x25519-sha512" in config
        assert "curve25519-sha256" in config
        assert "curve25519-sha256@libssh.org" in config
        assert "diffie-hellman-group16-sha512" in config
        assert "diffie-hellman-group18-sha512" in config

    def test_kex_algorithms_comma_separated(self, ssh_env, base_vars):
        """SSH-5: KexAlgorithms must be a comma-separated list on one line."""
        config = render_sshd_config(ssh_env, base_vars)
        kex_line = next(line for line in config.splitlines() if line.startswith("KexAlgorithms "))
        assert "," in kex_line

    def test_ciphers_are_aead_only(self, ssh_env, base_vars):
        """SSH-6: each configured AEAD cipher is rendered."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "chacha20-poly1305@openssh.com" in config
        assert "aes256-gcm@openssh.com" in config
        assert "aes128-gcm@openssh.com" in config

    def test_ciphers_comma_separated(self, ssh_env, base_vars):
        """SSH-6: Ciphers must be a comma-separated list on one line."""
        config = render_sshd_config(ssh_env, base_vars)
        cipher_line = next(line for line in config.splitlines() if line.startswith("Ciphers "))
        assert "," in cipher_line

    def test_macs_are_etm_only(self, ssh_env, base_vars):
        """SSH-7: each configured Encrypt-Then-MAC variant is rendered."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "hmac-sha2-512-etm@openssh.com" in config
        assert "hmac-sha2-256-etm@openssh.com" in config

    def test_macs_comma_separated(self, ssh_env, base_vars):
        """SSH-7: MACs must be a comma-separated list on one line."""
        config = render_sshd_config(ssh_env, base_vars)
        mac_line = next(line for line in config.splitlines() if line.startswith("MACs "))
        assert "," in mac_line

    def test_no_weak_kex_algorithms(self, ssh_env, base_vars):
        """SSH-5: four named excluded key exchange algorithms must not appear.

        A denylist, not an allowlist: a weak algorithm not named here passes.
        """
        config = render_sshd_config(ssh_env, base_vars)
        assert "diffie-hellman-group14" not in config
        # group1 and group-sha1 are weak; group16/18 are allowed — check word boundaries
        assert "diffie-hellman-group1-" not in config
        assert "diffie-hellman-group-sha1" not in config
        assert "ecdh-sha2-nistp" not in config

    def test_no_cbc_ciphers(self, ssh_env, base_vars):
        """SSH-6: three named CBC-mode ciphers must not appear.

        A denylist, not an allowlist: a non-AEAD cipher not named here passes.
        """
        config = render_sshd_config(ssh_env, base_vars)
        assert "aes256-cbc" not in config
        assert "aes128-cbc" not in config
        assert "3des-cbc" not in config

    def test_no_non_etm_macs(self, ssh_env, base_vars):
        """SSH-7: three named non-ETM MACs must not appear.

        A denylist, not an allowlist, and the first check is anchored to a
        line ending rather than to the MACs directive.
        """
        config = render_sshd_config(ssh_env, base_vars)
        assert "hmac-sha2-512\n" not in config
        assert "hmac-sha1" not in config
        assert "hmac-md5" not in config


class TestAllowGroupsDirective:
    """Tests for the AllowGroups directive: SSH-12."""

    def test_allow_groups_contains_ssh_access_group(self, ssh_env, base_vars):
        """SSH-12: AllowGroups must include the ssh access group."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "AllowGroups" in config
        allow_line = next(line for line in config.splitlines() if line.startswith("AllowGroups "))
        assert "ssh-users" in allow_line

    def test_allow_groups_with_custom_group(self, ssh_env, base_vars):
        """SSH-12: AllowGroups reflects a custom configured group name."""
        base_vars["ssh_access_group"] = "custom-ssh"
        config = render_sshd_config(ssh_env, base_vars)
        allow_line = next(line for line in config.splitlines() if line.startswith("AllowGroups "))
        assert "custom-ssh" in allow_line

    def test_allow_groups_single_group_by_default(self, ssh_env, base_vars):
        """SSH-12: AllowGroups contains exactly one group."""
        config = render_sshd_config(ssh_env, base_vars)
        allow_line = next(line for line in config.splitlines() if line.startswith("AllowGroups "))
        groups = allow_line.replace("AllowGroups ", "").split()
        assert len(groups) == 1


class TestSessionSecurity:
    """Tests for session security settings: SSH-14, SSH-15, SSH-16."""

    def test_max_auth_tries(self, ssh_env, base_vars):
        """SSH-14: MaxAuthTries renders the configured value."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "MaxAuthTries 3" in config

    def test_login_grace_time(self, ssh_env, base_vars):
        """SSH-15: LoginGraceTime renders the configured value."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "LoginGraceTime 30s" in config

    def test_client_alive_interval(self, ssh_env, base_vars):
        """SSH-16: ClientAliveInterval renders the configured value."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "ClientAliveInterval 300" in config

    def test_client_alive_count_max(self, ssh_env, base_vars):
        """SSH-16: ClientAliveCountMax renders the configured value."""
        config = render_sshd_config(ssh_env, base_vars)
        assert "ClientAliveCountMax 2" in config

    def test_custom_session_values(self, ssh_env, base_vars):
        """SSH-14, SSH-15, SSH-16: custom session values are rendered correctly."""
        base_vars["ssh_max_auth_tries"] = 5
        base_vars["ssh_login_grace_time"] = "60s"
        base_vars["ssh_client_alive_interval"] = 600
        base_vars["ssh_client_alive_count_max"] = 3
        config = render_sshd_config(ssh_env, base_vars)
        assert "MaxAuthTries 5" in config
        assert "LoginGraceTime 60s" in config
        assert "ClientAliveInterval 600" in config
        assert "ClientAliveCountMax 3" in config


class TestSSHInterfaceRestriction:
    """Tests for the SSH-18 ListenAddress binding, on both branches."""

    def test_listen_all_interfaces_when_tailscale_disabled(self, ssh_env, base_vars):
        """SSH-18: with Tailscale disabled, sshd binds all interfaces."""
        base_vars["tailscale_enabled"] = False
        config = render_sshd_config(ssh_env, base_vars)
        assert "ListenAddress 0.0.0.0" in config
        assert "ListenAddress ::" in config

    def test_listen_tailscale_only_when_enabled(self, ssh_env, base_vars):
        """SSH-18: with Tailscale enabled, sshd binds the tailnet addresses only."""
        base_vars["tailscale_enabled"] = True
        base_vars["tailscale_ipv4"] = "100.64.0.1"
        base_vars["tailscale_ipv6"] = "fd7a:115c:a1e0::1"
        config = render_sshd_config(ssh_env, base_vars)
        assert "ListenAddress 100.64.0.1" in config
        assert "ListenAddress fd7a:115c:a1e0::1" in config
        assert "ListenAddress 0.0.0.0" not in config
        assert "ListenAddress ::" not in config

    def test_tailscale_ip_reflected_in_listen_address(self, ssh_env, base_vars):
        """SSH-18: the published tailnet addresses are the ones bound."""
        base_vars["tailscale_enabled"] = True
        base_vars["tailscale_ipv4"] = "100.100.42.7"
        base_vars["tailscale_ipv6"] = "fd7a:115c:a1e0::7"
        config = render_sshd_config(ssh_env, base_vars)
        assert "ListenAddress 100.100.42.7" in config
        assert "ListenAddress fd7a:115c:a1e0::7" in config
