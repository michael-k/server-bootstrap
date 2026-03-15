"""
Shared fixtures for unit tests.

Provides Jinja2 environment factories and common variable sets
used across all unit test modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"


@pytest.fixture
def jinja_env():
    """Factory fixture that creates a Jinja2 Environment for a given role's templates directory."""

    def _make_env(role_name: str) -> Environment:
        template_dir = ROLES_DIR / role_name / "templates"
        return Environment(loader=FileSystemLoader(str(template_dir)))

    return _make_env


@pytest.fixture
def render_template(jinja_env):
    """Helper fixture that renders a template with given variables."""

    def _render(role_name: str, template_name: str, variables: dict) -> str:
        env = jinja_env(role_name)
        template = env.get_template(template_name)
        return template.render(**variables)

    return _render


@pytest.fixture
def default_users_vars() -> dict:
    """Default variable set for the users role."""
    return {
        "manual_user_name": "admin",
        "manual_user_uid": 1000,
        "deploy_user_name": "ansible",
        "deploy_user_uid": 1999,
        "authorized_keys_mode": "0600",
    }


@pytest.fixture
def default_ssh_vars() -> dict:
    """Default variable set for the ssh_hardening role."""
    return {
        "ssh_port": 22,
        "ssh_max_auth_tries": 3,
        "ssh_login_grace_time": "30s",
        "ssh_client_alive_interval": 300,
        "ssh_client_alive_count_max": 2,
        "ssh_kex_algorithms": [
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


@pytest.fixture
def default_firewall_vars() -> dict:
    """Default variable set for the firewall role."""
    return {
        "firewall_ssh_port": 22,
        "firewall_tailscale_enabled": False,
        "firewall_tailscale_interface": "tailscale0",
        "firewall_tailscale_ipv4": "",
        "firewall_wireguard_port": 41641,
    }


@pytest.fixture
def default_fail2ban_vars() -> dict:
    """Default variable set for the fail2ban role."""
    return {
        "fail2ban_max_retry": 5,
        "fail2ban_ban_time": "10m",
        "fail2ban_find_time": "10m",
        "fail2ban_ssh_enabled": True,
        "fail2ban_ssh_backend": "systemd",
        "fail2ban_banaction": "nftables-multiport",
        "ssh_port": 22,
    }


@pytest.fixture
def default_logging_vars() -> dict:
    """Default variable set for the logging role."""
    return {
        "journald_max_disk_usage": "500M",
        "journald_max_retention_time": "1month",
    }


@pytest.fixture
def default_swap_vars() -> dict:
    """Default variable set for the swap role."""
    return {
        "zram_enabled": False,
        "zram_size": "50%",
        "disk_swap_size": "",
        "zram_swap_priority": 100,
        "disk_swap_priority": 10,
    }


@pytest.fixture
def default_system_config_vars() -> dict:
    """Default variable set for the system_config role."""
    return {
        "system_hostname": "",
        "time_sync_service": "chrony",
        "ntp_servers": [
            "0.debian.pool.ntp.org",
            "1.debian.pool.ntp.org",
            "2.debian.pool.ntp.org",
            "3.debian.pool.ntp.org",
        ],
    }
