# PAM Hardening

The bootstrap playbook hardens PAM with account lockout protection and system-wide resource limits.

## What It Does

### Account Lockout (pam_faillock)

Locks accounts after repeated failed authentication attempts. Protects against brute-force attacks on console login, SSH, and sudo.

- Locks after 5 failed attempts within a 15-minute window
- Unlocks automatically after 10 minutes
- Root accounts are locked too (timed, never permanent)
- Lockout state clears on reboot

Deployed to: `/etc/security/faillock.conf`
PAM profile: `/usr/share/pam-configs/faillock`

### Resource Limits (pam_limits)

Enforces system-wide resource limits to prevent fork bombs, file descriptor exhaustion, and credential leaks via core dumps. These limits apply to PAM-authenticated sessions (login shells, SSH). Systemd services set their own limits independently.

| Limit | User | Root | Purpose |
|-------|------|------|---------|
| `nproc` | 1024 | 2048 | Max processes (prevents fork bombs) |
| `nofile` | 4096 | 8192 | Max open file descriptors |
| `core` | 0 | 0 | Disables core dumps (prevents credential leaks) |

Deployed to: `/etc/security/limits.d/50-hardening.conf`

## Managing Locked Accounts

```bash
# View failed login attempts for a user
faillock --user <username>

# Manually unlock a locked account
faillock --user <username> --reset

# View all users with failed attempts
faillock
```

A locked account unlocks automatically after 10 minutes. Rebooting also clears all lockout state.

## Checking Resource Limits

```bash
# Check current resource limits for your session
ulimit -a

# Check a specific user's limits
su - <username> -c 'ulimit -a'
```

## Configuration

Override these variables in your inventory or playbook:

```yaml
# Account lockout
pam_faillock_deny: 5             # Failed attempts before lockout
pam_faillock_unlock_time: 600    # Seconds until automatic unlock
pam_faillock_fail_interval: 900  # Sliding window for counting failures

# Resource limits
pam_limits_nproc: 1024           # Max processes per user
pam_limits_nproc_root: 2048      # Max processes for root
pam_limits_nofile: 4096          # Max open file descriptors per user
pam_limits_nofile_root: 8192     # Max open file descriptors for root
```

Core dumps (`core 0`) cannot be configured — this is security policy.
