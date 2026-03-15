# Bootstrap Contract

This document defines the machine state that `server-bootstrap` produces. Purpose-specific repos (headscale, nameserver, mailserver, etc.) build on top of this state.

## Repository Layout

```
config/
  server-bootstrap/    # This repo — base hardening
  headscale/           # Purpose-specific: headscale server
  nameserver/          # Purpose-specific: nameserver
  mailserver/          # Purpose-specific: mailserver
```

Purpose repos are **not coupled** to bootstrap. They don't import, depend on, or reference bootstrap roles. The contract is the **machine state** described below, not the code.

## Guaranteed Machine State

After a successful bootstrap run, a coding agent working on a purpose-specific repo can assume everything in this section.

### Operating System

- Debian 13 (trixie) or newer, fully patched (`dist-upgrade` applied)
- Hostname configured (if `system_hostname` was set)

### Time Synchronization

- NTP-based time sync is active via either chrony or systemd-timesyncd (configurable, default: chrony)
- NTP servers: Debian pool (`0-3.debian.pool.ntp.org`)

### Logging

- Persistent journald logging
- Retention: 1 month, max 500 MB disk usage
- Purpose repos should log to journald (via systemd units) — logs will be retained and queryable with `journalctl`

### User Accounts

| Property | Manual user | Automation user |
|---|---|---|
| Default name | `admin` | `ansible` |
| UID | 1000 | 1999 |
| Shell | `/bin/bash` | `/bin/bash` |
| SSH auth | Key-only | Key-only |
| Password login | Has password (for sudo) | Disabled (`!`) |
| Sudo | Password-required (`ALL=(ALL:ALL) ALL`) | Passwordless (`NOPASSWD:ALL`) |

- Root SSH access is disabled
- `su` is restricted to `wheel` group members (manual user is in `wheel`)

### Login Hardening

- Shell idle timeout: 600 seconds (via `/etc/profile.d/shell-timeout.sh`)
- Console root login restricted to `tty1`–`tty6` only (via `securetty` + `pam_securetty`)
- Hardened `login.defs` (umask `027`, 3 retries, 30s timeout)
- PAM faillock: account locked after 5 failures within 15 minutes, unlocked after 10 minutes
- PAM resource limits: nproc 1024 (root 2048), nofile 4096 (root 8192)
- Sudo hardening: environment sanitization, logging, 5-minute credential timeout

### SSH

- Key-only authentication (passwords disabled)
- Port: 22 (configurable via `ssh_port`)
- Max 3 auth attempts, 30s login grace time
- Client alive interval: 300s, max 2 missed keepalives
- X11/TCP/agent forwarding: disabled
- `AllowGroups ssh-users` — only members of the `ssh-users` group can log in
- Strong algorithms only:
  - **KEX**: curve25519-sha256, diffie-hellman-group16-sha512, diffie-hellman-group18-sha512
  - **Ciphers**: chacha20-poly1305, aes256-gcm, aes128-gcm
  - **MACs**: hmac-sha2-512-etm, hmac-sha2-256-etm
- When Tailscale is enabled: SSH listens only on the Tailscale interface IPs

### Firewall (nftables)

- **Default-deny** inbound policy (input chain policy: `drop`)
- **Default-deny** forwarding (forward chain policy: `drop`)
- **Allow-all** outbound (output chain policy: `accept`)
- Loopback, established/related, and ICMP/ICMPv6 traffic allowed
- SSH access is governed by one of three modes:
  - **Tailscale-restricted** (default when Tailscale enabled): SSH accepted only on `tailscale0` interface, plus UDP 41641 (WireGuard) open on all interfaces
  - **Port knocking** (default when Tailscale disabled): SSH hidden behind a 3-port TCP knock sequence (default: 7000, 8500, 9100) with configurable timeouts
  - **Open** (when both Tailscale and port knocking disabled): SSH accepted on all interfaces

**Extension point:** `/etc/nftables.d/*.nft` — bootstrap creates this directory and includes it at the end of `/etc/nftables.conf`. Purpose repos drop rule files here. Files **must** use `add rule` syntax since the base table already exists. Example:

```
# /etc/nftables.d/webserver.nft
add rule inet filter input tcp dport { 80, 443 } accept
```

Bootstrap owns `/etc/nftables.conf` and regenerates it on re-run, but the `include` directive and `/etc/nftables.d/` directory are preserved. Drop-in files survive bootstrap re-runs. After deploying a drop-in file, reload nftables to apply:

