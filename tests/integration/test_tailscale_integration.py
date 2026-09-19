"""
End-to-end integration tests for Tailscale + firewall + emergency access.

Three Incus VMs: a headscale control server, a tailnet peer, and the
bootstrap target. Verifies SSH is restricted to the tailnet, port
knocking cannot bypass it, and the emergency script toggles access.

This is the only suite in the project that runs an enabled Tailscale
bootstrap against a real host. Each test cites the requirement it
exercises; the tests covering SSH binding, firewall isolation and the
emergency script belong to specs that are not yet written and carry no
citation yet.
"""

import dataclasses
import os
import subprocess
import time
from pathlib import Path

import pytest

from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from incus.fixtures import incus_available, print_debug_info
from incus.headscale import HeadscaleServer
from incus.vm import IncusVM
from tests.integration.helpers import run_bootstrap_playbook

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Timeout for "should fail" SSH attempts — keep short
_SSH_FAIL_TIMEOUT = 5
# Timeout for "should succeed" SSH attempts
_SSH_OK_TIMEOUT = 10
# Timeout for tailscale peer connectivity
_PEER_TIMEOUT = 60

_MANUAL_USER = "testuser"
_PEER_KEY_PATH = "/root/.ssh/vm3_key"


@dataclasses.dataclass
class TailscaleEnv:
    """All three VMs and metadata needed by the test class."""

    headscale: IncusVM
    peer: IncusVM
    target: IncusVM
    target_ts_ipv4: str
    target_ts_ipv6: str
    manual_user: str


