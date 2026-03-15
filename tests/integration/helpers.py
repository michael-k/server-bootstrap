"""Bootstrap-specific playbook wrappers and test constants.

These are server-bootstrap specific and not part of the shared incus package.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from incus.ansible import _get_ssh_public_key_file, run_playbook
from incus.vm import IncusVM

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TEST_VARS: dict[str, str | int | bool | list[int]] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    # Generated with: openssl passwd -6 -salt testsalt 'TestPassword123!'
    "manual_user_password": (
        "$6$testsalt$5P2FnhrAYcA6OcEmW5HOdQx2s/g5RDF/pjLq9r43iwy.jOyY9Ap0uReLp0zSd"
        "/WR6.609JYtDYaQVnBIlY3zG/"
    ),
    "manual_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "deploy_user_name": "ansible",
    "deploy_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "ssh_port": 22,
    "target_hostname": "bootstrap-test",
    "port_knocking_sequence": [7000, 8500, 9100],
    "tailscale_enabled": False,
    "swap_enabled": False,
    # Login policy defaults (must match roles/users/defaults/main.yml)
    "login_policy_umask": "027",
    "login_policy_retries": 3,
    "login_policy_timeout": 30,
    # PAM hardening defaults (must match roles/users/defaults/main.yml)
    "pam_faillock_deny": 5,
}


def run_bootstrap_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    limit_to_role: str | list[str] | None = None,
    timeout: int = 600,
    check_mode: bool = False,
    user: str = "root",
) -> subprocess.CompletedProcess:
    """Run site.yml (or a single role) against the VM."""
    pub_key_path = _get_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    result = run_playbook(
        vm,
        playbook_path=WORKSPACE_ROOT / "site.yml",
        extra_vars=merged_vars,
        roles=limit_to_role,
        check_mode=check_mode,
        user=user,
        timeout=timeout,
        cwd=WORKSPACE_ROOT,
        roles_path=WORKSPACE_ROOT / "roles",
    )

    # Update the VM's SSH port to match what the playbook configured
    if result.returncode == 0:
        ssh_port = merged_vars.get("ssh_port", 22)
        vm.ssh_port = ssh_port if isinstance(ssh_port, int) else int(ssh_port)  # type: ignore[arg-type]

    return result


def run_verify_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    timeout: int = 300,
    user: str = "ansible",
) -> subprocess.CompletedProcess:
    """Run verify_bootstrap.yml against the VM."""
    pub_key_path = _get_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    return run_playbook(
        vm,
        playbook_path=WORKSPACE_ROOT / "tests" / "verify_bootstrap.yml",
        extra_vars=merged_vars,
        user=user,
        timeout=timeout,
        cwd=WORKSPACE_ROOT,
    )
