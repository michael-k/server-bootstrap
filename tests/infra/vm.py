"""Incus VM lifecycle management for integration testing."""


import json
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from tests.infra.constants import (
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_POLL_INTERVAL_SECONDS,
    VM_NAME_PREFIX,
    VM_READY_TIMEOUT_SECONDS,
)
from tests.infra.ssh import SSHKeyPair


@dataclass
class IncusVM:
    """Manages a single Incus VM for testing."""

    name: str
    ssh_key: SSHKeyPair
    ip_address: str = ""
    ssh_port: int = 22
    _image: str = ""

    @classmethod
    def create(cls, image: str, name_hint: str = "") -> IncusVM:
        """Launch a new Incus VM.

        The Debian cloud images don't include cloud-init, so SSH setup
        is handled in wait_ready() via incus exec after the VM boots.
        """
        suffix = secrets.token_hex(4)
        name = f"{VM_NAME_PREFIX}{name_hint + '-' if name_hint else ''}{suffix}"

        ssh_key = SSHKeyPair.create(name)

        subprocess.run(
            ["incus", "launch", image, name, "--vm"],
            capture_output=True,
            text=True,
            check=True,
        )

        return cls(name=name, ssh_key=ssh_key, _image=image)

    def destroy(self) -> None:
        """Force-delete the VM and clean up SSH keys."""
        subprocess.run(
            ["incus", "delete", self.name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.ssh_key.cleanup()

    def wait_ready(self, timeout: int = VM_READY_TIMEOUT_SECONDS) -> None:
        """Wait until the VM is running and SSH is reachable.

        Since the Debian cloud images lack cloud-init, this method:
        1. Waits for the VM to reach Running state
        2. Waits for the Incus agent inside the VM (incus exec works)
        3. Installs openssh-server if not present
        4. Injects the ephemeral SSH public key into root's authorized_keys
        5. Waits for SSH to accept connections with the key
        """
        deadline = time.monotonic() + timeout

        # Phase 1: Wait for VM to be Running
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["incus", "list", self.name, "--format=json"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                vms = json.loads(result.stdout)
                if vms and vms[0].get("status") == "Running":
                    break
            time.sleep(SSH_POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError(f"VM '{self.name}' did not start within {timeout}s")

        # Phase 2: Wait for Incus agent (incus exec) to work
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["incus", "exec", self.name, "--", "echo", "agent-ready"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and "agent-ready" in result.stdout:
                break
            time.sleep(SSH_POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError(
                f"Incus agent not ready on VM '{self.name}' within {timeout}s"
            )

        # Phase 3: Wait for IP address
        self.ip_address = self.get_ip()
        if not self.ip_address:
            while time.monotonic() < deadline:
                self.ip_address = self.get_ip()
                if self.ip_address:
                    break
                time.sleep(SSH_POLL_INTERVAL_SECONDS)
            else:
                raise TimeoutError(
                    f"VM '{self.name}' did not get an IP within {timeout}s"
                )

        # Phase 4: Install openssh-server and inject SSH key via incus exec
        self._setup_ssh()

        # Phase 5: Wait for SSH to accept connections
        while time.monotonic() < deadline:
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "PubkeyAuthentication=yes",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "BatchMode=yes",
                    "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-i", str(self.ssh_key.private_key_path),
                    f"root@{self.ip_address}",
                    "echo ready",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and "ready" in result.stdout:
                return
            time.sleep(SSH_POLL_INTERVAL_SECONDS)

        raise TimeoutError(
            f"SSH not reachable on VM '{self.name}' ({self.ip_address}) "
            f"within {timeout}s"
        )

    def _setup_ssh(self) -> None:
        """Install openssh-server and inject the ephemeral SSH key."""
        # Install openssh-server if not already present
        result = self.exec("dpkg -s openssh-server 2>/dev/null", timeout=10)
        if result.returncode != 0:
            self.exec(
                "apt-get update -qq && apt-get install -y -qq openssh-server",
                timeout=120,
            )

        # Ensure root login is permitted (Debian defaults may vary)
        self.exec(
            "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' "
            "/etc/ssh/sshd_config"
        )

        # Inject SSH public key
        self.exec("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        self.exec(
            f"echo '{self.ssh_key.public_key}' >> /root/.ssh/authorized_keys "
            "&& chmod 600 /root/.ssh/authorized_keys"
        )

        # Restart sshd to pick up config changes
        self.exec("systemctl restart ssh || systemctl restart sshd")

    def get_ip(self) -> str:
        """Get the VM's IPv4 address from Incus."""
        result = subprocess.run(
            ["incus", "list", self.name, "--format=json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""

        vms = json.loads(result.stdout)
        if not vms:
            return ""

        network = vms[0].get("state", {}).get("network", {})
        for iface_name, iface in network.items():
            if iface_name == "lo":
                continue
            for addr in iface.get("addresses", []):
                if addr.get("family") == "inet" and addr.get("scope") == "global":
                    return addr["address"]
        return ""

    def exec(self, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a command inside the VM via incus exec (no SSH).

        The command is passed to sh -c so pipes and shell syntax work.
        """
        return subprocess.run(
            ["incus", "exec", self.name, "--", "sh", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def ssh(self, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command on the VM via SSH using the ephemeral key."""
        return subprocess.run(
            [
                "ssh",
                "-p", str(self.ssh_port),
                "-o", "PubkeyAuthentication=yes",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                "-i", str(self.ssh_key.private_key_path),
                f"root@{self.ip_address}",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def put_file(self, src: str | Path, dst: str) -> None:
        """Push a local file into the VM."""
        subprocess.run(
            ["incus", "file", "push", str(src), f"{self.name}{dst}"],
            capture_output=True,
            text=True,
            check=True,
        )

    def get_file(self, src: str, dst: str | Path) -> None:
        """Pull a file from the VM to local path."""
        subprocess.run(
            ["incus", "file", "pull", f"{self.name}{src}", str(dst)],
            capture_output=True,
            text=True,
            check=True,
        )
