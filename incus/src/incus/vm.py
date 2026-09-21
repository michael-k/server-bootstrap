"""Incus VM lifecycle management for integration testing.

``IncusVM`` is the single object a caller holds for one machine, and it owes
that caller four separate things:

INCUS-2: ``launch()`` puts the machine on the Incus daemon.
INCUS-12: ``wait_ready()`` brings it to the point where it accepts SSH.
INCUS-13: ``destroy()`` force-deletes it.
INCUS-14: ``__post_init__`` generates the name and the access key when the
caller supplies neither.

INCUS-3: two command paths, deliberately asymmetric.  ``ssh()`` goes through
the machine's own sshd as ``ssh_user`` on ``ssh_port``; ``exec()`` bypasses
SSH entirely through the Incus agent as root, so it keeps working on a
machine whose SSH the bootstrap has just shut.

INCUS-4 and INCUS-15: ``put_file()`` pushes a file in and ``get_file()``
pulls one out, both through Incus rather than scp, for the same reason.

INCUS-5: ``knock()``, and the automatic re-knock in ``ssh()`` and in
``wait_ready()``'s readiness poll.

INCUS-6: ``background_service()`` stops what it started, including on an
exception.

INCUS-8: ``destroy()`` removes the ephemeral key along with the machine.
This class is NOT a context manager -- no ``__enter__``, no ``__exit__``, no
``__del__`` -- so a caller that raises before ``destroy()`` leaves the
private key behind.  The fixtures are what close that today.

INCUS-1 is violated at ``knock()``'s fallback sequence and at the three
``apt-get``/``dpkg`` calls, which assume Debian -- one of them behind a guard
on whether the command is needed, not on what it assumes.  Recorded in
specs/incus-tooling, not fixed here.
"""


import contextlib
import json
import secrets
import subprocess
import time
from collections.abc import Generator
from dataclasses import InitVar, dataclass, field
from pathlib import Path

from incus.constants import (
    BASE_IMAGE_PREFIX,
    DEFAULT_DEBIAN_VERSION,
    IMAGE_PREFIX,
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_POLL_INTERVAL_SECONDS,
    VM_NAME_PREFIX,
    VM_READY_TIMEOUT_SECONDS,
)
from incus.ssh import SSHKeyPair


