"""Unit tests for IncusVM command construction and parsing."""


import json
from unittest.mock import MagicMock, patch

import pytest

from incus.vm import IncusVM

pytestmark = pytest.mark.unit


class TestIncusVMLaunch:
    def test_launch_calls_incus_launch_with_vm_flag(self):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock(), image="images:debian/13")

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.launch()

        cmd = mock_run.call_args[0][0]
        assert "incus" in cmd[0]
        assert "launch" in cmd
        assert "--vm" in cmd
        assert "images:debian/13" in cmd

    def test_launch_does_not_use_cloud_init(self):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock(), image="images:debian/13")

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.launch()

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "cloud-init" not in cmd_str
        assert "user.user-data" not in cmd_str

    def test_launch_raises_without_image(self):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock())
        with pytest.raises(ValueError, match="image is required"):
            vm.launch()

    @patch("incus.vm.subprocess.run")
    @patch("incus.vm.SSHKeyPair.create")
    def test_auto_launch_calls_launch(self, mock_keypair, mock_run):
        mock_keypair.return_value = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM(image="images:debian/13", auto_launch=True)

        cmd = mock_run.call_args[0][0]
        assert "launch" in cmd
        assert vm.name.startswith("bootstrap-test-")


class TestIncusVMName:
    @patch("incus.vm.SSHKeyPair.create")
    def test_name_uses_prefix_and_random_suffix(self, mock_keypair):
        mock_keypair.return_value = MagicMock()

        vm = IncusVM()
        assert vm.name.startswith("bootstrap-test-")
        suffix = vm.name[len("bootstrap-test-"):]
        assert len(suffix) > 0

    @patch("incus.vm.SSHKeyPair.create")
    def test_name_hint_is_incorporated(self, mock_keypair):
        mock_keypair.return_value = MagicMock()

        vm = IncusVM(name_hint="myvm")
        assert "myvm" in vm.name


class TestIncusVMDestroy:
    def test_destroy_calls_incus_delete_force(self):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock())

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.destroy()

        cmd = mock_run.call_args[0][0]
        assert cmd == ["incus", "delete", "bootstrap-test-abc123", "--force"]
        vm._ssh_key.cleanup.assert_called_once()


class TestIncusVMGetIP:
    def test_get_ip_parses_json_output(self):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock())

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
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock())

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.exec("whoami")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["incus", "exec", "bootstrap-test-abc123", "--", "sh", "-c", "whoami"]


_SSH_KEY = MagicMock(private_key_path="/tmp/fake/id_ed25519")


class TestIncusVMSSH:
    def test_ssh_builds_correct_command(self):
        vm = IncusVM(
            name="bootstrap-test-abc123", ssh_key=_SSH_KEY, ip_address="10.0.0.42",
        )

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "-i" in cmd
        assert "/tmp/fake/id_ed25519" in cmd
        assert "root@10.0.0.42" in cmd
        assert "whoami" in cmd

    def test_ssh_uses_configured_user(self):
        vm = IncusVM(
            name="bootstrap-test-abc123", ssh_key=_SSH_KEY, ip_address="10.0.0.42",
            ssh_user="deploy",
        )

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        cmd = mock_run.call_args[0][0]
        assert "deploy@10.0.0.42" in cmd

    def test_ssh_auto_knocks_when_sequence_set_and_stale(self):
        vm = IncusVM(
            name="bootstrap-test-abc123", ssh_key=_SSH_KEY, ip_address="10.0.0.42",
            knock_sequence=[7000, 8500, 9100],
        )

        with (
            patch("incus.vm.subprocess.run") as mock_run,
            patch.object(vm, "knock") as mock_knock,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        mock_knock.assert_called_once()

    def test_ssh_skips_knock_when_recent(self):
        import time as _time

        vm = IncusVM(
            name="bootstrap-test-abc123", ssh_key=_SSH_KEY, ip_address="10.0.0.42",
            knock_sequence=[7000, 8500, 9100],
        )
        vm._last_knock_time = _time.monotonic()  # just knocked

        with (
            patch("incus.vm.subprocess.run") as mock_run,
            patch.object(vm, "knock") as mock_knock,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        mock_knock.assert_not_called()

    def test_ssh_no_knock_without_sequence(self):
        vm = IncusVM(
            name="bootstrap-test-abc123", ssh_key=_SSH_KEY, ip_address="10.0.0.42",
        )

        with (
            patch("incus.vm.subprocess.run") as mock_run,
            patch.object(vm, "knock") as mock_knock,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            vm.ssh("whoami")

        mock_knock.assert_not_called()
