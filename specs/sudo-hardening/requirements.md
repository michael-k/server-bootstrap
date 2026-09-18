# Sudo Hardening — Requirements

**Prefix:** `SUDO`

## Purpose

This spec covers how the two bootstrap accounts escalate privilege, and what
keeps that escalation both restricted and visible: the `sudo` package
itself; a per-account `sudoers.d` file naming each account individually,
one requiring a password and the other not; a shared `sudoers.d` drop-in
that sanitizes sudo's environment, fixes its search path, enriches its log
entries, and requires a controlling terminal; the configurable timeout on
a cached sudo authentication; and, alongside sudo, the `wheel` group and
the `pam_wheel` restriction that keep `su` on the same footing — named
principals only, nobody let in by default. `USR` creates the two accounts
this spec grants privileges to and puts one of them in `wheel`; this spec
is what makes holding one of those accounts mean something in particular
rather than unrestricted root.

## Scope

### In scope

- Installing the `sudo` package.
- The manual account's own `sudoers.d` file, requiring a password.
- The automation account's own `sudoers.d` file, granting sudo without a
  password.
- Validating every `sudoers.d` file this role writes with `visudo` before
  it is installed.
- The shared `00-sudo-security` defaults file and each directive it sets:
  `env_reset`, `secure_path`, `timestamp_timeout`, `log_year`, `log_host`,
  `use_pty`, and `requiretty` with the automation account's exemption from
  it.
- The configurable sudo credential cache timeout (`sudo_timestamp_timeout`,
  default 5 minutes).
- Creating the `wheel` group and adding the manual account to it.
- Restricting `su` to `wheel` members via `pam_wheel`.

### Out of scope

- Creating the two accounts, their uids, names, shells, supplementary
  groups, passwords, SSH keys and `authorized_keys` files, and the SSH
  access group — owned by `USR`. This spec assumes both accounts already
  exist before it grants either one anything.
- `login.defs`, console TTY restriction (`securetty`) and the shell idle
  timeout — owned by `LOGIN`.
- Account lockout (`faillock`) and resource limits (`limits.d`) — owned by
  `PAM`.
- SSH's own authentication configuration, including that the automation
  account authenticates by key only — sshd enforces that, and it is owned
  by `SSH`, not by anything in this spec.
- Independent, post-bootstrap confirmation of sudo and `su` behaviour on a
  live host — owned by `VRFY` and exercised further by the integration
  suite.

## Security invariants

**Upholds:** INV-7
**Allowances claimed:** none

INV-7 requires that privilege escalation be restricted to explicitly named
principals and leave an audit trail of its use, and this spec is what makes
that true rather than merely stated. Sudo is granted per account through
its own dedicated `sudoers.d` file (`SUDO-2`, `SUDO-3`) rather than through
a shared group entry, so the set of principals who can escalate is exactly
the set of files in `/etc/sudoers.d/` naming one account each. `su` is
restricted the same way, to members of a group with a fixed membership
(`SUDO-11` through `SUDO-13`). The audit trail is `SUDO-8`'s and `SUDO-9`'s:
enriched syslog entries and a sudo-controlled pty mean a session run
through sudo is both logged and, while it runs, observable.

The automation account's grant is passwordless (`SUDO-3`), which might look
like a departure from "restricted" — but INV-7 restricts escalation to
*named* principals with an *audit trail*, and says nothing about a
password being part of either property. The automation account is still
named individually in its own `sudoers.d` file, and its sudo use is logged
exactly as the manual account's is; the absence of a password changes how
the escalation is authenticated, not whether it is named or recorded. The
password itself would authenticate nothing a network attacker could not
already defeat by other means: the account has no interactive network
authenticator of its own (`SSH` enforces key-only access to it, `USR-6`
leaves it with no usable password at all), so a password prompt on `sudo`
would gate access already gated by the key that got the caller onto the
account in the first place. On that basis this spec upholds INV-7 outright
rather than bending it, and claims no allowance.

## Requirements

### SUDO-1 — `sudo` package installed

THE Bootstrap SHALL ensure the `sudo` package is installed.

