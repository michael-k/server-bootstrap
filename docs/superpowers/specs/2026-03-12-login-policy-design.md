# Login Policy Hardening Design

## Goal

Harden system-wide login defaults to enforce idle timeouts, restrict root console access to known TTYs, and tighten console login parameters.

## When Active

Always. Like sudo hardening, login policy hardening has no feature flag — these are baseline security defaults that apply to every bootstrapped server.

## Approach

Extend the existing `users` role. This role already manages sudo hardening and pam_wheel, so it owns access control policy. No new role.

Three changes:
1. Deploy a hardened `/etc/login.defs` with tighter defaults
2. Deploy `/etc/securetty` to restrict root console login to known TTYs
3. Deploy a `/etc/profile.d/` drop-in to enforce shell idle timeout via TMOUT

## Shell Idle Timeout (TMOUT)

A new template `shell-timeout.sh.j2` deploys to `/etc/profile.d/shell-timeout.sh`. Every login shell sources files in `/etc/profile.d/`, making this the standard mechanism for system-wide shell variables.

```bash
# Shell idle timeout — deployed by Ansible
# Logs out idle interactive shells after the configured timeout.
# Only affects shells waiting at the prompt, not running commands.
TMOUT={{ login_policy_tmout }}
readonly TMOUT
export TMOUT
```

`readonly` prevents users from unsetting the timeout. This is safe because TMOUT only fires when the shell is waiting for input at the prompt — long-running commands, log tailing, and other active work are unaffected.

The default is 600 seconds (10 minutes), matching the effective SSH ClientAlive timeout (300s interval x 2 missed keepalives). SSH sessions get both protections: TMOUT exits the shell gracefully, while ClientAlive drops the TCP connection as a backstop. KVM console sessions — which SSH ClientAlive cannot reach — get TMOUT as their only idle protection.

## Console TTY Restrictions (`/etc/securetty`)

A new template `securetty.j2` deploys to `/etc/securetty`.

```
# Console TTY restrictions — deployed by Ansible
# Only listed TTYs allow root login. pam_securetty.so enforces this.

# Virtual console TTYs (KVM/physical console)
tty1
tty2
tty3
tty4
tty5
tty6

# Serial console TTYs (some hosters use serial instead of VT)
ttyS0
ttyS1
```

### Why This File Matters

Debian 11+ does not ship `/etc/securetty`. When the file is absent, `pam_securetty.so` allows root login on all TTYs. Creating this file activates the restriction.

`pam_securetty.so` must be enabled in `/etc/pam.d/login` for the file to have any effect. Debian ships this line by default, but the deployment task should verify it is present (see Task Order below).

### What It Restricts

`pam_securetty` only restricts root. The manual user can log in on any TTY and then `su` to root (they are in the `wheel` group). The listed TTYs cover both standard virtual consoles (`tty1`-`tty6`, used by most KVM providers) and serial consoles (`ttyS0`-`ttyS1`, used by some hosters). This can be narrowed later once the hoster's console type is known.

## System Login Defaults (`/etc/login.defs`)

A new template `login.defs.j2` deploys to `/etc/login.defs`. The template is based on Debian's default `login.defs` (from the `shadow` package) with four settings changed. All other settings — including UID/GID ranges, encryption method, and system defaults — are preserved verbatim from the Debian original.

### Changed Settings

| Setting | Debian Default | New Value | Purpose |
|---------|---------------|-----------|---------|
| `UMASK` | `022` (implicit) | `027` | New files get `rw-r-----` (640), new directories get `rwxr-x---` (750) — other users cannot read them |
| `LOGIN_RETRIES` | `5` | `3` | Matches SSH `MaxAuthTries 3` |
| `LOGIN_TIMEOUT` | `60` | `30` | Matches SSH `LoginGraceTime 30s` |
| `LOG_OK_LOGINS` | `no` | `yes` | Log successful console logins to syslog |

### Preserved Settings

All other settings remain at Debian defaults:

