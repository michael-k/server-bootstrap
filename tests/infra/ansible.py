"""Ansible playbook execution helpers for integration testing."""


import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from tests.infra.constants import DEFAULT_TEST_VARS

if TYPE_CHECKING:
    from tests.infra.vm import IncusVM

WORKSPACE_ROOT = Path(__file__).parent.parent.parent


def build_inventory(vm: IncusVM, ssh_port: int = 22) -> str:
    """Generate a YAML inventory string pointing at the VM."""
    inventory = {
        "all": {
            "hosts": {
                "testvm": {
                    "ansible_host": vm.ip_address,
                    "ansible_user": "root",
                    "ansible_port": ssh_port,
                    "ansible_ssh_private_key_file": str(vm.ssh_key.private_key_path),
                    "ansible_ssh_common_args": "-o StrictHostKeyChecking=no",
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


def _write_ssh_public_key_file(vm: IncusVM) -> Path:
    """Write the VM's SSH public key to a temp file for Ansible to read."""
    pub_key_path = vm.ssh_key.private_key_path.with_suffix(".pub")
    if not pub_key_path.exists():
        pub_key_path.write_text(vm.ssh_key.public_key + "\n")
    return pub_key_path


def run_bootstrap_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    limit_to_role: str | list[str] | None = None,
    timeout: int = 600,
    check_mode: bool = False,
) -> subprocess.CompletedProcess:
    """Run site.yml (or a single role) against the VM."""
    pub_key_path = _write_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["ansible_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    tmp_dir = tempfile.mkdtemp(prefix="bootstrap-ansible-")
    tmp_path = Path(tmp_dir)

    inv_path = tmp_path / "inventory.yml"
    inv_path.write_text(build_inventory(vm))

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


def run_verify_playbook(
    vm: IncusVM,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run verify_bootstrap.yml against the VM."""
    tmp_dir = tempfile.mkdtemp(prefix="bootstrap-verify-")
    inv_path = Path(tmp_dir) / "inventory.yml"
    inv_path.write_text(build_inventory(vm))

    cmd = [
        "uv", "run", "ansible-playbook",
        "-i", str(inv_path),
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
