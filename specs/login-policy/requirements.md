# Login Policy Hardening — Requirements

**Prefix:** `LOGIN`

## Purpose

This spec covers what happens once a login prompt — console, or any other
path that ends up reading `/etc/login.defs` or `/etc/pam.d/login` — is
actually presented: the system-wide defaults in `/etc/login.defs`, which
apply to every account and every login method, hardened past Debian's
shipped values in four places; whether root is allowed to authenticate at
the console at all, gated by `pam_securetty` and the fixed list of TTYs in
`/etc/securetty` it consults; and what happens to an interactive shell left
idle at its own prompt once login has already succeeded. `USR` decides
which accounts exist and which shell each one runs; `SUDO` decides what a
shell can escalate to once it is running; this spec is what governs the
login event itself and the shell session immediately after it, for every
account, independent of which one is using it.

## Scope

### In scope

- Deploying a hardened `/etc/login.defs` from a template, and each setting
  the template changes from Debian's shipped default: `LOG_OK_LOGINS`,
  `LOGIN_RETRIES`, `LOGIN_TIMEOUT`, `UMASK`.
- Enabling `pam_securetty` in `/etc/pam.d/login` for console login.
- Deploying `/etc/securetty`, the fixed list of TTYs `pam_securetty`
  consults to decide whether root may log in at the tty presenting the
  prompt.
- Deploying the shell idle timeout (`TMOUT`) to
  `/etc/profile.d/shell-timeout.sh`: its configurable duration and its
  `readonly` declaration.
- The four configurable defaults this spec's tasks and templates consume:
  `login_policy_tmout`, `login_policy_umask`, `login_policy_retries`,
  `login_policy_timeout`.

### Out of scope

- Creating the bootstrap accounts, their uids, names, shells, supplementary
  groups, and SSH keys — owned by `USR`. This spec assumes both accounts
  already exist and only changes what login does with them; whether a
  shell ever reads the idle-timeout drop-in this spec deploys (`LOGIN-5`)
  depends on the login shell `USR-7` assigns, not on anything here.
- Sudo and `su` privilege escalation, including the `wheel` group and
  `pam_wheel` — owned by `SUDO`.
- Account lockout after repeated failed authentication (`pam_faillock`) and
  resource limits (`limits.d`) — owned by `PAM`. `LOGIN_RETRIES` and
  `LOGIN_TIMEOUT` here are `/bin/login`'s own console-prompt attempt and
  time budget, a mechanism entirely separate from `pam_faillock`'s
  cross-service failed-attempt counter; the two are easy to conflate
  because both are described as "login attempts," and this spec is only
  the former.
- SSH's own authentication and login restrictions, including
  `PermitRootLogin`, `MaxAuthTries` and `LoginGraceTime` — owned by `SSH`.
  This spec's `LOGIN-8`/`LOGIN-9` numeric defaults are chosen to match
  SSH's, a design decision recorded in `design.md`, not a shared
  mechanism or a shared variable.
- Independent, post-bootstrap confirmation of login behaviour on a live
  host — owned by `VRFY` and exercised further by the integration suite.

## Security invariants

**Upholds:** INV-3
**Allowances claimed:** none

INV-3 requires that root have no remote login path. sshd's own
`PermitRootLogin no` (owned by `SSH`) is what makes that true for the
network login path this bootstrap actually exposes; this spec is what
keeps it true if that first barrier is ever bypassed or reached by some
path outside sshd's own configuration. `LOGIN-3` wires `pam_securetty`
into `/etc/pam.d/login`, and `LOGIN-4`'s `/etc/securetty` is the fixed
allow-list `pam_securetty` consults: physical/virtual console TTYs, and
the serial TTYs a hosting provider's own out-of-band console substitutes
for them, with pseudo-terminals deliberately excluded. Pseudo-terminals
are what every network-terminated interactive session presents as its own
controlling tty — SSH's included — so as long as `/etc/securetty` names no
`pts/` device, no session that reached the host over the network can
present a tty `pam_securetty` will accept for direct root login,
independent of which PAM service asked. Both mechanisms are
console-recoverable in the sense `INV-6` requires: an operator with actual
physical or provider-console access retains root login exactly where they
had it, while the same path stays refused to anything arriving as a pty.
This spec claims no allowance: it does not bend INV-3, it is one of the
two mechanisms — alongside `SSH`'s own refusal of root at the daemon level
— that make it true.