**Why:** the base images this bootstrap targets are Debian cloud images,
which do not universally ship `sudo` preinstalled. Every other requirement
in this spec writes a file under `/etc/sudoers.d/` or otherwise assumes
`sudo` exists to read it; without this task, those files would sit inert
on a host where the very binary that would consult them is missing, and
every later task that writes one would still report success.
**Verified:** the task installs `sudo` via the package module with
`state: present`, which is idempotent and requires no version pin. No test
in either suite references this task; no unit or property assertion
checks that the package is present, installed, or referenced anywhere in
the role.

### SUDO-2 — Manual account granted password-required sudo

THE Bootstrap SHALL grant the manual access account sudo privileges
through its own `sudoers.d` file, requiring a password.

**Why:** requiring a password here is what makes the manual account's sudo
grant mean something distinct from the automation account's: a key that
reaches this account over SSH is not, by itself, enough to run a command
as root — the operator also has to know the password `USR-3` set. Placing
the grant in a file named after the account, rather than editing
`/etc/sudoers` or a shared group entry, is what keeps the grant legible:
removing this account's sudo access is deleting one file, and no other
account's privileges are represented in it.
**Verified:** the task writes `{{ manual_user_name }} ALL=(ALL:ALL) ALL`
to `/etc/sudoers.d/{{ manual_user_name }}`, mode `0440`, validated with
`visudo -cf %s` before being installed. The unit suite parses the task and
asserts the exact content, the mode, and the validation command; the
property suite asserts the same content and mode substrings, plus that a
`visudo`-validated file exists somewhere in the role. No test creates the
account and attempts to sudo as it — the integration suite does, on a real
bootstrapped VM, but that is outside either suite this spec's citations
name.

### SUDO-3 — Automation account granted passwordless sudo

THE Bootstrap SHALL grant the automation account sudo privileges through
its own `sudoers.d` file, without requiring a password.

**Why:** this account is the one the playbook itself runs subsequent tasks
as, non-interactively, over an SSH connection that is not present to
answer a password prompt. A password requirement here would not add a
meaningful barrier — see this spec's Security invariants — and would
instead fail every unattended run the moment it reached a `become: true`
task, discovered only when the run stops dead with no operator watching a
terminal to supply one.
**Verified:** the task writes
`{{ deploy_user_name }} ALL=(ALL:ALL) NOPASSWD:ALL` to
`/etc/sudoers.d/{{ deploy_user_name }}`, mode `0440`, validated with
`visudo -cf %s`. The unit suite parses the task and asserts the exact
content, the mode, and the validation command; the property suite asserts
the same content and mode substrings. No test exercises an actual
passwordless `sudo` invocation outside the integration suite.

### SUDO-4 — Sudo security defaults deployed as a validated drop-in

THE Bootstrap SHALL deploy the shared sudo security defaults as a
`sudoers.d` file, validated with `visudo` before being installed.

**Why:** every directive `SUDO-5` through `SUDO-10` sets lives in one file,
`/etc/sudoers.d/00-sudo-security`, rendered from a template rather than
edited in place on the host, so the defaults are identical on every
bootstrapped host and a single review of the template covers all of them.
Validating with `visudo` before installing is what stops a rendering
mistake — a stray character, an unresolved variable — from landing as a
syntax error in a file sudo reads on every invocation: `visudo -cf %s`
checks the rendered file in place before Ansible's `template` module
replaces the live one, so a broken render is caught and the previous
working file is left in place, rather than sudo itself refusing to run
for anyone once the broken file is live.
**Verified:** the task deploys `00-sudo-security.j2` to
`/etc/sudoers.d/00-sudo-security`, mode `0440`, with
`validate: "visudo -cf %s"`. The property suite asserts that the tasks
file names `00-sudo-security`, uses the `template` module, and contains
`visudo` somewhere — a whole-file substring search, not a check scoped to
this one task, so it would not catch the validation moving to a different
task while this one lost it.

### SUDO-5 — Sudo environment reset

THE Bootstrap SHALL reset sudo's environment before running an escalated
command.

