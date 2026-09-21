"""Ephemeral SSH keypair management for Incus VM testing.

INCUS-7: one fresh passphrase-less ed25519 keypair per VM, in a directory of
its own, private key at mode 0600 -- unless the caller passes ``IncusVM`` an
``ssh_key`` of its own, which nothing stops it from sharing between machines.

INCUS-8: ``cleanup()`` is what removes the key from the controller's disk.
Nothing here calls it -- ``IncusVM.destroy()`` does, and nothing guarantees
that anybody calls ``destroy()``; in this repository the pytest fixtures are
what make the removal reliable.

INCUS-1 is violated twice below: the temp directory prefix and the key
comment spell ``bootstrap-test`` out literally instead of reading
``VM_NAME_PREFIX``, so a consuming repository inherits this project's name
even if that constant is ever made configurable.  Recorded, not fixed.
"""


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
