# PAM Hardening — Requirements

**Prefix:** `PAM`

## Purpose

This spec covers the two PAM mechanisms that sit underneath every local and
console authenticator this bootstrap exposes — console login, `su`, and
`sudo` — rather than any one of them: `pam_faillock`, which counts failed
authentication attempts against an account and locks it out once a
configurable threshold is reached, and `pam_limits`, which caps how many
processes and open file descriptors a PAM-authenticated session may hold.
`USR` decides which accounts exist; `SUDO` decides what they may escalate
to; `LOGIN` decides what happens at the console login prompt itself; this
spec is what stands behind all three, bounding how many times any of them
may be guessed at before the account guessing them is shut out, and
bounding what a session obtained through any of them may then consume.

## Scope

### In scope

- Deploying `/etc/security/faillock.conf` from a template, and its three
  configurable settings: `deny`, `unlock_time`, `fail_interval`.
- Locking the root account under the same policy as every other account,
  with the same unlock timeout, rather than exempting it.
- The two `pam-auth-update` profiles that wire `pam_faillock` into
  `/etc/pam.d/common-auth` — `faillock-preauth` and `faillock-authfail` —
  and the priority each declares relative to `pam_unix` and to each other.
- Removing the single-profile deployment `ec94b3d` superseded, so a host
  still carrying it self-heals on the next run.
- Rebuilding `/etc/pam.d/common-auth` via `pam-auth-update` whenever any of
  the profiles above changes.
- Deploying `/etc/security/limits.d/50-hardening.conf` from a template, and
  its four configurable settings: `nproc` and `nofile`, each set separately
  for root and for every other account.
- Hardcoding core dumps to 0 and every limit in this file to a hard ceiling,
  never a soft one.

### Out of scope

- Creating the accounts `pam_faillock` and `pam_limits` govern, their uids,
  names, shells, and SSH keys — owned by `USR`.
- Sudo's own configuration, the `wheel` group, and `pam_wheel`'s restriction
  of `su` — owned by `SUDO`. This spec's lockout applies underneath both,
  since both authenticate through PAM's `common-auth`, but neither
  mechanism is this spec's to configure.
- `/etc/login.defs`, `/etc/securetty`, and the shell idle timeout — owned by
  `LOGIN`. `LOGIN-8`'s console retry limit and `LOGIN-9`'s console timeout
  are `/bin/login`'s own attempt and time budget, entirely separate from
  the cross-service failure counter this spec configures.
- SSH's own authentication — owned by `SSH`. SSH accepts no passwords at
  all (`INV-2`), so it presents `pam_faillock` nothing to count; brute-force
  resistance for the SSH surface is `fail2ban`'s concern, not this spec's —
  see `## Interactions`.
- Independent, post-bootstrap confirmation of lockout and resource-limit
  behaviour on a live host — owned by `VRFY` and exercised further by the
  integration suite.

## Security invariants

**Upholds:** INV-7
**Relies on:** INV-2, INV-3, INV-6
**Allowances claimed:** none

`SUDO-2` requires a password from the manual account before it may
escalate, and that password is the one interactive secret this bootstrap's
threat model has to protect against being guessed rather than stolen.
Without a bound on failed attempts, that password is only as strong as
however long an attacker is willing to keep guessing it, at the console, at
`su`, or at `sudo` itself — all three consult PAM's `common-auth`, which is
where this spec's two profiles sit. `PAM-2` through `PAM-7` are what turn
"a password exists" into "a password that can only be guessed a bounded
number of times before the account guessing it is locked out," which is
what makes `INV-7`'s named, audited escalation path actually resistant to
being brute-forced rather than merely observed while it is.

This spec relies on `INV-2` to know where its own boundary is: `INV-2`
keeps SSH from ever accepting a password, which means SSH presents
`pam_faillock` nothing to count in the first place — there is no failed
password attempt for `common-auth` to see, because there is no password
prompt. Guarding the SSH surface against repeated connection attempts is
therefore a different mechanism entirely, owned by the `fail2ban` spec, not
by anything here; `## Interactions` names that split against `F2B`'s own
requirement IDs.

