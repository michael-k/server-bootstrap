"""Unit tests for Ansible playbook execution helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from incus.ansible import (
    build_inventory,
    build_single_role_playbook,
    run_playbook,
)
from incus.vm import IncusVM

pytestmark = pytest.mark.unit

_SSH_KEY = MagicMock(private_key_path=Path("/tmp/fake/id_ed25519"))
_VM = IncusVM(name="bootstrap-test-abc123", ssh_key=_SSH_KEY, ip_address="10.0.0.42")


class TestBuildInventory:
    def test_generates_valid_yaml_inventory(self):
        content = build_inventory(_VM)
        inv = yaml.safe_load(content)

        assert "all" in inv
        host_vars = inv["all"]["hosts"]["testvm"]
        assert host_vars["ansible_host"] == "10.0.0.42"
        assert host_vars["ansible_ssh_private_key_file"] == "/tmp/fake/id_ed25519"
        assert host_vars["ansible_user"] == "root"
        assert host_vars["ansible_port"] == 22

    def test_uses_vm_ssh_port(self):
        vm = IncusVM(
            name="bootstrap-test-abc123", ssh_key=_SSH_KEY,
            ip_address="10.0.0.42", ssh_port=2222,
        )

        content = build_inventory(vm)
        inv = yaml.safe_load(content)
        assert inv["all"]["hosts"]["testvm"]["ansible_port"] == 2222

    def test_uses_custom_user(self):
        content = build_inventory(_VM, user="ansible")
        inv = yaml.safe_load(content)
        assert inv["all"]["hosts"]["testvm"]["ansible_user"] == "ansible"


class TestBuildSingleRolePlaybook:
    def test_generates_playbook_with_single_role(self):
        content = build_single_role_playbook("ssh_hardening")
        playbook = yaml.safe_load(content)

        assert len(playbook) == 1
        play = playbook[0]
        assert play["become"] is True
        assert {"role": "ssh_hardening"} in play["roles"]

    def test_generates_playbook_with_role_list(self):
        content = build_single_role_playbook(["users", "ssh_hardening"])
        playbook = yaml.safe_load(content)

        play = playbook[0]
        assert len(play["roles"]) == 2
        assert {"role": "users"} in play["roles"]
        assert {"role": "ssh_hardening"} in play["roles"]


class TestRunPlaybook:
    @patch("incus.ansible.subprocess.run")
    def test_runs_ansible_playbook_directly(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        run_playbook(_VM, playbook_path=Path("/tmp/site.yml"))

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ansible-playbook"
        cmd_str = " ".join(str(c) for c in cmd)
        assert "/tmp/site.yml" in cmd_str

    @patch("incus.ansible.subprocess.run")
    def test_passes_extra_vars_via_json_file(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        run_playbook(_VM, playbook_path=Path("/tmp/site.yml"), extra_vars={"ssh_port": 2222})

        cmd = mock_run.call_args[0][0]
        extra_var_args = [c for c in cmd if str(c).startswith("@")]
        assert len(extra_var_args) == 1
        assert "-e" in cmd

    @patch("incus.ansible.subprocess.run")
    def test_passes_cwd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        run_playbook(_VM, playbook_path=Path("/tmp/site.yml"), cwd="/some/dir")

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == "/some/dir"

    @patch("incus.ansible.subprocess.run")
    def test_does_not_mutate_vm_ssh_port(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        run_playbook(_VM, playbook_path=Path("/tmp/site.yml"), extra_vars={"ssh_port": 2222})

        # run_playbook should NOT mutate vm.ssh_port
        assert _VM.ssh_port == 22
