"""Unit tests for IncusVM command construction and parsing."""


import json
from unittest.mock import MagicMock, patch

import pytest

from incus.vm import IncusVM

pytestmark = pytest.mark.unit


class TestIncusVMCreate:
    @patch("incus.vm.subprocess.run")
    @patch("incus.vm.SSHKeyPair.create")
    def test_create_calls_incus_launch_with_vm_flag(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM.create(image="images:debian/13")

        launch_call = mock_run.call_args_list[0]
        cmd = launch_call[0][0]
        assert "incus" in cmd[0]
        assert "launch" in cmd
        assert "--vm" in cmd
        assert "images:debian/13" in cmd
        assert vm.name.startswith("bootstrap-test-")

    @patch("incus.vm.subprocess.run")
    @patch("incus.vm.SSHKeyPair.create")
    def test_create_does_not_use_cloud_init(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        IncusVM.create(image="images:debian/13")

        launch_call = mock_run.call_args_list[0]
        cmd = launch_call[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "cloud-init" not in cmd_str
        assert "user.user-data" not in cmd_str


class TestIncusVMName:
    @patch("incus.vm.subprocess.run")
    @patch("incus.vm.SSHKeyPair.create")
    def test_name_uses_prefix_and_random_suffix(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM.create(image="images:debian/13")
        assert vm.name.startswith("bootstrap-test-")
        suffix = vm.name[len("bootstrap-test-"):]
        assert len(suffix) > 0

    @patch("incus.vm.subprocess.run")
    @patch("incus.vm.SSHKeyPair.create")
    def test_name_hint_is_incorporated(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock(
            public_key="ssh-ed25519 AAAA test",
            private_key_path="/tmp/fake/id_ed25519",
        )
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM.create(image="images:debian/13", name_hint="myvm")
        assert "myvm" in vm.name


class TestIncusVMDestroy:
    def test_destroy_calls_incus_delete_force(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock()
        vm._image = "images:debian/13"

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.destroy()

        cmd = mock_run.call_args[0][0]
        assert cmd == ["incus", "delete", "bootstrap-test-abc123", "--force"]
        vm.ssh_key.cleanup.assert_called_once()


class TestIncusVMGetIP:
    def test_get_ip_parses_json_output(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock()
        vm._image = "images:debian/13"

        mock_output = json.dumps([{
            "name": "bootstrap-test-abc123",
            "state": {
                "network": {
                    "enp5s0": {
                        "addresses": [
                            {"family": "inet", "address": "10.0.0.42", "scope": "global"},
                        ]
                    }
                }
            }
        }])

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
            ip = vm.get_ip()

        assert ip == "10.0.0.42"


class TestIncusVMExec:
    def test_exec_builds_correct_command(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock()
        vm._image = "images:debian/13"

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.exec("whoami")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["incus", "exec", "bootstrap-test-abc123", "--", "sh", "-c", "whoami"]


class TestIncusVMSSH:
    def test_ssh_builds_correct_command(self):
        vm = IncusVM.__new__(IncusVM)
        vm.name = "bootstrap-test-abc123"
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")
        vm.ip_address = "10.0.0.42"
        vm._image = "images:debian/13"

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "-i" in cmd
        assert "/tmp/fake/id_ed25519" in cmd
        assert "root@10.0.0.42" in cmd
        assert "whoami" in cmd