## Requirements

### LOGIN-1 — Hardened `login.defs` deployed

THE Bootstrap SHALL deploy a hardened `/etc/login.defs` from a template,
changing only the settings this spec hardens and leaving Debian's other
shipped defaults in place.

**Why:** the base image ships its own `login.defs` with sane-but-generic
defaults; rather than hand-patching individual lines on the host —
fragile, and easy for a value to drift silently across re-runs — the
whole file is rendered from one template so every setting is visible and
reviewed in one place. Deliberately preserving unrelated settings
(`UID_MIN`/`UID_MAX`, `ENCRYPT_METHOD`, `HOME_MODE`, password aging, and
more) keeps the blast radius of this hardening limited to the four
settings intentionally changed (`LOGIN-2`, `LOGIN-7`, `LOGIN-8`,
`LOGIN-9`), rather than accidentally reintroducing or dropping a Debian
default that other machinery — `useradd`'s uid allocation, existing
password hashes — depends on.
**Verified:** the task "Deploy hardened login.defs" renders
`login.defs.j2` to `/etc/login.defs`, mode `0644`
(`test_tasks_deploy_login_defs`). Three property tests confirm specific
preserved settings remain at Debian's original values: `UID_MIN 1000` /
`UID_MAX 60000` (`test_login_defs_preserves_uid_ranges`),
`ENCRYPT_METHOD YESCRYPT` (`test_login_defs_preserves_encrypt_method`),
and `HOME_MODE 0700` (`test_login_defs_preserves_home_mode`). All three
are whole-file substring checks — a template that dropped every other
Debian-default directive while keeping just these three lines would still
pass all three, and no test enumerates the file's full directive set
against Debian's shipped `login.defs` to confirm nothing else silently
drifted.

### LOGIN-2 — Successful console logins logged

THE Bootstrap SHALL log successful console logins.

**Why:** Debian ships `LOG_OK_LOGINS` as `no`: only failed logins reach
the log, so an operator reviewing auth activity sees every wrong password
guess but not the successful login that followed it — or one that needed
no guessing at all, using a credential obtained some other way. Setting
it to `yes` gives the console login path an audit trail parallel to what
sshd's own logging already provides for the network path.
**Verified:** `login.defs.j2` sets `LOG_OK_LOGINS yes` unconditionally
(not templated). `test_login_defs_enables_ok_login_logging` parses the
rendered template for an uncommented `LOG_OK_LOGINS` line and asserts it
reads `yes`. No test confirms an actual console login is ever recorded in
syslog or journald; `docs/login-policy.md` documents how an operator
would query it (`journalctl SYSLOG_IDENTIFIER=login`), but that query is
never exercised by either suite.

### LOGIN-3 — `pam_securetty` enabled for console login

THE Bootstrap SHALL enable `pam_securetty` for console login via
`/etc/pam.d/login`.

**Why:** `pam_securetty` is what makes `/etc/securetty`'s tty list
(`LOGIN-4`) actually enforced for root — without a PAM module consulting
it, the file is inert data nobody reads. Wiring it into `/etc/pam.d/login`
specifically, rather than a shared PAM file, is what scopes the
restriction to console login: SSH consults a different PAM service
entirely and denies root a different way, at the sshd level, owned by
`SSH`; `su` and `sudo` are different services again, restricted by
`SUDO`'s own PAM configuration. This task's only job is making the
console path enforce the tty list.
**Verified:** the task "Ensure pam_securetty is enabled for console
login" uses `lineinfile` against `/etc/pam.d/login` with a `regexp` that
matches Debian's shipped line whether or not it starts commented out, so
the directive is uncommented in place rather than duplicated.
`test_tasks_ensure_pam_securetty` asserts the task references
`pam_securetty`, targets `/etc/pam.d/login`, and uses the `lineinfile`
module — substring checks against the whole tasks file, not scoped to
this one task. No test confirms the line is actually enabled after a run,
or that a login attempt from a tty outside `/etc/securetty` is actually
refused.

