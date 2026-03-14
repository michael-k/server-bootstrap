# Tailscale Integration Test Design

## Goal

Verify that the bootstrap playbook's Tailscale integration works end-to-end: SSH restricted to the tailnet by firewall rules, port knocking unable to bypass that restriction, and the emergency script able to toggle public access without breaking tailnet access.

## Overview

The test spins up three Incus VMs on the shared bridge network:

| VM | Role | Setup |
|---|---|---|
| VM1 — headscale | Control server | Download latest headscale binary, run with minimal config on port 8080 (HTTP, no TLS) |
| VM2 — peer | Tailnet peer | Raw-install tailscale via apt, join VM1's tailnet with pre-auth key 1 |
| VM3 — target | Bootstrap target | Full `run_bootstrap_playbook()` with Tailscale enabled, pointing at VM1, using pre-auth key 2 |

After setup, VM2 and VM3 are peers on the same tailnet. The host machine sits outside the tailnet and can only reach VMs via their bridge IPs.

## Known Issue: sshd ListenAddress Ordering

The `ssh_hardening` role renders `sshd_config` before the `tailscale` role sets `tailscale_ipv4`. Because `tailscale_ipv4` is undefined at template time, the Jinja2 conditional falls through and sshd ends up with `ListenAddress 0.0.0.0` — listening on all interfaces. SSH restriction is enforced **solely by nftables firewall rules**, not by sshd bind address.

This means:
- The emergency script's unrestrict mode is a no-op on sshd_config (the sed pattern for `ListenAddress <tailscale_ip>` does not match), but it correctly opens the firewall.
- The emergency script's `--restore` mode deletes all `ListenAddress` lines and writes `ListenAddress <tailscale_ip>`, actually *fixing* the sshd binding. After a restore cycle, the system is more secure than the initial bootstrap state.

This is a pre-existing playbook bug, not something this test addresses. The tests must reflect actual post-bootstrap behavior.

## Headscale Helper — `tests/infra/headscale.py`

A `HeadscaleServer` class that encapsulates headscale lifecycle on a VM.

### Interface

```python
class HeadscaleServer:
    def __init__(self, vm: IncusVM): ...
    def setup(self) -> None
    def create_preauth_key(self) -> str
    def teardown(self) -> None
```

### Setup Flow

1. **Fetch latest release** — query the GitHub API (`/repos/juanfont/headscale/releases/latest`) for the download URL of the `linux_amd64` binary.
2. **Download binary** — fetch it onto the VM via `vm.exec()`, make it executable.
3. **Write config** — minimal YAML deployed via `vm.exec()`:
   - `server_url: http://<vm1_bridge_ip>:8080` (required — clients use this to reach the server)
   - `listen_addr: 0.0.0.0:8080`
   - `database.type: sqlite` (ephemeral, default path)
   - `prefixes.v4: 100.64.0.0/10`
   - `prefixes.v6: fd7a:115c:a1e0::/48`
4. **Start server** — `systemd-run` or `nohup`. Poll `headscale` CLI (e.g., `headscale users list`) until it responds, with a 30s timeout.
5. **Create user** — `headscale users create testuser`.

### Pre-Auth Key Generation

`headscale preauthkeys create --user testuser` — parses the key from stdout and returns it. Called twice during fixture setup.

### Version Policy

Always use the latest stable release. No pinned version — this test validates a real-world setup and should surface upstream compatibility issues early. If headscale makes breaking config changes, the test fails and we update the config to match — that is the intended behavior.

## Tailscale Peer Setup (VM2)

Raw install via `incus exec`, no Ansible:

1. Add the official Tailscale apt repository and GPG key.
2. `apt-get install -y tailscale`.
3. `tailscale up --login-server=http://<vm1_ip>:8080 --authkey=<key1>`.
4. Wait for `tailscale status --json` to show `BackendState: Running`, with a 60s timeout.

After the bootstrap playbook finishes on VM3, push VM3's ephemeral SSH private key onto VM2 at a known path (e.g., `/root/.ssh/vm3_key`) with permissions `0600`, so VM2 can authenticate as the manual user.

## Bootstrap Target (VM3)

Run `run_bootstrap_playbook()` with these extra vars:

```python
{
    "tailscale_enabled": True,
    "tailscale_control_server": "http://<vm1_ip>:8080",
    "tailscale_pre_auth_key": "<key2>",
    "port_knocking_sequence": [7000, 8500, 9100],
}
```

The default `tailscale_interface: "tailscale0"` applies — this is the standard interface name when Tailscale connects to headscale.

