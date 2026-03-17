"""Ansible playbook execution helpers for Incus VM testing."""


import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from incus.vm import IncusVM


def build_inventory(vm: IncusVM, user: str = "root") -> str:
    """Generate a YAML inventory string pointing at the VM."""
    inventory = {
        "all": {
            "hosts": {
                "testvm": {
                    "ansible_host": vm.ip_address,
                    "ansible_user": user,
                    "ansible_port": vm.ssh_port,
                    "ansible_ssh_private_key_file": str(vm.private_key_path),
                    "ansible_python_interpreter": "/usr/bin/python3",
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
    """Return the path to the VM's SSH public key file."""
    return vm.private_key_path.with_suffix(".pub")


def run_playbook(
    vm: IncusVM,
    playbook_path: str | Path,
    extra_vars: dict | None = None,
    roles: str | list[str] | None = None,
    check_mode: bool = False,
    user: str = "root",
    timeout: int = 600,
    cwd: str | Path | None = None,
    roles_path: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """Run an Ansible playbook against a VM.

    Args:
        vm: The target VM.
        playbook_path: Path to the playbook YAML file.
        extra_vars: Additional Ansible variables.
        roles: If provided, generate a temporary single-role playbook instead.
        check_mode: Run Ansible in check mode (--check).
        user: SSH user for the inventory.
        timeout: Subprocess timeout in seconds.
        cwd: Working directory for the ansible-playbook process.
        roles_path: Custom ANSIBLE_ROLES_PATH for single-role playbooks.
    """
    tmp_dir = tempfile.mkdtemp(prefix="incus-ansible-")
    tmp_path = Path(tmp_dir)

    inv_path = tmp_path / "inventory.yml"
    inv_path.write_text(build_inventory(vm, user=user))

    vars_path = None
    if extra_vars:
        vars_path = tmp_path / "extra_vars.json"
        vars_path.write_text(json.dumps(extra_vars))

    if roles:
        pb_path = tmp_path / "playbook.yml"
        pb_path.write_text(build_single_role_playbook(roles))
        actual_playbook = str(pb_path)
    else:
        actual_playbook = str(playbook_path)

    cmd = [
        "ansible-playbook",
        "-i", str(inv_path),
        actual_playbook,
    ]
    if vars_path:
        cmd.extend(["-e", f"@{vars_path}"])
    if check_mode:
        cmd.append("--check")

    env = None
    if roles and roles_path:
        env = {**os.environ, "ANSIBLE_ROLES_PATH": str(roles_path)}

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            check=False,
            env=env,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