def _ssh_from_host(
    ip: str,
    port: int,
    user: str,
    key_path: str | Path,
    timeout: int = _SSH_FAIL_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Attempt SSH from the host machine to an IP. Returns CompletedProcess."""
    return subprocess.run(
        [
            "ssh",
            "-p", str(port),
            "-o", "PubkeyAuthentication=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", f"ConnectTimeout={timeout}",
            "-i", str(key_path),
            f"{user}@{ip}",
            "echo SUCCESS",
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
        check=False,
    )


def _ssh_from_peer(
    peer_vm: IncusVM,
    target_ip: str,
    port: int,
    user: str,
    timeout: int = _SSH_OK_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run SSH from the peer VM to the target via incus exec."""
    cmd = (
        f"ssh -i {_PEER_KEY_PATH}"
        f" -o PubkeyAuthentication=yes"
        f" -o StrictHostKeyChecking=no"
        f" -o UserKnownHostsFile=/dev/null"
        f" -o BatchMode=yes"
        f" -o IdentitiesOnly=yes"
        f" -o ConnectTimeout={timeout}"
        f" -p {port}"
        f" {user}@{target_ip}"
        f" echo SUCCESS"
    )
    return peer_vm.exec(cmd, timeout=timeout + 10)


def _install_tailscale_on_peer(vm: IncusVM, login_server: str, authkey: str) -> None:
    """Raw-install tailscale on a VM and join the tailnet."""
    # Use Tailscale's official install script — handles all Debian versions
    vm.exec("apt-get update -qq && apt-get install -y -qq curl", timeout=60)
    result = vm.exec("curl -fsSL https://tailscale.com/install.sh | sh", timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"Tailscale install failed on peer.\n"
            f"stdout: {result.stdout[-1000:]}\nstderr: {result.stderr[-500:]}"
        )

    # Join the tailnet
    result = vm.exec(
        f"tailscale up --login-server={login_server} --authkey={authkey}"
        " --accept-routes --accept-dns=false",
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"tailscale up failed on peer.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    # Wait for tailscale to have an IP (confirms it joined the tailnet)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = vm.exec("tailscale ip -4 2>/dev/null")
        if result.returncode == 0 and result.stdout.strip():
            return
        time.sleep(2)

    raise TimeoutError(
        f"Tailscale on peer did not get an IP.\n"
        f"tailscale status: {vm.exec('tailscale status').stdout}"
    )


def _wait_for_peer(
    peer_vm: IncusVM, target_ip: str, timeout: int = _PEER_TIMEOUT,
) -> None:
    """Wait until the peer can ping the target via the tailnet."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = peer_vm.exec(f"tailscale ping --timeout=5s {target_ip}")
        if result.returncode == 0 and "pong" in result.stdout:
            return
        time.sleep(2)

    raise TimeoutError(
        f"Peer cannot reach {target_ip} via tailnet within {timeout}s.\n"
        f"peer tailscale status: {peer_vm.exec('tailscale status').stdout}\n"
    )


def _collect_diagnostics(
    headscale_vm: IncusVM, peer_vm: IncusVM, target_vm: IncusVM,
) -> str:
    """Collect diagnostic info from all VMs for debugging failures."""
    lines = ["\n=== DIAGNOSTICS ==="]

    for label, vm, cmds in [
        ("headscale", headscale_vm, [
            "headscale nodes list",
            "systemctl status headscale",
            "journalctl -u headscale --no-pager -n 20",
        ]),
        ("peer", peer_vm, [
            "tailscale status",
            "systemctl status tailscaled",
        ]),
        ("target", target_vm, [
            "tailscale status",
            "systemctl status tailscaled",
            "nft list ruleset",
            "ss -tlnp",
            "cat /etc/ssh/sshd_config | grep -E 'ListenAddress|Port'",
        ]),
    ]:
        lines.append(f"\n--- {label} ({vm.name}) ---")
        for cmd in cmds:
            result = vm.exec(cmd, timeout=30)
            lines.append(f"$ {cmd}")
            lines.append(result.stdout[:500] if result.stdout else "(empty stdout)")
            if result.stderr:
                lines.append(f"  stderr: {result.stderr[:200]}")

    return "\n".join(lines)


@pytest.fixture(scope="session")
def tailscale_env(request):
    """Three-VM environment: headscale server, tailnet peer, bootstrap target.

    Session-scoped — all tests in TestTailscaleIntegration share this fixture.

    TS-1: the only place this project runs the role with enrolment enabled.
    TS-6: the target registers with the headscale server on VM1.
    TS-7: it registers with a pre-auth key that server issued.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    # Step 1: Create all three VMs
    headscale_vm = IncusVM(image=image, name_hint="headscale", auto_launch=True)
    peer_vm = IncusVM(image=image, name_hint="ts-peer", auto_launch=True)
    target_vm = IncusVM(image=image, name_hint="ts-target", auto_launch=True)
    all_vms = [headscale_vm, peer_vm, target_vm]

    def _cleanup(preserve: bool = False) -> None:
        if preserve:
            for vm in all_vms:
                print_debug_info(vm)
        else:
            for vm in all_vms:
                vm.destroy()

    headscale = HeadscaleServer(vm=headscale_vm)

    try:
        # Wait for all VMs to be ready
        for vm in all_vms:
            vm.wait_ready()

        # Step 2: Set up headscale and generate pre-auth keys
        headscale.setup()
        key1 = headscale.create_preauth_key()
        key2 = headscale.create_preauth_key()

        # Step 3: Install tailscale on peer and join tailnet
        login_server = f"http://{headscale_vm.ip_address}:8080"
        _install_tailscale_on_peer(peer_vm, login_server, key1)

        # Step 4: Run bootstrap playbook on target with tailscale enabled
        result = run_bootstrap_playbook(
            target_vm,
            extra_vars={
                "tailscale_enabled": True,
                "tailscale_control_server": login_server,
                "tailscale_pre_auth_key": key2,
                "port_knocking_sequence": [7000, 8500, 9100],
            },
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Bootstrap playbook failed on target.\n"
                f"stdout: {result.stdout[-3000:]}\n"
                f"stderr: {result.stderr[-1000:]}"
            )

        # Step 5: Discover target's Tailscale IPs
        ts_ipv4 = target_vm.exec("tailscale ip -4").stdout.strip()
        ts_ipv6 = target_vm.exec("tailscale ip -6").stdout.strip()
        if not ts_ipv4 or not ts_ipv6:
            raise RuntimeError(
                f"Failed to discover Tailscale IPs on target.\n"
                f"ipv4: {ts_ipv4!r}, ipv6: {ts_ipv6!r}\n"
                f"tailscale status: {target_vm.exec('tailscale status').stdout}"
            )

        # Step 6: Push target's SSH private key onto peer
        peer_vm.exec("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        peer_vm.put_file(
            target_vm.private_key_path, _PEER_KEY_PATH
        )
        peer_vm.exec(f"chmod 600 {_PEER_KEY_PATH}")

        # Step 7 & 8: Wait for peer connectivity (IPv4 and IPv6)
        _wait_for_peer(peer_vm, ts_ipv4)
        _wait_for_peer(peer_vm, ts_ipv6)

    except Exception:
        diag = _collect_diagnostics(headscale_vm, peer_vm, target_vm)
        print(diag)
        _cleanup(preserve=bool(os.environ.get("KEEP_VM_ON_FAIL")))
        raise

    env = TailscaleEnv(
        headscale=headscale_vm,
        peer=peer_vm,
        target=target_vm,
        target_ts_ipv4=ts_ipv4,
        target_ts_ipv6=ts_ipv6,
        manual_user=_MANUAL_USER,
    )

    yield env

    # Teardown
    try:
        headscale.teardown()
    finally:
        keep = bool(os.environ.get("KEEP_VM_ON_FAIL"))
        failed = getattr(request.session, "testsfailed", 0)
        errored = getattr(request.session, "testserrors", 0)
        _cleanup(preserve=keep and (failed + errored) > 0)


class TestTailscaleIntegration:
    """End-to-end tests for Tailscale + firewall + emergency access.

    Tests run in definition order. Each test builds on the state left
    by the previous one (especially tests 4 and 5 which toggle the
    emergency script).
    """

    def test_ssh_closed_from_host(self, tailscale_env: TailscaleEnv) -> None:
        """SSH from host to target's bridge IP must fail (firewall blocks it)."""
        env = tailscale_env
        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=env.target.private_key_path,
            timeout=_SSH_FAIL_TIMEOUT,
        )
        assert result.returncode != 0, (
            "SSH from host to target bridge IP succeeded — "
            "firewall is not restricting SSH to Tailscale interface"
        )
        assert "SUCCESS" not in result.stdout

    def test_port_knocking_does_not_bypass_tailscale(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Port knocking must NOT open SSH when Tailscale restricts it."""
        env = tailscale_env
        env.target.knock(ports=[7000, 8500, 9100])

        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=env.target.private_key_path,
            timeout=_SSH_FAIL_TIMEOUT,
        )
        assert result.returncode != 0, (
            "SSH from host succeeded after port knocking — "
            "knock sequence bypasses Tailscale restriction"
        )
        assert "SUCCESS" not in result.stdout

    def test_ssh_closed_without_firewall(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """SSH from host must fail even with the firewall disabled.

        sshd should be bound only to Tailscale IPs, so disabling
        nftables must not expose SSH on the bridge interface. This
        is defense-in-depth: both sshd binding and firewall restrict
        access independently.
        """
        env = tailscale_env

        # Disable the firewall
        env.target.exec("systemctl stop nftables")
        env.target.exec("nft flush ruleset")
        try:
            result = _ssh_from_host(
                ip=env.target.ip_address,
                port=env.target.ssh_port,
                user=env.manual_user,
                key_path=env.target.private_key_path,
                timeout=_SSH_FAIL_TIMEOUT,
            )
            assert result.returncode != 0, (
                "SSH from host succeeded with firewall disabled — "
                "sshd is not bound exclusively to Tailscale interface"
            )
            assert "SUCCESS" not in result.stdout
        finally:
            # Re-enable the firewall
            env.target.exec("systemctl start nftables")

    def test_ssh_open_from_tailnet_peer(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """SSH from the tailnet peer to the target must succeed (IPv4 and IPv6).

        TS-17, TS-18: reaching the target on both published addresses is the
        only evidence in this project that each fact held a real address.
        TS-21: the only check that traffic actually crosses the tailnet,
        rather than being answered locally by the target's own kernel.
        TS-22: the target has already been narrowed to those addresses by the
        time this runs, so a verification that ran too late shows up here.
        """
        env = tailscale_env

        # IPv4
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv4, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer to target via Tailscale IPv4 failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # IPv6
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv6, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer to target via Tailscale IPv6 failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

    def test_emergency_script_unrestricts_ssh(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Emergency script opens SSH to all interfaces without breaking tailnet."""
        env = tailscale_env

        result = env.target.exec("/root/emergency-ssh-access.sh")
        assert result.returncode == 0, (
            f"Emergency script failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # SSH from host must now succeed
        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=env.target.private_key_path,
            timeout=_SSH_OK_TIMEOUT,
        )
        assert result.returncode == 0, (
            f"SSH from host failed after emergency unrestrict.\n"
            f"stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # SSH via tailnet IPv4 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv4, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv4 broke after emergency unrestrict.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # SSH via tailnet IPv6 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv6, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv6 broke after emergency unrestrict.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

    def test_emergency_script_restore(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Emergency --restore re-restricts SSH; tailnet access still works."""
        env = tailscale_env

        result = env.target.exec("/root/emergency-ssh-access.sh --restore")
        assert result.returncode == 0, (
            f"Emergency restore failed.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # SSH from host must fail again
        result = _ssh_from_host(
            ip=env.target.ip_address,
            port=env.target.ssh_port,
            user=env.manual_user,
            key_path=env.target.private_key_path,
            timeout=_SSH_FAIL_TIMEOUT,
        )
        assert result.returncode != 0, (
            "SSH from host still works after emergency restore — "
            "script did not re-restrict access"
        )
        assert "SUCCESS" not in result.stdout

        # SSH via tailnet IPv4 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv4, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv4 broke after emergency restore.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

        # SSH via tailnet IPv6 must still work
        result = _ssh_from_peer(
            env.peer, env.target_ts_ipv6, env.target.ssh_port, env.manual_user,
        )
        assert result.returncode == 0, (
            f"SSH from peer via Tailscale IPv6 broke after emergency restore.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout

    def test_tailscale_services_running(
        self, tailscale_env: TailscaleEnv,
    ) -> None:
        """Tailscaled service is enabled and running on the target.

        TS-12, TS-13: the only checks of the real unit state rather than of
        the task that is supposed to produce it.
        """
        env = tailscale_env

        result = env.target.exec("systemctl is-active tailscaled")
        assert result.returncode == 0, (
            f"tailscaled not active.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "active" in result.stdout

        result = env.target.exec("systemctl is-enabled tailscaled")
        assert result.returncode == 0, (
            f"tailscaled not enabled.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