```yaml
- name: Reload nftables to apply firewall rules
  ansible.builtin.systemd:
    name: nftables
    state: reloaded
```

### Intrusion Prevention (fail2ban)

- Monitors SSH via systemd journal
- Bans IPs after 5 failures within 10 minutes (10-minute ban)
- Uses `nftables-multiport` ban action
- Purpose repos can add additional fail2ban jails by dropping config into `/etc/fail2ban/jail.d/`

### Filesystem Hardening

- `/tmp` — mounted with `noexec,nosuid,nodev` (drop-in override or bind-mount, depending on base system)
- `/dev/shm` — mounted with `noexec,nosuid,nodev` (drop-in override)
- `/var/tmp` — bind-mounted to `/tmp` (inherits restrictions)

Purpose repos should be aware that executables cannot run from `/tmp`, `/var/tmp`, or `/dev/shm`.

### Tailscale VPN (if enabled)

- Connected to a Headscale control server
- `tailscale0` interface up with assigned IPv4 and IPv6 addresses
- WireGuard port (UDP 41641) open in firewall
- DNS acceptance disabled, routes accepted
- Emergency SSH restore script at `/root/emergency-ssh-access.sh`

### Swap (if configured)

- **Zram** (if enabled): compressed RAM swap using LZ4, priority 100
- **Disk swap** (if configured): swapfile at `/swapfile`, priority 10 (used after zram is exhausted)

## Ansible Connection Model

Purpose-specific playbooks connect as the automation user with `become: true`:

```yaml
- name: Configure headscale server
  hosts: headscale
  become: true
  remote_user: ansible  # or whatever deploy_user_name was set to

  roles:
    - role: headscale
```

- The automation user has passwordless sudo — no `become_password` needed
- SSH key auth only — the playbook runner must have the matching private key
- If Tailscale is enabled, the target is only reachable via its Tailscale IP

## Bootstrap-Owned Files

Bootstrap overwrites these on every run. Purpose repos must not modify them.

- `/etc/nftables.conf`
- `/etc/ssh/sshd_config`
- `/etc/fail2ban/jail.local`
- `/etc/systemd/journald.conf`
- `/etc/hostname`
- `/etc/chrony/chrony.conf` (or `/etc/systemd/timesyncd.conf`)
- `/etc/login.defs`
- `/etc/securetty`
- `/etc/sudoers.d/00-sudo-security`
- `/etc/sudoers.d/<manual_user_name>`
- `/etc/sudoers.d/<deploy_user_name>`
- `/etc/profile.d/shell-timeout.sh`
- `/etc/security/faillock.conf`
- `/etc/security/limits.d/50-hardening.conf`
- `/usr/share/pam-configs/faillock`
- `/etc/systemd/system/tmp.mount` (or `tmp.mount.d/hardening.conf`)
- `/etc/systemd/system/dev-shm.mount.d/hardening.conf`
- `/etc/systemd/system/var-tmp.mount`
- `/root/emergency-ssh-access.sh` (if Tailscale enabled)

## What Purpose Repos Must Not Do

- Modify any file in the bootstrap-owned list above
- Import, reference, or depend on bootstrap roles or role internals
- Duplicate bootstrap functionality (don't re-configure SSH, don't re-create users)
- Depend on bootstrap-internal details (nftables chain names, systemd unit internals)

## Extension Points

These are the designated places where purpose repos integrate with the bootstrapped system:

| Extension point | How to use | Survives bootstrap re-run? |
|---|---|---|
| `ssh-users` group | Add users to this group to grant SSH access | Yes |
| `/etc/nftables.d/*.nft` | Drop firewall rules using `add rule` syntax, then reload nftables | Yes |
| `/etc/fail2ban/jail.d/*.conf` | Drop jail configs for service-specific intrusion prevention | Yes |
| systemd units | Create new services — they log to journald automatically | Yes |
| apt packages | Install any package (bootstrap runs `dist-upgrade` on re-run, which may update them) | Yes |

Beyond the extension points above, purpose repos can also:
- Use the automation user (`ansible` by default) for Ansible-driven configuration
- Assume the Tailscale interface exists if `tailscale_enabled` was set

## Workflows

### New VPS

1. Provision VPS (Debian 13+, root access)
2. Run bootstrap → hardened base
3. Run purpose-specific playbook → server ready

### Applying Bootstrap Updates

1. Make changes in `server-bootstrap`
2. Re-run bootstrap against affected hosts (idempotent)
3. Purpose-specific config is unaffected