**Why:** without `env_reset`, sudo carries the caller's environment into
the root-privileged command it runs, including variables like `LD_PRELOAD`
or `PYTHONPATH` that change what code an otherwise-trusted binary actually
executes. An attacker who can set environment variables in the calling
shell — which on a shared account is nearly anyone — can use an
unprivileged foothold to run arbitrary code as root the moment a
legitimate user next escalates, and nothing about the escalation looks
unusual: the command that ran is the one that was typed.
**Verified:** the template sets `Defaults    env_reset`. The parametrized
property test draws `env_reset` from its strategy on some fraction of its
hundred examples and asserts it appears in the rendered template text; no
test constructs an environment and confirms sudo actually discards it.

### SUDO-6 — Sudo command search path fixed

THE Bootstrap SHALL fix sudo's command search path to standard system
binary directories.

**Why:** `env_reset` clears the caller's environment, but sudo still needs
a `PATH` to resolve the command it was asked to run, and `secure_path` is
what stops that resolution from consulting a directory the caller
controls. Without it, a caller who can write anywhere earlier in an
inherited or default `PATH` — a writable directory of their own, a
current-directory entry — can shadow a common binary name, and sudo runs
their version with root privileges the moment someone else invokes what
looks like the standard command.
**Verified:** the template sets `secure_path` to exactly
`/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`. The property
suite has a dedicated test asserting every one of those six directories
appears in the template, plus the parametrized directive test. Neither
test confirms sudo actually refuses a binary found outside that path.

### SUDO-7 — Sudo credential cache timeout configurable

THE Bootstrap SHALL accept `sudo_timestamp_timeout` as a configurable
variable controlling how long a successful sudo authentication is cached,
defaulting to 5 minutes.

**Why:** sudo's own default timeout is 15 minutes on most distributions,
chosen for convenience rather than for this bootstrap's threat model; a
long-lived cached credential is exactly what turns a momentarily
unattended, already-authenticated terminal into a window an attacker with
physical or session access can escalate through without ever seeing a
password prompt. Making the value configurable, rather than accepting
sudo's shipped default silently, is what turns that window into a decision
an operator can see and shorten — or, for a use case this bootstrap did
not anticipate, lengthen — rather than an inherited property of whatever
sudo happens to ship with.
**Verified:** the template renders `timestamp_timeout={{
sudo_timestamp_timeout }}`, and the role's defaults define the variable as
`5`. Two property tests assert the variable name appears in the template
and the `sudo_timestamp_timeout:` key appears in the defaults file. No
test renders the template with a substituted value, and no test confirms
sudo actually re-prompts after the configured interval elapses.

### SUDO-8 — Sudo log entries enriched with year and host

THE Bootstrap SHALL enrich sudo's log entries with the year and the host,
relying on syslog and journald as sudo's log destination rather than a
separate sudo logfile.

**Why:** sudo already logs every invocation to syslog's AUTH facility,
which journald captures without any configuration here, so the audit
trail INV-7 requires already exists in outline; `log_host` and `log_year`
are what make an individual entry usable once it leaves that single host's
journal. A fleet that ships logs to a central collector loses the
host-column context syslog otherwise supplies unless each entry names its
own origin, and a rotated or archived log that spans a year boundary is
ambiguous about which December an undated entry's "Dec 31" belongs to
without the year on the line. A dedicated `logfile` directive was
considered and deliberately not added: it would duplicate syslog's own
record in a second location this bootstrap does not rotate, permission,
or ship anywhere, for no additional information.
**Verified:** the template sets `Defaults    log_year` and
`Defaults    log_host`. The parametrized directive test covers both
substrings, and a dedicated test asserts the template contains no
`Defaults` line naming `logfile` — evidence that the logfile alternative
was rejected and stays rejected, not evidence that syslog logging itself
works. No test inspects an actual log entry on a live host or confirms it
carries a year or a hostname.

### SUDO-9 — Escalated commands run in a sudo-controlled pty

THE Bootstrap SHALL run every escalated command in a pseudo-terminal that
sudo itself allocates and controls.

**Why:** without `use_pty`, a command sudo runs can inherit the caller's
own terminal directly, which is also the terminal certain interactive
programs use to detect and evade being monitored or logged — a script
that shells out through a character device it recognizes as its own
controlling tty behaves differently than one running under an unfamiliar
pty. Forcing sudo to allocate its own pty for the command closes that
distinction and is also what makes the session sudo runs one it can
observe end to end, which is the other half of INV-7's audit trail beyond
the log line sudo writes at invocation.
**Verified:** the template sets `Defaults    use_pty`. The parametrized
directive test asserts the substring appears in the rendered template. No
test starts a sudo session and confirms a pty was actually allocated for
it.

