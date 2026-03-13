# PAM Hardening Design

## Goal

Harden PAM with account lockout after failed login attempts (pam_faillock) and system-wide resource limits (pam_limits).

## When Active

Always. Like sudo and login policy hardening, PAM hardening has no feature flag — these are baseline security defaults that apply to every bootstrapped server.

## Approach

Extend the existing `users` role. This role already manages pam_wheel, pam_securetty, sudo hardening, and login policy, so it owns access control. No new role.

Two changes:
1. Deploy `/etc/security/faillock.conf` and enable pam_faillock in PAM
2. Deploy `/etc/security/limits.d/50-hardening.conf` for resource limits

## Account Lockout (pam_faillock)

A new template `faillock.conf.j2` deploys to `/etc/security/faillock.conf`. This file configures pam_faillock, which locks accounts after repeated failed authentication attempts.

```
# Account lockout policy — deployed by Ansible
deny = {{ pam_faillock_deny }}
unlock_time = {{ pam_faillock_unlock_time }}
fail_interval = {{ pam_faillock_fail_interval }}
even_deny_root = true
root_unlock_time = {{ pam_faillock_unlock_time }}
```

- **`deny`** — lock after this many consecutive failures (default: 5)
- **`unlock_time`** — seconds until automatic unlock (default: 600 = 10 minutes, matches TMOUT and SSH ClientAlive)
- **`fail_interval`** — sliding window in seconds for counting failures (default: 900 = 15 minutes)
- **`even_deny_root = true`** — root gets locked too; the lockout is timed, so emergency console access is never permanently blocked
- **`root_unlock_time`** — uses the same `unlock_time` value as regular users

### PAM Enablement

pam_faillock requires entries in two PAM service files: `common-auth` (for preauth/authfail) and `common-account` (to reset the failure counter on success). On Debian 12, both files are sourced by SSH, console login, and sudo, so enabling the module there covers all authentication paths.

**Important:** On Debian 12, `/etc/pam.d/common-auth` and `/etc/pam.d/common-account` are managed by `pam-auth-update`. Direct edits via `lineinfile` would be overwritten whenever a package triggers `pam-auth-update` (e.g., upgrading `libpam-modules`). The correct approach is to create a PAM profile and register it with `pam-auth-update`.

A new template `faillock-pam-config.j2` deploys to `/usr/share/pam-configs/faillock`:

```
Name: Faillock account lockout
Default: yes
Priority: 512
Auth-Type: Primary
Auth:
  required  pam_faillock.so preauth
Auth-Final:
  [default=die]  pam_faillock.so authfail
Account-Type: Additional
Account:
  required  pam_faillock.so
```

The `Priority: 512` places faillock after pam_unix (priority 256 on Debian) in the generated PAM stack. `Auth-Type: Primary` puts the `preauth` line before pam_unix; `Auth-Final` puts the `authfail` line after. `pam-auth-update` handles the `success=N` jump count arithmetic automatically.

After deploying the profile, the task runs `pam-auth-update --enable faillock` to regenerate `common-auth` and `common-account`. This is idempotent — running it again has no effect if the profile is already enabled.

### What pam_faillock Protects

fail2ban blocks IP addresses after SSH brute-force attempts. pam_faillock locks the account itself, regardless of source IP. These are complementary layers:

- An attacker rotating IPs bypasses fail2ban but still triggers pam_faillock
- A console brute-force attack (KVM/serial) is invisible to fail2ban but caught by pam_faillock
- pam_faillock fires on any PAM-authenticated service, not just SSH

### Lockout State

pam_faillock tracks failed attempts in `/run/faillock/` by default (tmpfs). The failure tally clears on reboot. This is the correct default — a reboot implies physical/console access, making persistent lockout state pointless.

## Resource Limits (pam_limits)

A new template `50-hardening.conf.j2` deploys to `/etc/security/limits.d/50-hardening.conf`.

```
# Resource limits — deployed by Ansible
# Prevents fork bombs, caps file descriptors, disables core dumps.

# Prevent fork bombs — hard limit on number of processes
*               hard    nproc           {{ pam_limits_nproc }}
root            hard    nproc           {{ pam_limits_nproc_root }}

# Cap open file descriptors — prevents fd exhaustion
*               hard    nofile          {{ pam_limits_nofile }}
root            hard    nofile          {{ pam_limits_nofile_root }}

# Disable core dumps — prevents credential leaks in dumps
*               hard    core            0
```

### Design Choices

**Drop-in file in `limits.d/`** rather than replacing `limits.conf`. This avoids clobbering package-managed defaults or operator customizations.

**`50-hardening.conf`** — numbered for predictable ordering. Package defaults load first; operator overrides at `90-*` load last.

**Hard limits only.** Soft limits can be raised by users up to the hard limit. We set the ceiling; users keep flexibility below it.

**Root gets higher nproc/nofile.** Root processes (systemd services, package management) legitimately need more headroom.

**`nproc 1024`** — generous for a VPS running mail or web services; a fork bomb spawns thousands. Regular workloads rarely exceed a few hundred processes per user.

**`nofile 4096`** — Debian's default hard limit is 1048576. A hard cap of 4096 is reasonable for a VPS and prevents fd exhaustion from runaway processes. Note: this limit only affects PAM-authenticated sessions (login shells, SSH sessions). Services managed by systemd set their own limits via `LimitNOFILE=` independently of pam_limits.