def ensure_base_image(version: str = DEFAULT_DEBIAN_VERSION) -> str:
    """Ensure a pre-baked base image exists for the given Debian version.

    The base image contains openssh-server, curl, and PermitRootLogin enabled.
    It is rebuilt automatically when the upstream images:debian/{version}
    fingerprint changes.

    Returns the image alias (e.g. ``bootstrap/internal-base-13``).
    """
    alias = f"{BASE_IMAGE_PREFIX}{version}"
    upstream_image = f"{IMAGE_PREFIX}{version}"

    # Get upstream fingerprint (image info doesn't support --format=json
    # for remote images, so we parse the text output)
    result = subprocess.run(
        ["incus", "image", "info", upstream_image, "--vm"],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.lower().startswith("fingerprint:"):
            upstream_fp = line.split(":", 1)[1].strip()
            break
    else:
        raise RuntimeError(
            f"Could not parse fingerprint from 'incus image info {upstream_image}'"
        )

    # Check if base image already exists
    result = subprocess.run(
        ["incus", "image", "list", alias, "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    existing = json.loads(result.stdout)
    if existing:
        stored_fp = existing[0].get("properties", {}).get("user.upstream_fingerprint")
        if stored_fp == upstream_fp:
            return alias
        # Stale — delete old image
        subprocess.run(
            ["incus", "image", "delete", existing[0]["fingerprint"]],
            capture_output=True,
            text=True,
            check=True,
        )

    # Build new base image
    vm_name = f"{VM_NAME_PREFIX}base-build-{secrets.token_hex(4)}"
    subprocess.run(
        ["incus", "launch", upstream_image, vm_name, "--vm"],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        # Wait for agent
        for _ in range(60):
            result = subprocess.run(
                ["incus", "exec", vm_name, "--", "echo", "agent-ready"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and "agent-ready" in result.stdout:
                break
            time.sleep(SSH_POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError(f"Agent not ready on '{vm_name}' within 120s")

        # Install packages
        subprocess.run(
            [
                "incus", "exec", vm_name, "--", "sh", "-c",
                "apt-get update -qq && apt-get install -y -qq openssh-server curl",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )

        # Enable PermitRootLogin
        subprocess.run(
            [
                "incus", "exec", vm_name, "--", "sh", "-c",
                "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Stop VM before publishing
        subprocess.run(
            ["incus", "stop", vm_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )

        # Publish with upstream fingerprint property
        subprocess.run(
            [
                "incus", "publish", vm_name,
                f"--alias={alias}",
                f"user.upstream_fingerprint={upstream_fp}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        subprocess.run(
            ["incus", "delete", vm_name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )

    return alias


@dataclass
class IncusVM:
    """Manages a single Incus VM for testing."""

    image: str = f"{IMAGE_PREFIX}{DEFAULT_DEBIAN_VERSION}"
    name: str = ""
    ssh_key: InitVar[SSHKeyPair | None] = None
    ip_address: str = ""
    ssh_port: int = 22
    ssh_user: str = "root"
    # Consumes KNOCK-10: the ports a knock-gated VM requires. Left None for a
    # VM that is not behind a knock sequence; knock() then falls back to a
    # copy of the bootstrap's default, since this helper has no inventory to
    # read the real value from.
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

        If the image is a raw upstream Debian image (``images:debian/…``),
        transparently swaps to a pre-baked base image with openssh-server
        and curl already installed.
        """
        if not self.image:
            raise ValueError("image is required to launch a VM")
        image = self.image
        if image.startswith(IMAGE_PREFIX):
            version = image[len(IMAGE_PREFIX):]
            image = ensure_base_image(version)
        subprocess.run(
            ["incus", "launch", image, self.name, "--vm"],
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

        # Phase 5: Port knock (if configured) then wait for SSH to accept
        # connections. Consumes KNOCK-7: the 20-second threshold is chosen to
        # re-knock with margin inside the 30-second pass window, so a poll
        # loop never attempts SSH on an expired knock.
        while time.monotonic() < deadline:
            if self.knock_sequence is not None and (time.monotonic() - self._last_knock_time) > 20:
                self.knock()
            result = subprocess.run(
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
        """Install openssh-server and inject the ephemeral SSH key for ssh_user."""
        # Install openssh-server if not already present
        result = self.exec("dpkg -s openssh-server 2>/dev/null", timeout=10)
        if result.returncode != 0:
            self.exec(
                "apt-get update -qq && apt-get install -y -qq openssh-server",
                timeout=120,
            )

        if self.ssh_user == "root":
            self.exec(
                "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' "
                "/etc/ssh/sshd_config"
            )

        # Resolve home directory and inject key
        home = self.exec(f"eval echo ~{self.ssh_user}").stdout.strip()
        ssh_dir = f"{home}/.ssh"
        self.exec(f"mkdir -p {ssh_dir} && chmod 700 {ssh_dir}")
        self.exec(
            f"echo '{self.public_key}' >> {ssh_dir}/authorized_keys "
            f"&& chmod 600 {ssh_dir}/authorized_keys"
        )
        self.exec(f"chown -R {self.ssh_user}:{self.ssh_user} {ssh_dir}")

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
        last knock was more than 20 seconds ago — consuming KNOCK-7, whose
        pass window is 30 seconds, with 10 seconds of margin.
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
        otherwise a copy of KNOCK-10's default ``[7000, 8500, 9100]``. The
        copy is a copy, not a read: this helper drives a VM from outside
        Ansible and has no inventory to take the configured value from, so a
        deployment that changes the sequence must change it here too.

        Order matters (KNOCK-5, KNOCK-6) and the delay must keep consecutive
        knocks inside KNOCK-7's 5-second stage window.
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
