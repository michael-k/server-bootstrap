"""Incus VM lifecycle management for integration testing."""


import contextlib
import json
import secrets
import subprocess
import time
from collections.abc import Generator
from dataclasses import InitVar, dataclass, field
from pathlib import Path

from incus.constants import (
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_POLL_INTERVAL_SECONDS,
    VM_NAME_PREFIX,
    VM_READY_TIMEOUT_SECONDS,
)
from incus.ssh import SSHKeyPair


@dataclass
class IncusVM:
    """Manages a single Incus VM for testing."""

    image: str = ""
    name: str = ""
    ssh_key: InitVar[SSHKeyPair | None] = None
    ip_address: str = ""
    ssh_port: int = 22
    ssh_user: str = "root"
    knock_sequence: list[int] | None = None
    name_hint: InitVar[str] = ""
    auto_launch: InitVar[bool] = False
    _ssh_key: SSHKeyPair = field(init=False, repr=False, compare=False)
    _last_knock_time: float = field(default=0.0, repr=False, compare=False)

    def __post_init__(
        self,
        ssh_key: SSHKeyPair | None,
        name_hint: str,
        auto_launch: bool,
    ) -> None:
        if not self.name:
            suffix = secrets.token_hex(4)
            hint = f"{name_hint}-" if name_hint else ""
            self.name = f"{VM_NAME_PREFIX}{hint}{suffix}"
        self._ssh_key = ssh_key if ssh_key is not None else SSHKeyPair.create(self.name)
        if auto_launch:
            self.launch()

    @property
    def private_key_path(self) -> Path:
        """Path to the ephemeral SSH private key."""
        return self._ssh_key.private_key_path

    @property
    def public_key(self) -> str:
        """The SSH public key string."""
        return self._ssh_key.public_key

    def launch(self) -> None:
        """Launch the VM in Incus.

        The Debian cloud images don't include cloud-init, so SSH setup
        is handled in wait_ready() via incus exec after the VM boots.
        """
        if not self.image:
            raise ValueError("image is required to launch a VM")
        subprocess.run(
            ["incus", "launch", self.image, self.name, "--vm"],
            capture_output=True,
            text=True,
            check=True,
        )

    def destroy(self) -> None:
        """Force-delete the VM and clean up SSH keys."""
        import sys

        result = subprocess.run(
            ["incus", "delete", self.name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"Warning: failed to destroy VM '{self.name}': "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
        self._ssh_key.cleanup()

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
                    "-i", str(self.private_key_path),
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
            f"echo '{self.public_key}' >> /root/.ssh/authorized_keys "
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
        """Run a command on the VM via SSH using the ephemeral key.

        If a knock_sequence is configured, automatically port-knocks when the
        last knock was more than 20 seconds ago.
        """
        if self.knock_sequence is not None:
            elapsed = time.monotonic() - self._last_knock_time
            if elapsed > 20:
                self.knock()
        return subprocess.run(
            [
                "ssh",
                "-p", str(self.ssh_port),
                "-o", "PubkeyAuthentication=yes",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                "-i", str(self.private_key_path),
                f"{self.ssh_user}@{self.ip_address}",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def knock(self, ports: list[int] | None = None, delay: float = 0.3) -> None:
        """Perform a port knock sequence to unlock SSH access.

        Sends a TCP SYN to each port in sequence with a short delay between.
        Uses *ports* if given, otherwise falls back to ``knock_sequence``,
        otherwise the firewall role default ``[7000, 8500, 9100]``.
        """
        import socket

        if ports is None:
            ports = self.knock_sequence if self.knock_sequence is not None else [7000, 8500, 9100]

        for port in ports:
            with (
                socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
                contextlib.suppress(ConnectionRefusedError, TimeoutError, OSError),
            ):
                sock.settimeout(1)
                sock.connect((self.ip_address, port))
            time.sleep(delay)

        self._last_knock_time = time.monotonic()

    @contextlib.contextmanager
    def background_service(
        self, start_cmd: str, stop_cmd: str, settle: float = 1,
    ) -> Generator[None]:
        """Run a background service on the VM, ensuring cleanup on exit."""
        self.exec(start_cmd)
        time.sleep(settle)
        try:
            yield
        finally:
            self.exec(stop_cmd)

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
