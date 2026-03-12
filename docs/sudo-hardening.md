# Sudo Hardening

The bootstrap playbook applies security defaults to sudo and restricts `su` to members of the `wheel` group.

## What Gets Configured

### Sudo Security Defaults

Deployed to `/etc/sudoers.d/00-sudo-security`:

- **Environment sanitization** — `env_reset` and `env_clean` strip dangerous variables (LD_PRELOAD, PATH injection). `secure_path` hardcodes PATH to system directories.
- **Credential caching** — `timestamp_timeout=5` re-prompts for the password after 5 minutes of inactivity. Only affects the manual user (the ansible user has passwordless sudo).
- **Logging** — `log_year` and `log_host` enhance syslog entries with the year and hostname. Sudo logs to syslog's AUTH facility by default, which journald captures.
- **PTY allocation** — `use_pty` allocates a pseudo-terminal for all sudo commands.
- **TTY requirement** — `requiretty` requires a real terminal for sudo. The ansible user is exempted so that Ansible's `become: true` continues to work.

### `su` Restriction

Only members of the `wheel` group can use `su`. The manual user is added to `wheel`; the ansible user is not.

## Querying Sudo Logs

Sudo logs to journald via syslog's AUTH facility:

```bash
# All sudo activity
journalctl SYSLOG_IDENTIFIER=sudo

# Today's sudo activity
journalctl SYSLOG_IDENTIFIER=sudo --since today

# Sudo activity by a specific user
journalctl SYSLOG_IDENTIFIER=sudo _COMM=sudo | grep "admin"

# Follow sudo logs in real time
journalctl SYSLOG_IDENTIFIER=sudo -f
```

## Customizing the Timeout

Edit `sudo_timestamp_timeout` in your inventory:

```yaml
sudo_timestamp_timeout: 10  # 10 minutes instead of the default 5
```

Set to `0` to require the password on every sudo invocation.

## Verifying the Configuration

On the server:

```bash
# Check sudo security defaults
sudo cat /etc/sudoers.d/00-sudo-security

# Check wheel group membership
getent group wheel

# Check su restriction
grep pam_wheel /etc/pam.d/su
```
