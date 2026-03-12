# Sudo Hardening Design

## Goal

Harden sudo configuration and restrict `su` access to close privilege escalation gaps in the VPS bootstrap playbook.

## When Active

Always. Unlike port knocking or Tailscale, sudo hardening has no feature flag — these are baseline security defaults that apply to every bootstrapped server.

## Approach

Extend the existing `users` role. This role already manages sudoers files for both users, so it owns privilege escalation policy. No new role.

Three changes:
1. Deploy a shared sudoers security defaults file
2. Create a `wheel` group and restrict `su` to its members
3. Add the manual user to the `wheel` group

## Sudo Security Defaults

A new template `00-sudo-security.j2` deploys to `/etc/sudoers.d/00-sudo-security`. The `00-` prefix ensures it loads before the per-user files (sudoers.d reads in lexical order), so these defaults govern all sudo usage.

```
# Sudo security defaults — deployed by Ansible

# Environment sanitization — prevent LD_PRELOAD, PATH injection
Defaults    env_reset
Defaults    env_clean
Defaults    secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Credential caching
Defaults    timestamp_timeout={{ sudo_timestamp_timeout }}

# Logging — enhance syslog entries (sudo logs to AUTH facility by default,
# which journald captures automatically)
Defaults    log_year
Defaults    log_host

# Security restrictions
Defaults    use_pty
Defaults    requiretty
Defaults:{{ ansible_user_name }}    !requiretty
```

### Directives Explained

| Directive | Purpose |
|-----------|---------|
| `env_reset` | Start with a clean environment, strip inherited variables |
| `env_clean` | Remove dangerous environment variables (LD_PRELOAD, etc.) |
| `secure_path` | Hardcode PATH to system directories — prevents trojaned binaries |
| `timestamp_timeout` | Re-prompt for password after configured timeout (default: 5 minutes) |
| `log_year` | Include the year in syslog timestamps |
| `log_host` | Include the hostname in syslog entries |
| `use_pty` | Allocate a PTY for sudo commands — prevents I/O log bypass |
| `requiretty` | Require a real terminal to use sudo |
| `!requiretty` for ansible user | Exempt Ansible from the TTY requirement — Ansible's `become: true` does not allocate a TTY |

### Why `requiretty` with an Ansible Exemption

`requiretty` blocks sudo invocations from cron jobs, scripts, or exploits that lack a terminal. This hardens interactive sudo for the manual user. Ansible needs the exemption because it runs commands over SSH without allocating a PTY by default. The exemption applies only to the ansible user, which already has `NOPASSWD:ALL` — the TTY requirement would add no meaningful security for that account anyway.

## `su` Restriction via pam_wheel

Restrict the `su` command to members of the `wheel` group by enabling `pam_wheel.so` in `/etc/pam.d/su`.

Debian ships this line commented out by default:

```
# auth       required   pam_wheel.so
```

The task uses `ansible.builtin.lineinfile` to ensure the uncommented form is present:

```
auth       required   pam_wheel.so
```

### Group Membership

- The `wheel` group is created if it does not exist.
- The manual user is added to `wheel` — can use `su`.
- The ansible user is **not** added to `wheel` — it has no password (`!`), so `su` with password auth would fail regardless. The explicit exclusion from `wheel` makes the restriction visible.

## Configurable Defaults

Added to `roles/users/defaults/main.yml`:

```yaml
# Sudo hardening
sudo_timestamp_timeout: 5
```

Only the timeout is configurable. The security directives (`env_reset`, `env_clean`, `secure_path`, `use_pty`, `requiretty`, `log_year`, `log_host`) are hardcoded in the template — they should not be optional. Sudo logs to syslog (AUTH facility) by default, which journald captures automatically — no separate log file needed.

## Per-User Sudoers Files

The existing per-user files are unchanged:

- `/etc/sudoers.d/{{ manual_user_name }}`: `admin ALL=(ALL:ALL) ALL`
- `/etc/sudoers.d/{{ ansible_user_name }}`: `ansible ALL=(ALL:ALL) NOPASSWD:ALL`

These define **who** gets sudo and **how** (password vs passwordless). The `00-sudo-security` file defines **how sudo behaves** (environment, logging, timeouts). The separation keeps each file focused.

## Files Changed

```
roles/users/
├── defaults/main.yml              # Add sudo_timestamp_timeout
├── tasks/main.yml                 # Add wheel group, sudo security, pam_wheel tasks
└── templates/
    └── 00-sudo-security.j2       # New: sudo security defaults template

docs/
└── sudo-hardening.md              # New: admin instructions and log queries

tests/
├── verify_bootstrap.yml           # Add sudo hardening verification checks
└── property/
    └── test_sudo_hardening_properties.py  # New: property tests
```

## Task Order

New tasks are appended after the existing ansible user tasks in `roles/users/tasks/main.yml`:

1. **Create wheel group** — `ansible.builtin.group`, `state: present`
2. **Add manual user to wheel group** — `ansible.builtin.user` with `groups: wheel`, `append: true`
3. **Deploy sudo security defaults** — `ansible.builtin.template`, `dest: /etc/sudoers.d/00-sudo-security`, `validate: visudo -cf %s`, `mode: 0440`
4. **Enable pam_wheel.so in /etc/pam.d/su** — `ansible.builtin.lineinfile` with `regexp: '^\s*#?\s*auth\s+required\s+pam_wheel\.so'` to replace the commented line in-place rather than appending a duplicate

## Verification

New conditional checks in `verify_bootstrap.yml`:

1. `/etc/sudoers.d/00-sudo-security` exists
2. The file contains `env_reset`, `secure_path`, `use_pty`
3. `wheel` group exists
4. Manual user is a member of `wheel`
5. `/etc/pam.d/su` contains uncommented `pam_wheel.so` line

## Property Tests

New file `tests/property/test_sudo_hardening_properties.py`:

- Template contains `env_reset` and `env_clean`
- Template contains `secure_path` with standard system directories
- Template contains `timestamp_timeout` referencing `sudo_timestamp_timeout` variable
- Template contains `use_pty`
- Template contains `requiretty`
- Template contains `!requiretty` exemption for ansible user (references `ansible_user_name` variable)
- Defaults file defines `sudo_timestamp_timeout`
- Tasks file creates wheel group
- Tasks file enables `pam_wheel.so`
- Tasks file deploys `00-sudo-security` with `visudo` validation

## Querying Sudo Logs

Sudo logs to syslog's AUTH facility, which journald captures. The client documentation (`docs/sudo-hardening.md`) should include these common queries:

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

## Interaction with Existing Roles

- **fail2ban**: No interaction. Fail2ban monitors SSH logs, not sudo.
- **ssh_hardening**: No interaction. SSH hardening manages sshd_config; sudo hardening manages sudoers.
- **firewall**: No interaction.
- **emergency_access**: The emergency script runs as root (`/root/emergency-ssh-access.sh`). Since it is executed directly by root (not via sudo), the `requiretty` directive does not affect it.