**`core 0`** — core dumps can contain passwords, keys, and other secrets from process memory. Disabling them is standard hardening. This value is hardcoded — it is security policy, not tunable.

### PAM Enablement

On Debian 12, `pam_limits.so` is already enabled in `/etc/pam.d/common-session` by default. No PAM enablement task is needed — deploying the limits file is sufficient.

## Configurable Defaults

Added to `roles/users/defaults/main.yml`:

```yaml
# PAM hardening — account lockout
pam_faillock_deny: 5
pam_faillock_unlock_time: 600
pam_faillock_fail_interval: 900

# PAM hardening — resource limits
pam_limits_nproc: 1024
pam_limits_nproc_root: 2048
pam_limits_nofile: 4096
pam_limits_nofile_root: 8192
```

`even_deny_root`, `root_unlock_time`, and `core 0` are hardcoded in templates — they are security policy, not optional.

## Files Changed

```
roles/users/
├── defaults/main.yml              # Add pam_faillock + pam_limits variables
├── tasks/main.yml                 # Add 4 new tasks
└── templates/
    ├── faillock.conf.j2           # New: account lockout config
    ├── faillock-pam-config.j2     # New: pam-auth-update profile
    └── 50-hardening.conf.j2       # New: resource limits config

docs/
└── pam-hardening.md               # New: admin instructions and commands

tests/
├── verify_bootstrap.yml           # Add pam hardening verification checks
└── property/
    └── test_pam_hardening_properties.py  # New: property tests
```

## Task Order

New tasks are appended after the login policy tasks in `roles/users/tasks/main.yml`:

1. **Deploy faillock.conf** — `ansible.builtin.template`, `dest: /etc/security/faillock.conf`, `owner: root`, `group: root`, `mode: 0644`
2. **Deploy faillock PAM profile** — `ansible.builtin.template`, `dest: /usr/share/pam-configs/faillock`, `owner: root`, `group: root`, `mode: 0644`
3. **Enable faillock in PAM** — `ansible.builtin.command: pam-auth-update --enable faillock`. The task registers its result and uses `changed_when` to detect whether the PAM stack was actually modified (pam-auth-update modifies existing files rather than creating new ones, so `creates:` is not appropriate).
4. **Deploy resource limits** — `ansible.builtin.template`, `dest: /etc/security/limits.d/50-hardening.conf`, `owner: root`, `group: root`, `mode: 0644`

All tasks use `tags: [users, pam_hardening]`.

No handlers needed. Both modules read their config files on each authentication or session event.

## Verification

New checks in `verify_bootstrap.yml`:

1. `/etc/security/faillock.conf` contains `deny` with configured value
2. `/etc/security/faillock.conf` contains `even_deny_root`
3. `/usr/share/pam-configs/faillock` exists (PAM profile deployed)
4. `/etc/pam.d/common-auth` contains `pam_faillock.so` (pam-auth-update has enabled it)
5. `/etc/security/limits.d/50-hardening.conf` exists and contains `nproc`
6. `/etc/security/limits.d/50-hardening.conf` contains `core` with value `0`

## Property Tests

New file `tests/property/test_pam_hardening_properties.py`:

- faillock.conf template contains deny, unlock_time, fail_interval using configurable variables
- faillock.conf template hardcodes even_deny_root = true
- faillock.conf template hardcodes root_unlock_time using the unlock_time variable
- 50-hardening.conf template contains nproc, nofile, core limits
- 50-hardening.conf template hardcodes core to 0
- 50-hardening.conf template has separate root limits for nproc and nofile
- Defaults define all pam_faillock and pam_limits variables
- Tasks deploy faillock.conf and faillock PAM profile templates
- Tasks run pam-auth-update to enable faillock
- Tasks deploy resource limits to limits.d
- faillock PAM profile template contains correct Priority, Auth-Type, Auth-Final, and Account sections

## Admin Commands

The admin documentation (`docs/pam-hardening.md`) should include these commands:

```bash
# View failed login attempts for a user
faillock --user <username>

# Manually unlock a locked account
faillock --user <username> --reset

# View all users with failed attempts
faillock

# Check current resource limits for your session
ulimit -a

# Check a specific user's limits
su - <username> -c 'ulimit -a'
```

## Interaction with Existing Roles

- **fail2ban**: Complementary. fail2ban bans IPs after SSH failures; pam_faillock locks the account after auth failures regardless of source. Different layers, different protections.
- **login policy**: No conflict. pam_faillock counts auth failures; login.defs `LOGIN_RETRIES` controls how many attempts the `login` program offers per session. Both can fire independently.
- **sudo hardening**: Sudo uses PAM (`common-auth`) on Debian 12, so failed sudo password attempts count toward the pam_faillock lockout threshold. This is intentional — it prevents sudo brute-force attacks. The timed unlock (10 minutes) prevents permanent lockout.
- **ssh_hardening**: Complementary. SSH `MaxAuthTries` limits attempts per connection; pam_faillock counts across connections.
- **emergency_access**: Timed lockout (10 minutes) means emergency console access is never permanently blocked. An operator who knows the password waits 10 minutes or reboots (which clears `/run/faillock/`).
