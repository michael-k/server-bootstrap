"""Ephemeral SSH keypair management for Incus VM testing."""


import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SSHKeyPair:
    """An ephemeral ed25519 SSH keypair for VM access."""

    private_key_path: Path
    public_key: str
    _temp_dir: Path = field(repr=False, compare=False)

    @classmethod
    def create(cls, name: str) -> SSHKeyPair:
        """Generate a new ed25519 keypair in a unique temp directory.

        Args:
            name: Used in the key comment and temp directory name.
        """
        temp_dir = Path(tempfile.mkdtemp(prefix=f"bootstrap-test-{name}-"))
        key_path = temp_dir / "id_ed25519"

        subprocess.run(
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-f", str(key_path),
                "-N", "",
                "-C", f"bootstrap-test-{name}",
            ],
            capture_output=True,
            check=True,
        )

        key_path.chmod(0o600)
        public_key = key_path.with_suffix(".pub").read_text().strip()

        return cls(
            private_key_path=key_path,
            public_key=public_key,
            _temp_dir=temp_dir,
        )

    def cleanup(self) -> None:
        """Remove the keypair and its temp directory."""
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