### LOGIN-4 — Console login restricted to a fixed list of TTYs

THE Bootstrap SHALL restrict root console login to an explicit list of
virtual and serial console TTYs via `/etc/securetty`, excluding
pseudo-terminals.

**Why:** `pam_securetty` (`LOGIN-3`) enforces this file, but the
invariant it upholds only holds because of what the file actually
contains: `tty1` through `tty6` cover the physical/virtual console a KVM
or a hosting provider's console view attaches to, `ttyS0`/`ttyS1` cover
the serial console some hosting providers substitute for it, and — the
property that matters most for `INV-3` — no `pts/` entry is present.
Pseudo-terminals are what every network-terminated interactive session
presents as its controlling tty, SSH's included; keeping the list to
physical/virtual/serial console devices only means no session that
reached the host over the network can ever present a tty this file
accepts for direct root login, regardless of which PAM service asked.
This is what makes `/etc/securetty` a second, independent barrier behind
sshd's own `PermitRootLogin no`, rather than a restatement of it.
**Verified:** the task "Deploy securetty for console TTY restrictions"
renders `securetty.j2` to `/etc/securetty`, mode `0600`
(`test_tasks_deploy_securetty`). Two parametrized property tests confirm
`tty1`–`tty6` and `ttyS0`/`ttyS1` each appear as a whole line
(`test_securetty_lists_virtual_console_ttys`,
`test_securetty_lists_serial_console_ttys`); a third confirms no `pts/`
substring appears anywhere in the file
(`test_securetty_does_not_list_pseudo_terminals`). The template has no
Jinja variables, so there is no rendering failure mode these tests would
miss, but none of them exercises an actual login attempt: no test
confirms `pam_securetty` is actually the module consulting this file, or
that a tty outside the list is actually refused.

### LOGIN-5 — Shell idle timeout deployed as a configurable, exported variable

THE Bootstrap SHALL deploy a shell idle timeout, accepting
`login_policy_tmout` (default 600 seconds) as the number of idle seconds
before an interactive shell logs itself out, and export it so child
shells inherit it.

**Why:** `TMOUT` is the shell's own built-in idle-logout mechanism;
deploying it as a drop-in under `/etc/profile.d/` rather than editing
`/etc/profile` or a per-account rc file means it applies uniformly to
every login shell that sources the profile.d directory, without
hand-editing per-account files, and re-renders identically on every run.
Exporting it is what lets a shell spawned from a login shell — a
subshell, most invocations of a build tool, a script that sources another
— still inherit the same timeout, rather than losing it the moment
control passes to a child process.
**Verified:** the task "Deploy shell idle timeout" renders
`shell-timeout.sh.j2` to `/etc/profile.d/shell-timeout.sh`, mode `0644`
(`test_tasks_deploy_shell_timeout`). The defaults file defines
`login_policy_tmout: 600` (`test_defaults_define_tmout`). The template
sets `TMOUT={{ login_policy_tmout }}` and `export TMOUT`
(`test_shell_timeout_sets_tmout_variable`,
`test_shell_timeout_is_exported`). No test confirms the file is actually
sourced by any real shell at login — see `LOGIN-6`'s Verified note and
this spec's design `## Key decisions` for why that matters more than it
might look.

### LOGIN-6 — Idle timeout marked read-only, advisory only

THE Bootstrap SHALL mark the deployed `TMOUT` variable `readonly` in the
shell that sources it.

