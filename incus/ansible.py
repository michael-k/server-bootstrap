"""Ansible playbook execution helpers for integration testing."""


import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from incus.constants import DEFAULT_TEST_VARS

if TYPE_CHECKING:
    from incus.vm import IncusVM

WORKSPACE_ROOT = Path(__file__).parent.parent


def build_inventory(vm: IncusVM, user: str = "root") -> str:
    """Generate a YAML inventory string pointing at the VM."""
    inventory = {
        "all": {
            "hosts": {
                "testvm": {
                    "ansible_host": vm.ip_address,
                    "ansible_user": user,
                    "ansible_port": vm.ssh_port,
                    "ansible_ssh_private_key_file": str(vm.ssh_key.private_key_path),
                    "ansible_ssh_common_args": (
                        "-o PubkeyAuthentication=yes "
                        "-o IdentitiesOnly=yes "
                        "-o StrictHostKeyChecking=no "
                        "-o UserKnownHostsFile=/dev/null"
                    ),
                }
            }
        }
    }
    return yaml.dump(inventory, default_flow_style=False)


def build_single_role_playbook(roles: str | list[str]) -> str:
    """Generate a minimal playbook YAML for testing specific roles."""
    if isinstance(roles, str):
        roles = [roles]

    playbook = [
        {
            "name": "Test single role",
            "hosts": "all",
            "become": True,
            "gather_facts": True,
            "roles": [{"role": r} for r in roles],
        }
    ]
    return yaml.dump(playbook, default_flow_style=False)


def _get_ssh_public_key_file(vm: IncusVM) -> Path:
    """Return the path to the VM's SSH public key file.

    ssh-keygen creates the .pub file alongside the private key,
    so it always exists after SSHKeyPair.create().
    """
    return vm.ssh_key.private_key_path.with_suffix(".pub")


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

    tmp_dir = tempfile.mkdtemp(prefix="bootstrap-ansible-")
    tmp_path = Path(tmp_dir)

    inv_path = tmp_path / "inventory.yml"
    inv_path.write_text(build_inventory(vm, user=user))

    vars_path = tmp_path / "extra_vars.json"
    vars_path.write_text(json.dumps(merged_vars))

    if limit_to_role:
        pb_path = tmp_path / "playbook.yml"
        pb_path.write_text(build_single_role_playbook(limit_to_role))
        playbook_path = str(pb_path)
    else:
        playbook_path = str(WORKSPACE_ROOT / "site.yml")

    cmd = [
        "uv", "run", "ansible-playbook",
        "-i", str(inv_path),
        "-e", f"@{vars_path}",
        playbook_path,
    ]
    if check_mode:
        cmd.append("--check")

    env = None
    if limit_to_role:
        import os
        env = {**os.environ, "ANSIBLE_ROLES_PATH": str(WORKSPACE_ROOT / "roles")}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
            check=False,
            env=env,
        )
        # Update the VM's SSH port to match what the playbook configured,
        # so subsequent ssh() calls and inventory builds use the right port.
        if result.returncode == 0:
            ssh_port = merged_vars.get("ssh_port", 22)
            vm.ssh_port = ssh_port if isinstance(ssh_port, int) else int(ssh_port)  # type: ignore[arg-type]
        return result
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_verify_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    timeout: int = 300,
    user: str = "ansible",
) -> subprocess.CompletedProcess:
    """Run verify_bootstrap.yml against the VM.

    Defaults to the deploy user (ansible) since root SSH is disabled
    after bootstrap hardening.
    """
    pub_key_path = _get_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    tmp_dir = tempfile.mkdtemp(prefix="bootstrap-verify-")
    tmp_path = Path(tmp_dir)

    inv_path = tmp_path / "inventory.yml"
    inv_path.write_text(build_inventory(vm, user=user))

    vars_path = tmp_path / "extra_vars.json"
    vars_path.write_text(json.dumps(merged_vars))

    cmd = [
        "uv", "run", "ansible-playbook",
        "-i", str(inv_path),
        "-e", f"@{vars_path}",
        str(WORKSPACE_ROOT / "tests" / "verify_bootstrap.yml"),
    ]

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
            check=False,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
