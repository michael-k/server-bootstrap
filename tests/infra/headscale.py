"""Headscale server lifecycle management for integration testing."""

import json
import os
import time
from dataclasses import dataclass, field

from tests.infra.vm import IncusVM

# Headscale GitHub API endpoint for latest release
_GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/juanfont/headscale/releases/latest"
)

_HEADSCALE_CONFIG = """\
server_url: http://{server_ip}:8080
listen_addr: 0.0.0.0:8080
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
database:
  type: sqlite
"""


@dataclass
class HeadscaleServer:
    """Manages a headscale control server on an Incus VM."""

    vm: IncusVM
    _user_created: bool = field(default=False, repr=False)

    def setup(self, timeout: int = 120) -> None:
        """Download, configure, and start headscale.

        1. Fetch the latest release URL from GitHub API.
        2. Download the linux_amd64 binary onto the VM.
        3. Write a minimal config file.
        4. Start headscale via systemd-run.
        5. Wait for the CLI to respond.
        6. Create the test user.
        """
        deadline = time.monotonic() + timeout

        # 1. Fetch latest release download URL
        # Note: unauthenticated GitHub API allows 60 requests/hour per IP.
        # Set GITHUB_TOKEN env var on the host if rate-limited in CI.
        self.vm.exec("apt-get update -qq && apt-get install -y -qq curl jq", timeout=60)
        auth_header = ""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            auth_header = f"-H 'Authorization: Bearer {token}'"
        result = self.vm.exec(
            f"curl -sL {auth_header} {_GITHUB_RELEASES_URL}"
            " | jq -r '.assets[] | select(.name | test(\"linux_amd64\")) | .browser_download_url'"
            " | head -1",
            timeout=30,
        )
        download_url = result.stdout.strip()
        if not download_url or download_url == "null":
            raise RuntimeError(
                f"Failed to find headscale download URL.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

        # 2. Download binary
        self.vm.exec(
            f"curl -sL -o /usr/local/bin/headscale '{download_url}'"
            " && chmod +x /usr/local/bin/headscale",
            timeout=60,
        )

        # 3. Write config
        self.vm.exec("mkdir -p /etc/headscale")
        config = _HEADSCALE_CONFIG.format(server_ip=self.vm.ip_address)
        # Use heredoc via sh to avoid quoting issues
        self.vm.exec(
            f"cat > /etc/headscale/config.yaml << 'HEADSCALE_EOF'\n{config}HEADSCALE_EOF"
        )

        # 4. Start headscale
        self.vm.exec(
            "systemd-run --unit=headscale --property=Restart=no "
            "headscale serve"
        )

        # 5. Wait for CLI to respond
        while time.monotonic() < deadline:
            result = self.vm.exec("headscale users list -o json 2>/dev/null")
            if result.returncode == 0:
                break
            time.sleep(2)
        else:
            status = self.vm.exec("systemctl status headscale")
            journal = self.vm.exec("journalctl -u headscale --no-pager -n 30")
            raise TimeoutError(
                f"Headscale did not become ready within {timeout}s.\n"
                f"status: {status.stdout}\n"
                f"journal: {journal.stdout}"
            )

        # 6. Create test user
        result = self.vm.exec("headscale users create testuser")
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create headscale user.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        self._user_created = True

    def create_preauth_key(self) -> str:
        """Generate a pre-authentication key for the test user.

        Returns the key string (e.g., 'tskey-auth-...').
        """
        if not self._user_created:
            raise RuntimeError("Call setup() before creating pre-auth keys")

        result = self.vm.exec(
            "headscale preauthkeys create --user testuser -o json"
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create pre-auth key.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        data = json.loads(result.stdout)
        # The JSON output format may vary by version; try common paths
        if isinstance(data, dict):
            key = data.get("key", data.get("preAuthKey", {}).get("key", ""))
        else:
            key = ""
        if not key:
            raise RuntimeError(
                f"Could not parse pre-auth key from output.\n"
                f"stdout: {result.stdout}"
            )
        return key

    def teardown(self) -> None:
        """Stop the headscale server."""
        self.vm.exec("systemctl stop headscale 2>/dev/null")
