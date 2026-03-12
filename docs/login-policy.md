# Login Policy Hardening

The bootstrap playbook hardens system-wide login defaults. These settings apply to all users and all login methods (SSH and console).

## What It Does

### Shell Idle Timeout (TMOUT)

Interactive shells log out after 10 minutes of idle time at the prompt. This protects unattended console sessions. TMOUT only triggers when the shell waits for input — running commands, tailing logs, or other active work is unaffected.

The timeout is read-only and cannot be disabled by users.

Deployed to: `/etc/profile.d/shell-timeout.sh`

### Console TTY Restrictions

Root can only log in on virtual console TTYs (`tty1`–`tty6`) and serial console TTYs (`ttyS0`–`ttyS1`). This covers standard KVM and serial console access provided by hosting providers.

The manual user is not restricted — they can log in on any TTY and then `su` to root.

Deployed to: `/etc/securetty`

### Hardened login.defs

Four settings are tightened from Debian defaults:

| Setting | Value | Debian Default | Purpose |
|---------|-------|---------------|---------|
| `UMASK` | `027` | `022` | New files: `rw-r-----`, directories: `rwxr-x---` |
| `LOGIN_RETRIES` | `3` | `5` | Max console login attempts (matches SSH MaxAuthTries) |
| `LOGIN_TIMEOUT` | `30` | `60` | Seconds to complete console login (matches SSH LoginGraceTime) |
| `LOG_OK_LOGINS` | `yes` | `no` | Log successful console logins |

Deployed to: `/etc/login.defs`

## Querying Console Login Logs

Console logins log to syslog's AUTH facility, which journald captures:

```bash
# All console login activity
journalctl SYSLOG_IDENTIFIER=login

# Successful console logins today
journalctl SYSLOG_IDENTIFIER=login --since today

# Follow console login logs in real time
journalctl SYSLOG_IDENTIFIER=login -f
```

## Configuration

Override these variables in your inventory or playbook:

```yaml
login_policy_tmout: 600       # Shell idle timeout in seconds
login_policy_umask: "027"     # Default file creation mask
login_policy_retries: 3       # Max console login attempts
login_policy_timeout: 30      # Console login timeout in seconds
```