It also relies on `INV-3` and `INV-6`. `PAM-5` locks root out under the
same policy as every other account, which is acceptable only because root
has no remote login path (`INV-3`) and a lockout stays recoverable (`INV-6`);
`design.md` sets out both, and records how the recovery works. The
recovery `INV-6` counts here is waiting. With `even_deny_root`, a locked
root is refused at the console login and at `su`, even with the right
password, until `root_unlock_time` passes, and a locked manual account is
refused at `sudo` and at the console login until `unlock_time` passes.
Waiting out that timer at the console is the console-only recovery, and by
the reading `INV-6`'s **Why:** records it satisfies `INV-6`. The timer
exists only while `pam_faillock_unlock_time` is non-zero: `faillock.conf(5)`
reads 0 as never unlocking, and nothing in the role refuses that value.

This spec claims no allowance: it does not bend `INV-7`, it hardens the one
path (`sudo`'s password prompt) that gives `INV-7`'s named principals
something an attacker could otherwise guess.

## Requirements

### PAM-1 — Faillock configuration deployed from a template

THE Bootstrap SHALL deploy `/etc/security/faillock.conf` from a template.

**Why:** rendering the whole file from one template, rather than editing
individual lines on the host, means every lockout setting is reviewed in
one place and re-renders identically on every run, the same rationale
`LOGIN-1` and `SUDO-4` apply to their own templated files.
**Verified:** the task "Deploy faillock configuration" renders
`faillock.conf.j2` to `/etc/security/faillock.conf`, mode `0644`
(`test_tasks_deploy_faillock_conf`). No test confirms the rendered file is
actually the one `pam_faillock` reads at authentication time.

### PAM-2 — Failed-attempt threshold configurable

THE Bootstrap SHALL accept `pam_faillock_deny` (default 5) as the number of
failed authentication attempts before an account is locked out.

**Why:** the whole mechanism this spec exists for depends on this number
being a deliberate, reviewable choice rather than whatever `pam_faillock`
ships with; making it a role default rather than a hardcoded value lets a
deployment tighten or loosen it without editing the template.
**Verified:** the template sets `deny = {{ pam_faillock_deny }}`; the
defaults file defines `pam_faillock_deny: 5`
(`test_defaults_define_faillock_deny`). A parametrized property test
confirms both the setting name and the variable name appear in the
rendered template (`test_faillock_conf_has_configurable_settings`) — a
whole-file substring check, not one confirming the two sit on the same
line. No test renders the template with a substituted value or drives five
actual failed attempts to confirm the sixth is refused.

### PAM-3 — Unlock timeout configurable

THE Bootstrap SHALL accept `pam_faillock_unlock_time` (default 600 seconds)
as the number of seconds a locked-out account remains locked before
`pam_faillock` unlocks it automatically.

**Why:** an unbounded lockout would turn a mistyped password into a denial
of service against the operator's own access; a bounded, configurable
timeout is what keeps this spec's protection from becoming its own
availability problem. `PAM-5` reuses this same value for root, rather than
giving root an independently configurable timeout of its own.
**Verified:** the template sets `unlock_time = {{
pam_faillock_unlock_time }}`; the defaults file defines
`pam_faillock_unlock_time: 600` (`test_defaults_define_faillock_unlock_time`).
The same parametrized test as `PAM-2` confirms the setting and variable
names both appear in the rendered file
(`test_faillock_conf_has_configurable_settings`). No test confirms an
actual lockout clears after the configured interval elapses.

### PAM-4 — Failure-counting window configurable

THE Bootstrap SHALL accept `pam_faillock_fail_interval` (default 900
seconds) as the sliding window, in seconds, over which failed attempts are
counted toward the lockout threshold.

**Why:** without a window, a handful of failures scattered over weeks or
months would eventually add up to the same lockout as five failures in
quick succession — the window is what makes `PAM-2`'s threshold describe a
burst of guessing rather than a lifetime tally.
**Verified:** the template sets `fail_interval = {{
pam_faillock_fail_interval }}`; the defaults file defines
`pam_faillock_fail_interval: 900`
(`test_defaults_define_faillock_fail_interval`). The same parametrized test
as `PAM-2` and `PAM-3` confirms the setting and variable names both appear
in the rendered file (`test_faillock_conf_has_configurable_settings`). No
test confirms failures outside the window are actually excluded from the
count.

### PAM-5 — Root locked out under the same policy, not exempted

THE Bootstrap SHALL lock the root account out under the same policy as
every other account, hardcoding `even_deny_root = true` and reusing
`pam_faillock_unlock_time` as root's own unlock timeout, with neither value
exposed as a separately configurable setting.

**Why:** `pam_faillock` exempts root from lockout by default, on the
reasoning that locking out the one account every other recovery path
assumes is always available is too dangerous to enable casually; this
bootstrap makes the opposite choice deliberately, because — per this
spec's `## Security invariants` — root has no remote login path (`INV-3`)
and is reached only by escalating from an already-authenticated account, so
exempting it from lockout would leave exactly the account an attacker who
has already breached one layer would target next with no bound on how many
times they may keep guessing. Neither value is made configurable, unlike
`PAM-2` through `PAM-4`: whether root is exempt from lockout is treated as
this bootstrap's security policy, not a per-deployment tuning knob, the
same reasoning `LOGIN-7`'s `umask` and `SUDO-5`'s `env_reset` apply to
their own hardcoded directives.
**Verified:** the template sets `even_deny_root = true` unconditionally and
`root_unlock_time = {{ pam_faillock_unlock_time }}`, reusing `PAM-3`'s
variable rather than a separate one. `test_faillock_conf_hardcodes_even_deny_root`
scans the rendered file line by line for an uncommented `even_deny_root`
directive and asserts it reads `true`; `test_faillock_conf_has_root_unlock_time`
asserts `root_unlock_time` and `pam_faillock_unlock_time` both appear
somewhere in the file, the same file-wide, not same-line, limitation this
spec's other configurable-setting tests share. No test confirms root is
actually locked out after five failed attempts, or that the lockout clears
after `pam_faillock_unlock_time` seconds; see `design.md`'s `## Failure
modes` for what this requirement means for the manual account's own
recovery path when `even_deny_root` and `LOGIN-4`'s console restriction
combine.

### PAM-6 — Faillock preauth profile deployed ahead of `pam_unix`

THE Bootstrap SHALL deploy a `pam-auth-update` profile named
`faillock-preauth`, at a priority higher than `pam_unix`'s (256), that
checks whether an account is already locked out before password
authentication runs.

**Why:** `pam_faillock`'s preauth call has to run before `pam_unix` gets a
chance to prompt for or check a password at all — otherwise an
already-locked account would still reach the password prompt, and only the
*next* mechanism would have a chance to refuse it. `Priority: 512` places
this profile's `Auth:`/`Auth-Initial:` stanzas ahead of `pam_unix`'s own
`Priority: 256` in the assembled `common-auth` stack. See `design.md`'s
`## Key decisions` for why this has to be its own profile rather than a
second stanza inside one shared with `PAM-7`.
**Verified:** `faillock-preauth-pam-config.j2` sets `Priority: 512` and
`Auth-Type: Primary` with `required pam_faillock.so preauth` in both `Auth:`
and `Auth-Initial:`. `test_preauth_profile_has_higher_priority_than_unix`
and `test_preauth_profile_contains_preauth_directive` each assert these
substrings against the template file directly. The task "Deploy faillock
preauth PAM profile" renders it to
`/usr/share/pam-configs/faillock-preauth`
(`test_tasks_deploy_faillock_pam_profiles`). No test renders
`/etc/pam.d/common-auth` itself or confirms this profile's stanza actually
lands ahead of `pam_unix`'s in the assembled file, only that each source
profile states the priority that should produce that ordering.

### PAM-7 — Faillock authfail profile deployed behind `pam_unix`

THE Bootstrap SHALL deploy a `pam-auth-update` profile named
`faillock-authfail`, at a priority lower than `pam_unix`'s (256), that
denies authentication once the configured failure threshold is reached.

**Why:** unlike preauth, this half of `pam_faillock` has to run *after*
`pam_unix` has already recorded whether the password just presented was
correct — its job is to react to that specific attempt's outcome, not to
guess at it independently. `Priority: 128` places this profile's
`Auth:`/`Auth-Initial:` stanzas behind `pam_unix`'s `Priority: 256`. See
`design.md`'s `## Key decisions` for what runs this after, rather than
before, `pam_unix` actually protects against. `PAM-17` covers this same
profile's other job, resetting the failure counter on success, which is a
distinct behaviour realised in a different section of the same file.
**Verified:** `faillock-authfail-pam-config.j2` sets `Priority: 128` and
`Auth-Type: Primary` with `[default=die] pam_faillock.so authfail` in both
`Auth:` and `Auth-Initial:`. `test_authfail_profile_has_lower_priority_than_unix`
and `test_authfail_profile_contains_authfail_directive` each assert these
substrings against the template file directly. The task "Deploy faillock
authfail PAM profile" renders it to
`/usr/share/pam-configs/faillock-authfail`
(`test_tasks_deploy_faillock_pam_profiles`). No test confirms a fifth
failure is actually denied.

### PAM-8 — Superseded single-profile deployment removed

THE Bootstrap SHALL remove the single-profile `faillock` deployment that
`PAM-6` and `PAM-7` superseded, so a host still carrying it converges to
the two-profile deployment on its next run.

**Why:** before `ec94b3d`, this role deployed one profile,
`/usr/share/pam-configs/faillock`, that tried to express both preauth and
authfail in a single `Auth-Type: Primary` block at one priority — the
defect `design.md`'s `## Key decisions` explains. Deploying the two
replacement profiles without removing the old one would leave a
previously-bootstrapped host with three profiles, the broken one still
registered in `pam-auth-update`'s state; removing it explicitly is what
lets `INV-9` hold — a re-run converges a host that predates this fix to the
same state as one bootstrapped after it, rather than leaving stale,
broken configuration beside the corrected one.
**Verified:** the task "Remove legacy faillock PAM profile" deletes
`/usr/share/pam-configs/faillock` with `state: absent` and notifies the
handler `PAM-9` defines. Neither property suite has a test asserting this
task's presence or its `state: absent`; the removal is exercised only by
`tests/verify_bootstrap.yml`'s post-bootstrap check that the legacy path is
absent, which is outside this spec's citations (owned by `VRFY`).

### PAM-9 — `common-auth` rebuilt after any faillock profile change

THE Bootstrap SHALL rebuild `/etc/pam.d/common-auth` via `pam-auth-update`
whenever the faillock preauth profile, the faillock authfail profile, or
the legacy profile's removal changes anything on disk.

**Why:** `/usr/share/pam-configs/*` files are only pam-auth-update's own
source data; nothing PAM actually consults reads them directly.
`pam-auth-update --enable faillock-preauth faillock-authfail` is what
regenerates `/etc/pam.d/common-auth` itself from that source data, in the
priority order `PAM-6` and `PAM-7` declare. Without this handler, every
other requirement in this spec would deploy correctly-authored source files
that never reach the PAM stack a real authentication attempt walks.
**Verified:** all three tasks that touch `/usr/share/pam-configs/faillock*`
carry `notify: Rebuild PAM common-auth`; the handler runs `pam-auth-update
--enable faillock-preauth faillock-authfail` with `changed_when: true`.
`test_tasks_enable_faillock_via_pam_auth_update` asserts the string
`pam-auth-update` appears somewhere in the combined text of the tasks file
and the handlers file — it does not confirm the handler is actually wired
to any specific task via `notify`, or that it names both profiles by name
rather than some other invocation. No test in either suite runs
`pam-auth-update` and inspects the resulting `/etc/pam.d/common-auth`; see
`design.md`'s `## Failure modes` for what `changed_when: true` means on
every run, whether or not anything actually changed.

### PAM-10 — Process limit configurable for non-root accounts

THE Bootstrap SHALL accept `pam_limits_nproc` (default 1024) as the hard
limit on the number of processes a non-root, PAM-authenticated session may
hold.

**Why:** an unbounded process count for an ordinary account is what a fork
bomb, accidental or deliberate, needs to exhaust the system's process table
and starve every other account and service on the host; a hard ceiling
below the point of system-wide exhaustion is what keeps one account's
runaway process tree from taking the whole host down with it.
**Verified:** the template sets `*  hard  nproc  {{ pam_limits_nproc }}`;
the defaults file defines `pam_limits_nproc: 1024`
(`test_defaults_define_limits_nproc`). `test_limits_template_has_separate_root_nproc`
and the parametrized `test_limits_template_contains_all_limit_types` each
assert substrings against the rendered template. No test substitutes a
value and confirms a session is actually capped at it.

### PAM-11 — Process limit configurable for root, set separately

THE Bootstrap SHALL accept `pam_limits_nproc_root` (default 2048) as a
process-count hard limit for root distinct from `PAM-10`'s, rather than
subjecting root to the same ceiling as every other account.

**Why:** root routinely runs more concurrent processes than an ordinary
account in the course of legitimate system administration and service
management; giving it the same ceiling as `PAM-10` would risk the limit
itself becoming an availability problem for root's own legitimate work,
while giving it no limit at all would leave the fork-bomb protection
`PAM-10` exists for entirely bypassed by anything already running, or
escalated to, as root.
**Verified:** the template sets `root  hard  nproc  {{
pam_limits_nproc_root }}`; the defaults file defines
`pam_limits_nproc_root: 2048` (`test_defaults_define_limits_nproc_root`).
`test_limits_template_has_separate_root_nproc` asserts both
`pam_limits_nproc_root` and `pam_limits_nproc` appear in the rendered
template — evidence both variables are present, not that each governs the
line it is meant to. No test substitutes a value or confirms root is
actually capped at it.

### PAM-12 — Open file descriptor limit configurable for non-root accounts

THE Bootstrap SHALL accept `pam_limits_nofile` (default 4096) as the hard
limit on open file descriptors for a non-root, PAM-authenticated session.

**Why:** every open network connection, log file, and pipe a process holds
consumes one file descriptor; without a ceiling, a process leaking
descriptors — through a bug or a deliberate exhaustion attempt — can
consume every descriptor the kernel will hand out system-wide, denying
every other process, including ones needed to diagnose or recover from the
exhaustion, a new one of its own.
**Verified:** the template sets `*  hard  nofile  {{ pam_limits_nofile }}`;
the defaults file defines `pam_limits_nofile: 4096`
(`test_defaults_define_limits_nofile`). `test_limits_template_has_separate_root_nofile`
and the parametrized `test_limits_template_contains_all_limit_types` each
assert substrings against the rendered template. No test substitutes a
value or confirms a session is actually capped at it.

### PAM-13 — Open file descriptor limit configurable for root, set separately

THE Bootstrap SHALL accept `pam_limits_nofile_root` (default 8192) as an
open-file-descriptor hard limit for root distinct from `PAM-12`'s, rather
than subjecting root to the same ceiling as every other account.

**Why:** the same reasoning as `PAM-11` applies to file descriptors rather
than processes: root's legitimate workload routinely holds more open files
than an ordinary account's, so a shared ceiling would either constrain
root's own work or, set high enough to avoid that, defeat the point of
`PAM-12`'s protection for every other account.
**Verified:** the template sets `root  hard  nofile  {{
pam_limits_nofile_root }}`; the defaults file defines
`pam_limits_nofile_root: 8192` (`test_defaults_define_limits_nofile_root`).
`test_limits_template_has_separate_root_nofile` asserts both
`pam_limits_nofile_root` and `pam_limits_nofile` appear in the rendered
template, the same presence-not-placement limitation `PAM-11` records. No
test substitutes a value or confirms root is actually capped at it.

### PAM-14 — Core dumps disabled, hardcoded

THE Bootstrap SHALL disable core dumps for every PAM-authenticated session
by hardcoding the `core` limit to 0, not exposed as a configurable
variable.

**Why:** a core dump captures a process's full memory image at the moment
it crashes, which routinely includes credentials, private keys, and other
secrets a process was holding at the time — a core dump left on disk is a
plaintext copy of exactly the material this bootstrap otherwise takes care
to keep out of the repository, logs, and process argument lists (`INV-5`).
Disabling it outright, rather than exposing a variable an inventory could
raise, treats "no core dumps" as this bootstrap's security policy rather
than a tunable a deployment might reasonably want to relax.
**Verified:** the template sets `*  hard  core  0` unconditionally.
`test_limits_template_hardcodes_core_zero` scans the rendered file line by
line for the first uncommented line containing `core` and asserts it also
contains `0`; the parametrized `test_limits_template_contains_all_limit_types`
separately asserts the substring `core` appears in the template. No test
confirms a crashing process on a live host actually produces no core file.

### PAM-15 — Every resource limit is a hard limit, never a soft one

THE Bootstrap SHALL express every directive in the resource limits template
as a hard limit, with no soft limit among them.

**Why:** a soft limit is only a session's starting point — anything short
of the hard ceiling, a process may raise for itself with `ulimit`, up to
that ceiling. Setting a soft limit here instead of, or alongside, the hard
one would let an ordinary process opt back out of the very restriction
`PAM-10` through `PAM-14` exist to impose, leaving the hard ceiling as the
only line this spec actually controls.
**Verified:** `test_limits_template_uses_hard_limits_only` scans every
non-empty, non-comment line in the rendered template and asserts each one
contains the substring `hard` and none contains `soft`. This is a
whole-line, whole-file property rather than one tied to any single
directive, and is falsified by a single non-comment line failing either
check.

### PAM-16 — Resource limits deployed from a template

THE Bootstrap SHALL deploy `/etc/security/limits.d/50-hardening.conf` from
a template.

**Why:** the same rationale as `PAM-1`: one file, rendered from one
template, is reviewed and changed in one place rather than hand-edited
per-host.
**Verified:** the task "Deploy resource limits" renders
`50-hardening.conf.j2` to `/etc/security/limits.d/50-hardening.conf`, mode
`0644` (`test_tasks_deploy_resource_limits`). No test confirms the
rendered file is actually the one a live PAM session's limits are drawn
from.

### PAM-17 — Failure counter reset on successful authentication

THE Bootstrap SHALL reset an account's accumulated failure count when it
authenticates successfully, via the `faillock-authfail` profile's
`Account` section.

**Why:** `PAM-7` stops guessing past the configured threshold, but says
nothing about what happens to failures that came before a later success;
without a reset, those failures would linger indefinitely, so an account
that mistyped a password twice last week and authenticates correctly
today would still be two failures closer to `PAM-2`'s limit than an
account with a clean history, for no reason connected to any ongoing
attack. Resetting the count on success is what makes `PAM-2`'s `deny`
describe a burst of consecutive failures, not a lifetime tally interrupted
only by the lockouts it eventually causes.
**Verified:** `faillock-authfail-pam-config.j2` sets `Account-Type:
Additional` with a `pam_faillock.so` `Account:` line.
`test_authfail_profile_has_account_section` asserts both substrings
against the template file directly. The task "Deploy faillock authfail PAM
profile" renders this same file to
`/usr/share/pam-configs/faillock-authfail`
(`test_tasks_deploy_faillock_pam_profiles`), which is also `PAM-7`'s
deployment evidence, since both requirements are realised by one profile.
No test confirms a subsequent successful login actually clears a
previously-accumulated failure count.
