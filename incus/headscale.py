"""Headscale server lifecycle management for integration testing."""

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from incus.vm import IncusVM

_HEADSCALE_REPO = "juanfont/headscale"

_HEADSCALE_CACHE_DIR = Path("/tmp/bootstrap-test-headscale-cache")

_HEADSCALE_CONFIG = """\
server_url: http://{server_ip}:8080
listen_addr: 0.0.0.0:8080
noise:
  private_key_path: /etc/headscale/noise_private.key
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
database:
  type: sqlite3
  sqlite.path: /etc/headscale/db.sqlite
dns:
  override_local_dns: false
  base_domain: test.headscale.net
derp:
  urls:
    - https://controlplane.tailscale.com/derpmap/default
"""


def _fetch_headscale_binary() -> Path:
    """Download the latest headscale binary to a host-local cache.

    Uses `gh release download` (authenticated, no rate limits) and caches
    the binary in /tmp so repeated test runs don't re-download.

    Returns the path to the cached binary.
    """
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI (gh) is required but not found on PATH")

    # Get the latest release tag
    result = subprocess.run(
        ["gh", "release", "view", "--repo", _HEADSCALE_REPO,
         "--json", "tagName", "--jq", ".tagName"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    tag = result.stdout.strip()
    if not tag:
        raise RuntimeError("Failed to get latest headscale release tag")

    cache_dir = _HEADSCALE_CACHE_DIR / tag
    cached_binary = cache_dir / "headscale"

    if cached_binary.exists():
        return cached_binary

    # Download the binary asset (pattern: headscale_*_linux_amd64, not .deb)
    cache_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "release", "download", tag, "--repo", _HEADSCALE_REPO,
         "--pattern", "headscale_*_linux_amd64", "--output", str(cached_binary)],
        capture_output=True, text=True, check=True, timeout=120,
    )
    cached_binary.chmod(0o755)
    return cached_binary


@dataclass
class HeadscaleServer:
    """Manages a headscale control server on an Incus VM."""

    vm: IncusVM
    _user_id: int | None = field(default=None, repr=False)

    def setup(self, timeout: int = 120) -> None:
        """Download, configure, and start headscale.

        1. Fetch the latest binary (cached on host via gh CLI).
        2. Push it into the VM.
        3. Write a minimal config file.
        4. Start headscale via systemd-run.
        5. Wait for the CLI to respond.
        6. Create the test user.
        """
        deadline = time.monotonic() + timeout

        # 1. Fetch binary (downloads once, then uses cache)
        binary_path = _fetch_headscale_binary()

        # 2. Push binary into VM
        self.vm.put_file(binary_path, "/usr/local/bin/headscale")
        self.vm.exec("chmod +x /usr/local/bin/headscale")

        # 3. Write config and generate noise private key
        self.vm.exec("mkdir -p /etc/headscale")
        config = _HEADSCALE_CONFIG.format(server_ip=self.vm.ip_address)
        self.vm.exec(
            f"cat > /etc/headscale/config.yaml << 'HEADSCALE_EOF'\n{config}HEADSCALE_EOF"
        )
        self.vm.exec("headscale generate private-key > /etc/headscale/noise_private.key")

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

        # 6. Create test user and capture its numeric ID
        result = self.vm.exec("headscale users create testuser -o json")
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create headscale user.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        user_data = json.loads(result.stdout)
        if isinstance(user_data, dict):
            self._user_id = user_data.get("id")
        if self._user_id is None:
            raise RuntimeError(
                f"Could not parse user ID from output.\n"
                f"stdout: {result.stdout}"
            )

    def create_preauth_key(self) -> str:
        """Generate a pre-authentication key for the test user.

        Returns the key string (e.g., 'tskey-auth-...').
        """
        if self._user_id is None:
            raise RuntimeError("Call setup() before creating pre-auth keys")

        result = self.vm.exec(
            f"headscale preauthkeys create --user {self._user_id} -o json"
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