- `MAIL_DIR /var/mail`
- `LOG_UNKFAIL_ENAB no`
- `HUSHLOGIN_FILE .hushlogin`
- `ENV_SUPATH PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
- `ENV_PATH PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games`
- `TTYPERM 0600`
- `ERASECHAR 0177`
- `KILLCHAR 025`
- `HOME_MODE 0700`
- `PASS_MAX_DAYS 99999`
- `PASS_MIN_DAYS 0`
- `PASS_WARN_AGE 7`
- `UID_MIN 1000`, `UID_MAX 60000`
- `GID_MIN 1000`, `GID_MAX 60000`
- `SUB_UID_MIN 100000`, `SUB_UID_MAX 600100000`, `SUB_UID_COUNT 65536`
- `SUB_GID_MIN 100000`, `SUB_GID_MAX 600100000`, `SUB_GID_COUNT 65536`
- `CHFN_RESTRICT rwh`
- `ENCRYPT_METHOD YESCRYPT`
- `DEFAULT_HOME yes`
- `NONEXISTENT /nonexistent`
- `USERGROUPS_ENAB yes`

Password aging settings (`PASS_MAX_DAYS`, `PASS_MIN_DAYS`, `PASS_WARN_AGE`) are preserved at Debian defaults. Password authentication is disabled — these settings are inert.

### Logging

`LOG_OK_LOGINS yes` causes the `login` program to log successful console logins via syslog's AUTH facility — the same facility sudo uses. journald captures these entries automatically.

## Configurable Defaults

Added to `roles/users/defaults/main.yml`:

```yaml
# Login policy hardening
login_policy_tmout: 600
login_policy_umask: "027"
login_policy_retries: 3
login_policy_timeout: 30
```

The security directives in securetty (TTY list) and login.defs (LOG_OK_LOGINS, ENCRYPT_METHOD, etc.) are hardcoded in templates — they should not be optional.

## Files Changed

```
roles/users/
├── defaults/main.yml              # Add login policy variables
├── tasks/main.yml                 # Add 4 new tasks
└── templates/
    ├── login.defs.j2              # New: system login defaults
    ├── securetty.j2               # New: console TTY restrictions
    └── shell-timeout.sh.j2        # New: TMOUT drop-in

docs/
└── login-policy.md                # New: admin instructions and log queries

tests/
├── verify_bootstrap.yml           # Add login policy verification checks
└── property/
    └── test_login_policy_properties.py  # New: property tests
```

## Task Order

New tasks are appended after the sudo hardening tasks in `roles/users/tasks/main.yml`:

1. **Deploy login.defs** — `ansible.builtin.template`, `dest: /etc/login.defs`, `owner: root`, `group: root`, `mode: 0644`
2. **Ensure pam_securetty is enabled** — `ansible.builtin.lineinfile`, verify `/etc/pam.d/login` contains `auth requisite pam_securetty.so` (Debian ships this with `requisite` — immediate rejection if TTY not listed)
3. **Deploy securetty** — `ansible.builtin.template`, `dest: /etc/securetty`, `owner: root`, `group: root`, `mode: 0600`
4. **Deploy shell timeout** — `ansible.builtin.template`, `dest: /etc/profile.d/shell-timeout.sh`, `owner: root`, `group: root`, `mode: 0644`

All tasks use `tags: [users]`, matching the existing convention in the role.

No handlers needed. These files take effect on the next login session.

## Verification

New checks in `verify_bootstrap.yml`:

1. `/etc/login.defs` contains `UMASK` with value `027`
2. `/etc/login.defs` contains `LOGIN_RETRIES` with value `3`
3. `/etc/login.defs` contains `LOGIN_TIMEOUT` with value `30`
4. `/etc/login.defs` contains `LOG_OK_LOGINS` with value `yes`
5. `/etc/securetty` exists and contains `tty1`
6. `/etc/profile.d/shell-timeout.sh` exists and contains `TMOUT`

## Property Tests

New file `tests/property/test_login_policy_properties.py`:

- login.defs template contains hardened UMASK, LOGIN_RETRIES, LOGIN_TIMEOUT, LOG_OK_LOGINS
- login.defs template preserves critical Debian defaults (UID_MIN, UID_MAX, ENCRYPT_METHOD YESCRYPT, HOME_MODE 0700)
- securetty template lists tty1 through tty6
- securetty template lists ttyS0 and ttyS1
- securetty template does not contain `pts/` (no pseudo-terminal access for root)
- shell-timeout template sets TMOUT using the login_policy_tmout variable
- shell-timeout template marks TMOUT as readonly
- shell-timeout template exports TMOUT
- Defaults define all login policy variables

## Querying Console Login Logs

Console logins log to syslog's AUTH facility via the `login` program, which journald captures. The client documentation (`docs/login-policy.md`) should include these common queries:

```bash
# All console login activity
journalctl SYSLOG_IDENTIFIER=login

# Successful console logins today
journalctl SYSLOG_IDENTIFIER=login --since today

# Follow console login logs in real time
journalctl SYSLOG_IDENTIFIER=login -f
```

## Interaction with Existing Roles

- **ssh_hardening**: Complementary. SSH ClientAlive provides connection-level idle timeout; TMOUT provides shell-level idle timeout. `LOGIN_RETRIES` and `LOGIN_TIMEOUT` mirror SSH's `MaxAuthTries` and `LoginGraceTime` for console logins. No conflicts.
- **sudo hardening**: No interaction. Sudo hardening manages sudoers; login policy manages login.defs and shell environment.
- **fail2ban**: No interaction. Fail2ban monitors SSH logs, not console logins.
- **firewall**: No interaction.
- **emergency_access**: The emergency script runs as root on a console TTY. The securetty file permits root login on `tty1`-`tty6` and `ttyS0`-`ttyS1`, so emergency console access is preserved.