### SUDO-10 — Interactive sudo requires a controlling terminal, automation exempted

THE Bootstrap SHALL require a real controlling terminal for interactive
sudo use, exempting the automation account from that requirement.

**Why:** `requiretty` is what stops sudo from being invoked from a context
with no terminal at all — a cron job, a background script, an injected
command in a non-interactive pipe — closing off an escalation path that
does not go through an interactive session anyone could observe or be
asked to authenticate. The automation account is the one legitimate
exception: Ansible's own SSH connections run commands without allocating a
pty, so a blanket `requiretty` would break every task that account
executes with `become: true`, and the exemption is scoped to that one
account by name rather than lifted globally.
**Verified:** the template sets `Defaults    requiretty` and
`Defaults:{{ deploy_user_name }}    !requiretty`. A dedicated property test
asserts both directives are present and that the exemption line references
`deploy_user_name` rather than a literal username. No test attempts to
invoke sudo from a context with no tty and confirms it is refused, and
none confirms the automation account's exemption actually lets its
non-interactive invocations through.

### SUDO-11 — `wheel` group exists

THE Bootstrap SHALL create the `wheel` group.

**Why:** `pam_wheel`, with no `group=` option given, checks membership of
a group literally named `wheel` if one exists, falling back to the group
with GID 0 only when it does not. Debian does not create a group named
`wheel` by default — its GID-0 group is `root` — so without this task
`SUDO-13`'s restriction would silently fall back to checking `root`
membership instead of the intended, purpose-created group, changing who
can `su` without changing anything an operator reading the PAM
configuration would notice.
**Verified:** the task creates a group named `wheel` with the group
module. The property suite asserts both that the string `wheel` appears
in the tasks file and that the group module is used — a substring check
that would also pass if `wheel` appeared only in an unrelated comment.

### SUDO-12 — Manual account is a member of `wheel`

THE Bootstrap SHALL add the manual access account to the `wheel` group.

**Why:** creating `wheel` and restricting `su` to it accomplishes nothing
for the one account that is meant to use `su` — the manual account, whose
operator is the one falling back to a console session and a `su` prompt
in exactly the scenario `INV-3` and `INV-6` describe — unless that account
is actually a member. The automation account is deliberately left out: it
already has passwordless sudo (`SUDO-3`), so it has no legitimate reason
to invoke `su`, and adding it to `wheel` would extend a second, less
audited escalation path to an account that does not need one.
**Verified:** the task adds `{{ manual_user_name }}` to `wheel` with
`append: true`, so the membership does not disturb others `USR-8` may
already have granted. No test in the unit or property suite references
this task, the group, or the membership; the integration suite confirms
the automation account is *not* in `wheel` and cannot `su`, which is the
membership this requirement does not grant, not the one it does.

### SUDO-13 — `su` restricted to `wheel` group members

THE Bootstrap SHALL restrict `su` to members of the `wheel` group via
`pam_wheel`.

**Why:** without this restriction, `su` is available to any local account
that knows or can guess a target account's password, which is a second
escalation path running in parallel to sudo's, gated by a different
credential and invisible to anything that only reasons about the sudoers
files `SUDO-2` through `SUDO-4` write. Restricting it to `wheel` collapses
that second path back onto the same named, deliberately small set of
principals the rest of this spec maintains, so `INV-7`'s restriction to
named principals holds for `su` as well as for `sudo`.
**Verified:** the task ensures
`auth       required   pam_wheel.so` is present in `/etc/pam.d/su`, using
a `regexp` that matches Debian's shipped commented line
(`# auth       required   pam_wheel.so`) so the module uncomments and
rewrites it in place rather than appending a duplicate. The property suite
asserts `pam_wheel`, `/etc/pam.d/su`, and the `lineinfile` module all
appear in the tasks file. The integration suite confirms, on a real
bootstrapped VM, that an account outside `wheel` is refused by `su`. No
test in either the unit or property suite confirms a `wheel` member is
actually let through, only that non-members are not — and none inspects
`/etc/pam.d/su`'s content after the run, only the task that edits it.
