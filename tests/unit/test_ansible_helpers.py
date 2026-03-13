"""Unit tests for Ansible playbook execution helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tests.infra.ansible import (
    build_inventory,
    build_single_role_playbook,
    run_bootstrap_playbook,
)

pytestmark = pytest.mark.unit


class TestBuildInventory:
    def test_generates_valid_yaml_inventory(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm)
        inv = yaml.safe_load(content)

        assert "all" in inv
        host_vars = inv["all"]["hosts"]["testvm"]
        assert host_vars["ansible_host"] == "10.0.0.42"
        assert host_vars["ansible_ssh_private_key_file"] == "/tmp/fake/id_ed25519"
        assert host_vars["ansible_user"] == "root"

    def test_uses_custom_ssh_port(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm, ssh_port=2222)
        inv = yaml.safe_load(content)
        assert inv["all"]["hosts"]["testvm"]["ansible_port"] == 2222


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


class TestRunBootstrapPlaybook:
    @patch("tests.infra.ansible._write_ssh_public_key_file")
    @patch("tests.infra.ansible.subprocess.run")
    def test_uses_site_yml_by_default(self, mock_run, mock_write_key):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        mock_write_key.return_value = Path("/tmp/fake/id_ed25519.pub")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(
            private_key_path=Path("/tmp/fake/id_ed25519"),
            public_key="ssh-ed25519 AAAA test",
        )

        run_bootstrap_playbook(vm)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "site.yml" in cmd_str

    @patch("tests.infra.ansible._write_ssh_public_key_file")
    @patch("tests.infra.ansible.subprocess.run")
    def test_passes_extra_vars_via_json_file(self, mock_run, mock_write_key):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        mock_write_key.return_value = Path("/tmp/fake/id_ed25519.pub")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(
            private_key_path=Path("/tmp/fake/id_ed25519"),
            public_key="ssh-ed25519 AAAA test",
        )

        run_bootstrap_playbook(vm, extra_vars={"ssh_port": 2222})

        cmd = mock_run.call_args[0][0]
        # Extra vars are passed via @<json_file>
        extra_var_args = [c for c in cmd if str(c).startswith("@")]
        assert len(extra_var_args) == 1
        assert "-e" in cmd


class TestRunVerifyPlaybook:
    @patch("tests.infra.ansible.subprocess.run")
    def test_uses_verify_playbook(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_key = MagicMock(
            private_key_path=Path("/tmp/fake/id_ed25519"),
            public_key="ssh-ed25519 AAAA test",
        )

        from tests.infra.ansible import run_verify_playbook
        run_verify_playbook(vm)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "verify_bootstrap.yml" in cmd_str
