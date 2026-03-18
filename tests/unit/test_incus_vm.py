"""Unit tests for IncusVM command construction and parsing."""


import json
from unittest.mock import MagicMock, patch

import pytest

from incus.vm import IncusVM, ensure_base_image

pytestmark = pytest.mark.unit


class TestIncusVMLaunch:
    @patch("incus.vm.ensure_base_image", return_value="bootstrap/internal-base-13")
    def test_launch_calls_incus_launch_with_vm_flag(self, _mock_ensure):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock(), image="images:debian/13")

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.launch()

        cmd = mock_run.call_args[0][0]
        assert "incus" in cmd[0]
        assert "launch" in cmd
        assert "--vm" in cmd

    @patch("incus.vm.ensure_base_image", return_value="bootstrap/internal-base-13")
    def test_launch_does_not_use_cloud_init(self, _mock_ensure):
        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock(), image="images:debian/13")

        with patch("incus.vm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            vm.launch()

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "cloud-init" not in cmd_str
        assert "user.user-data" not in cmd_str

    def test_launch_raises_with_empty_image(self):
        vm = IncusVM(image="", name="bootstrap-test-abc123", ssh_key=MagicMock())
        with pytest.raises(ValueError, match="image is required"):
            vm.launch()

    @patch("incus.vm.ensure_base_image", return_value="bootstrap/internal-base-13")
    @patch("incus.vm.subprocess.run")
    @patch("incus.vm.SSHKeyPair.create")
    def test_auto_launch_calls_launch(self, mock_keypair, mock_run, _mock_ensure):
        mock_keypair.return_value = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM(image="images:debian/13", auto_launch=True)

        cmd = mock_run.call_args[0][0]
        assert "launch" in cmd
        assert vm.name.startswith("bootstrap-test-")

    @patch("incus.vm.ensure_base_image")
    @patch("incus.vm.subprocess.run")
    def test_launch_swaps_debian_image_for_base(self, mock_run, mock_ensure):
        mock_ensure.return_value = "bootstrap/internal-base-13"
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock(), image="images:debian/13")
        vm.launch()

        mock_ensure.assert_called_once_with("13")
        cmd = mock_run.call_args[0][0]
        assert "bootstrap/internal-base-13" in cmd
        assert "images:debian/13" not in cmd

    @patch("incus.vm.ensure_base_image")
    @patch("incus.vm.subprocess.run")
    def test_launch_skips_swap_for_bootstrap_images(self, mock_run, mock_ensure):
        mock_run.return_value = MagicMock(returncode=0)

        vm = IncusVM(name="bootstrap-test-abc123", ssh_key=MagicMock(), image="bootstrap/open-13")
        vm.launch()

        mock_ensure.assert_not_called()
        cmd = mock_run.call_args[0][0]
        assert "bootstrap/open-13" in cmd


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


class TestEnsureBaseImage:
    @patch("incus.vm.subprocess.run")
    def test_returns_existing_when_fingerprint_matches(self, mock_run):
        upstream_fp = "abc123"

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "image" in cmd and "info" in cmd and "images:debian" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({"fingerprint": upstream_fp}),
                )
            if "image" in cmd and "list" in cmd and "internal-base" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps([{
                    "fingerprint": "localfp",
                    "aliases": [{"name": "bootstrap/internal-base-13"}],
                    "properties": {"user.upstream_fingerprint": upstream_fp},
                }]))
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect
        assert ensure_base_image("13") == "bootstrap/internal-base-13"

        # No launch or publish should have happened
        launched = [c for c in mock_run.call_args_list if "launch" in c[0][0]]
        assert len(launched) == 0

    @patch("incus.vm.subprocess.run")
    def test_builds_when_missing(self, mock_run):
        upstream_fp = "abc123"

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "image" in cmd and "info" in cmd and "images:debian" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({"fingerprint": upstream_fp}),
                )
            if "image" in cmd and "list" in cmd and "internal-base" in cmd_str:
                return MagicMock(returncode=0, stdout="[]")
            if "exec" in cmd and "agent-ready" in cmd:
                return MagicMock(returncode=0, stdout="agent-ready")
            if "exec" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect
        assert ensure_base_image("13") == "bootstrap/internal-base-13"

        publish_calls = [c for c in mock_run.call_args_list if "publish" in c[0][0]]
        assert len(publish_calls) == 1
        assert f"user.upstream_fingerprint={upstream_fp}" in publish_calls[0][0][0]

    @patch("incus.vm.subprocess.run")
    def test_rebuilds_when_fingerprint_stale(self, mock_run):
        old_fp = "old123"
        new_fp = "new456"

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "image" in cmd and "info" in cmd and "images:debian" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({"fingerprint": new_fp}),
                )
            if "image" in cmd and "list" in cmd and "internal-base" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps([{
                    "fingerprint": "localfp",
                    "aliases": [{"name": "bootstrap/internal-base-13"}],
                    "properties": {"user.upstream_fingerprint": old_fp},
                }]))
            if "exec" in cmd and "agent-ready" in cmd:
                return MagicMock(returncode=0, stdout="agent-ready")
            if "exec" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect
        assert ensure_base_image("13") == "bootstrap/internal-base-13"

        # Old image should have been deleted
        image_deletes = [
            c for c in mock_run.call_args_list
            if "image" in c[0][0] and "delete" in c[0][0]
        ]
        assert len(image_deletes) == 1

        # New image published with new fingerprint
        publish_calls = [c for c in mock_run.call_args_list if "publish" in c[0][0]]
        assert len(publish_calls) == 1
        assert f"user.upstream_fingerprint={new_fp}" in publish_calls[0][0][0]
