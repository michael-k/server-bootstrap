# Tailscale Integration Test Design

## Goal

Verify that the bootstrap playbook's Tailscale integration works end-to-end: SSH restricted to the tailnet, port knocking unable to bypass that restriction, and the emergency script able to toggle public access without breaking tailnet access.

## Overview

The test spins up three Incus VMs on the shared bridge network:

| VM | Role | Setup |
|---|---|---|
| VM1 — headscale | Control server | Download latest headscale binary, run with minimal config on port 8080 (HTTP, no TLS) |
| VM2 — peer | Tailnet peer | Raw-install tailscale via apt, join VM1's tailnet with pre-auth key 1 |
| VM3 — target | Bootstrap target | Full `run_bootstrap_playbook()` with Tailscale enabled, pointing at VM1, using pre-auth key 2 |

After setup, VM2 and VM3 are peers on the same tailnet. The host machine sits outside the tailnet and can only reach VMs via their bridge IPs.

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
2. **Download binary** — fetch it onto the VM, make it executable.
3. **Write config** — minimal YAML: listen on `0.0.0.0:8080`, in-memory SQLite, IP prefixes for the tailnet (e.g., `100.64.0.0/10`).
4. **Start server** — run headscale in the background (e.g., `systemd-run` or `nohup`). Wait for it to respond.
5. **Create user** — `headscale users create testuser`.

### Pre-Auth Key Generation

`headscale preauthkeys create --user testuser` — parses the key from command output and returns it as a string. Called twice during fixture setup to produce two distinct keys.

### Version Policy

Always use the latest stable release. No pinned version — this test validates a real-world setup and should surface upstream compatibility issues early.

## Tailscale Peer Setup (VM2)

Raw install via `incus exec`, no Ansible:

1. Install tailscale from the official apt repository.
2. `tailscale up --login-server=http://<vm1_ip>:8080 --authkey=<key1>`.
3. Wait for `tailscale status` to show "Running".

After the bootstrap playbook finishes on VM3, push VM3's ephemeral SSH private key onto VM2 so it can authenticate as the manual user.

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

After the playbook completes:
- SSH listens only on the Tailscale IP.
- The firewall allows SSH only on the Tailscale interface.
- Port knocking rules are active.
- The emergency script is deployed at `/root/emergency-ssh-access.sh`.

## Fixture — `tailscale_env`

Session-scoped pytest fixture. Returns a dataclass with all three VMs, their bridge IPs, Tailscale IPs, and SSH keys.

### Setup Order

1. Create all three VMs (`IncusVM.create` + `wait_ready`).
2. Run `HeadscaleServer.setup()` on VM1; generate two pre-auth keys.
3. Raw-install tailscale on VM2; join the tailnet with key 1.
4. Run the bootstrap playbook on VM3 with key 2.
5. Push VM3's SSH private key onto VM2.
6. Wait for VM2 and VM3 to see each other as peers (`tailscale status`).

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

Five ordered test methods:

### 1. `test_ssh_closed_from_host`

SSH from the host to VM3's bridge IP with `ConnectTimeout=5`. Assert the connection fails (refused or timed out). This proves the firewall restricts SSH to the Tailscale interface.

### 2. `test_port_knocking_does_not_bypass_tailscale`

From the host, knock the correct sequence (7000, 8500, 9100) against VM3's bridge IP. Then attempt SSH again with `ConnectTimeout=5`. Assert it still fails. This catches any regression where port knocking rules accidentally open SSH to the public despite Tailscale restriction.

### 3. `test_ssh_open_from_tailnet_peer`

From VM2 (via `incus exec`), SSH to VM3's Tailscale IP as the manual user using the pushed private key. Assert the connection succeeds.

### 4. `test_emergency_script_unrestricts_ssh`

Run `/root/emergency-ssh-access.sh` on VM3 via `incus exec`. Then:
- SSH from the host to VM3's bridge IP succeeds.
- SSH from VM2 to VM3's Tailscale IP still succeeds (emergency script must not break tailnet access).

### 5. `test_emergency_script_restore`

Run `/root/emergency-ssh-access.sh --restore` on VM3 via `incus exec`. SSH from the host to VM3's bridge IP fails again. The system is back to its hardened state.

## Timeout Strategy

| Operation | Timeout |
|---|---|
| VM creation + wait_ready | 120s (existing) |
| Headscale download + setup | 120s |
| Tailscale join (per VM) | 60s |
| SSH "should succeed" assertions | 10s ConnectTimeout |
| SSH "should fail" assertions | 5s ConnectTimeout |

## Files Changed

| File | Change |
|---|---|
| `tests/infra/headscale.py` | New — `HeadscaleServer` class |
| `tests/integration/test_tailscale_integration.py` | New — fixture + 5 tests |
| `tests/infra/__init__.py` | Export `HeadscaleServer` if needed |