**Why:** without `readonly`, a user's own shell rc executing after
`/etc/profile.d` could reassign or unset `TMOUT` in one line, silently
undoing the timeout for that session with no trace. `readonly` stops that
one specific, casual override within the shell instance that sourced this
file. It is not, and this spec does not represent it as, a mechanism that
prevents a user from going without the timeout altogether — the design's
`## Key decisions` section states plainly what this control is and is not
worth.
**Verified:** the template sets `readonly TMOUT` immediately after
assigning it. `test_shell_timeout_is_readonly` asserts the literal string
is present. No test, and no mechanism in the implementation, confirms
that a shell which never sources `/etc/profile.d/shell-timeout.sh` — a
non-login shell, a shell started with an option that skips the profile,
or an account whose login shell does not read `/etc/profile.d` at all —
ever has `TMOUT` set, `readonly` or otherwise.

### LOGIN-7 — Default file-creation mask hardened to 027

THE Bootstrap SHALL set the default umask to `027`.

**Why:** Debian's shipped `login.defs` leaves `UMASK` unset, which in
practice yields an effective `022` for most login shells — a new file is
readable by every local account by default, and a new directory is
world-traversable. `027` removes the "other" permission bits entirely, so
a file or directory an operator or a service creates is unreadable
outside its own group unless something deliberately widens it afterward.
**Verified:** `login.defs.j2` sets `UMASK {{ login_policy_umask }}`; the
defaults file defines `login_policy_umask: "027"`
(`test_defaults_define_umask`). The parametrized
`test_login_defs_has_hardened_settings` asserts `UMASK` and
`login_policy_umask` both appear somewhere in the rendered template.
Neither test confirms the two appear on the same line, so a rendered file
that hardcoded a different value on the `UMASK` line while
`login_policy_umask` lingered, unused, in an unrelated comment would still
pass; and no test confirms a umask of `027` actually governs a file a
process creates on a live host.

### LOGIN-8 — Console login retry limit configurable

THE Bootstrap SHALL accept `login_policy_retries` (default 3) as the
maximum console login attempts `/bin/login` permits before refusing
further tries.

**Why:** Debian's default of 5 gives an attacker at the physical or
virtual console five password guesses per login prompt; 3 matches this
bootstrap's own SSH `MaxAuthTries` (`ssh_max_auth_tries: 3` in
`roles/ssh_hardening/defaults/main.yml`) so the console path shares the
same attempt budget as the network path this bootstrap otherwise
hardens, rather than being left deliberately more permissive.
**Verified:** `login.defs.j2` sets `LOGIN_RETRIES {{
login_policy_retries }}`; the defaults file defines
`login_policy_retries: 3` (`test_defaults_define_retries`).
`test_login_defs_has_hardened_settings` asserts `LOGIN_RETRIES` and
`login_policy_retries` both appear in the rendered file — the same
file-wide, not same-line, limitation noted under `LOGIN-7`. No test
confirms a fourth attempt at a real console prompt is actually refused,
and no mechanism ties this value to SSH's independently configured one:
the match is a design choice recorded once, not an enforced invariant.

### LOGIN-9 — Console login timeout limit configurable

THE Bootstrap SHALL accept `login_policy_timeout` (default 30 seconds) as
the number of seconds `/bin/login` allows to complete a console login
prompt.

**Why:** Debian's default of 60 seconds gives a walk-up attacker a full
minute to attempt or complete a login before the prompt gives up; 30
matches this bootstrap's own SSH `LoginGraceTime` (`ssh_login_grace_time:
"30s"` in `roles/ssh_hardening/defaults/main.yml`) for the same reason
`LOGIN-8` matches `MaxAuthTries` — one time budget for whichever path,
console or network, presents the login prompt.
**Verified:** `login.defs.j2` sets `LOGIN_TIMEOUT {{
login_policy_timeout }}`; the defaults file defines
`login_policy_timeout: 30` (`test_defaults_define_timeout`).
`test_login_defs_has_hardened_settings` asserts `LOGIN_TIMEOUT` and
`login_policy_timeout` both appear in the rendered file, with the same
file-wide limitation. No test confirms a login prompt left idle for
longer than the configured value is actually abandoned, and as with
`LOGIN-8`, nothing enforces that this value and SSH's stay equal beyond
both having been set to the same number by hand.
