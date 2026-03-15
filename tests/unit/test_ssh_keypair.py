"""Unit tests for ephemeral SSH keypair management."""


import pytest

from incus.ssh import SSHKeyPair

pytestmark = pytest.mark.unit


class TestSSHKeyPairCreate:
    def test_creates_private_key_file(self):
        kp = SSHKeyPair.create("test-vm")
        try:
            assert kp.private_key_path.exists()
        finally:
            kp.cleanup()

    def test_private_key_has_restricted_permissions(self):
        kp = SSHKeyPair.create("test-vm")
        try:
            mode = kp.private_key_path.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            kp.cleanup()

    def test_public_key_is_nonempty_string(self):
        kp = SSHKeyPair.create("test-vm")
        try:
            assert isinstance(kp.public_key, str)
            assert len(kp.public_key) > 0
            assert "ssh-ed25519" in kp.public_key
        finally:
            kp.cleanup()

    def test_private_key_in_unique_temp_directory(self):
        kp1 = SSHKeyPair.create("vm-a")
        kp2 = SSHKeyPair.create("vm-b")
        try:
            assert kp1.private_key_path.parent != kp2.private_key_path.parent
        finally:
            kp1.cleanup()
            kp2.cleanup()


class TestSSHKeyPairCleanup:
    def test_cleanup_removes_private_key(self):
        kp = SSHKeyPair.create("test-vm")
        key_path = kp.private_key_path
        kp.cleanup()
        assert not key_path.exists()

    def test_cleanup_removes_temp_directory(self):
        kp = SSHKeyPair.create("test-vm")
        temp_dir = kp.private_key_path.parent
        kp.cleanup()
        assert not temp_dir.exists()

    def test_cleanup_idempotent(self):
        kp = SSHKeyPair.create("test-vm")
        kp.cleanup()
        kp.cleanup()  # Should not raise