After the playbook completes:
- sshd listens on `0.0.0.0` (see known issue above), but the nftables firewall allows SSH only on the `tailscale0` interface.
- Port knocking rules are active.
- The emergency script is deployed at `/root/emergency-ssh-access.sh`.

### Discovering VM3's Tailscale IP

After bootstrap, run `tailscale ip -4` on VM3 via `vm.exec()` to get its Tailscale IPv4 address (e.g., `100.64.0.x`). Store this in the fixture's return value for use in test assertions.

## Fixture — `tailscale_env`

Session-scoped pytest fixture. Returns a dataclass:

```python
@dataclasses.dataclass
class TailscaleEnv:
    headscale: IncusVM
    peer: IncusVM          # VM2
    target: IncusVM        # VM3
    target_ts_ip: str      # VM3's Tailscale IPv4
    peer_ssh_key: str      # path to private key on VM2
    manual_user: str       # manual user name on VM3
```

### Setup Order

1. Create all three VMs (`IncusVM.create` + `wait_ready`).
2. Run `HeadscaleServer.setup()` on VM1; generate two pre-auth keys.
3. Raw-install tailscale on VM2; join the tailnet with key 1.
4. Run the bootstrap playbook on VM3 with key 2.
5. Discover VM3's Tailscale IP via `vm.exec("tailscale ip -4")`.
6. Push VM3's SSH private key onto VM2 at `/root/.ssh/vm3_key`.
7. Verify peer connectivity: run `tailscale ping <vm3_ts_ip>` from VM2 via `vm.exec()`, retry for up to 60s. A successful ping confirms the peers can route traffic through the tailnet (direct or via DERP relay).

### Teardown

Destroy all three VMs. If `KEEP_VM_ON_FAIL` is set and a test failed, preserve them and print SSH/cleanup commands for all three.

### Failure Diagnostics

On fixture setup failure, collect and print:
- `tailscale status` from VM2 and VM3
- `headscale nodes list` from VM1
- `systemctl status tailscaled` from VM2 and VM3
- `nft list ruleset` from VM3
- `ss -tlnp` from VM3

## Test Class — `TestTailscaleIntegration`

Five ordered test methods. Pytest executes methods in definition order within a class, which is sufficient here. No `pytest-ordering` dependency needed.

### 1. `test_ssh_closed_from_host`

From the host, attempt SSH to VM3's bridge IP as the manual user with `ConnectTimeout=5`. Assert the connection fails at the TCP level (refused or timed out). Uses the ephemeral private key that the playbook deployed — the failure must be network-level (firewall), not authentication-level.

### 2. `test_port_knocking_does_not_bypass_tailscale`

From the host, knock the correct sequence (7000, 8500, 9100) against VM3's bridge IP using `vm.knock()`. Then attempt SSH again as the manual user with `ConnectTimeout=5`. Assert it still fails. Catches regressions where port knocking rules accidentally open SSH to the public despite Tailscale restriction.

### 3. `test_ssh_open_from_tailnet_peer`

From VM2, run via `incus exec`:
```
ssh -i /root/.ssh/vm3_key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 -o BatchMode=yes \
    <manual_user>@<vm3_tailscale_ip> echo ok
```
Assert exit code 0. The default Debian SSH client supports the hardened algorithms (curve25519, chacha20-poly1305).

### 4. `test_emergency_script_unrestricts_ssh`

Run `/root/emergency-ssh-access.sh` on VM3 via `incus exec`. Then:
- SSH from the host to VM3's bridge IP as the manual user succeeds.
- SSH from VM2 to VM3's Tailscale IP as the manual user still succeeds.

### 5. `test_emergency_script_restore`

Run `/root/emergency-ssh-access.sh --restore` on VM3 via `incus exec`. SSH from the host to VM3's bridge IP fails again. After this restore, sshd is bound to the Tailscale IP (the script fixes the ListenAddress), so the system is in a tighter state than post-bootstrap.

## Timeout Strategy

| Operation | Timeout |
|---|---|
| VM creation + wait_ready | 120s (existing) |
| Headscale download + setup | 120s |
| Tailscale join (per VM) | 60s |
| Tailscale peer ping | 60s |
| SSH "should succeed" assertions | 10s ConnectTimeout |
| SSH "should fail" assertions | 5s ConnectTimeout |

## Files Changed

| File | Change |
|---|---|
| `tests/infra/headscale.py` | New — `HeadscaleServer` class |
| `tests/integration/test_tailscale_integration.py` | New — fixture + 5 tests |
| `tests/infra/__init__.py` | Export `HeadscaleServer` if needed |
