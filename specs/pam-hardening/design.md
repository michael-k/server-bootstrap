# PAM Hardening — Design

## Approach

Like `LOGIN`, this spec owns a contiguous block at the end of the same flat
task file three other specs share: five tasks under a `# PAM Hardening`
header in `roles/users/tasks/main.yml`, sitting after `LOGIN`'s block. Four
of the five tasks render a template — `faillock.conf.j2`,
`faillock-preauth-pam-config.j2`, `faillock-authfail-pam-config.j2`,
`50-hardening.conf.j2` — and the fifth removes the file the first two
templates' predecessor used to occupy.

Three of the five tasks — the two PAM-profile deployments and the removal —
carry `notify: Rebuild PAM common-auth`. That handler runs
`pam-auth-update --enable faillock-preauth faillock-authfail` unconditionally
whenever any of the three fires, which is the only thing that turns
`/usr/share/pam-configs/*` source files into the actual
`/etc/pam.d/common-auth` stack an authentication attempt walks.

The two PAM-profile templates render into `/usr/share/pam-configs/`, a
Deb822-like format `pam-auth-update` parses with no comment syntax of its
own — every line is a recognized field name or an indented continuation.
Both templates carry the `notify` above, so any change to their rendered
content — a stray added line included — makes the deploying task report
`changed` and fires the handler that rebuilds `common-auth` for every
account on the host. For that reason this spec's citations for `PAM-6`,
`PAM-7`, and `PAM-17` live entirely in `roles/users/tasks/main.yml`, on
the tasks that deploy those two templates, not inside the templates
themselves: a YAML `#` comment there is inert to the task's
rendered-content diff, where a `#`
line added to either `.j2` file would not be. `faillock.conf.j2` and
`50-hardening.conf.j2` carry no such risk — both already carried `#`
header comments before this spec existed, both render into formats where
`#` is an ordinary comment, and neither of their deploying tasks carries a
`notify` at all — so both are annotated directly.

## Implementation map

| Path | Realises |
|---|---|
| `roles/users/tasks/main.yml` | PAM-1, PAM-6, PAM-7, PAM-8, PAM-9, PAM-16, PAM-17 |
| `roles/users/templates/faillock.conf.j2` | PAM-1, PAM-2, PAM-3, PAM-4, PAM-5 |
| `roles/users/templates/faillock-preauth-pam-config.j2` | none — a Deb822-style `pam-auth-update` source file with no comment syntax; see `## Approach`. `PAM-6` is cited from the task that deploys it instead. |
| `roles/users/templates/faillock-authfail-pam-config.j2` | none — same constraint; `PAM-7` and `PAM-17` are cited from the task that deploys it instead. |
| `roles/users/templates/50-hardening.conf.j2` | PAM-10, PAM-11, PAM-12, PAM-13, PAM-14, PAM-15, PAM-16 |
| `roles/users/handlers/main.yml` | PAM-9 |
| `roles/users/defaults/main.yml` | PAM-2, PAM-3, PAM-4, PAM-10, PAM-11, PAM-12, PAM-13 |
| `tests/property/test_pam_hardening_properties.py` | PAM-1, PAM-2, PAM-3, PAM-4, PAM-5, PAM-6, PAM-7, PAM-9, PAM-10, PAM-11, PAM-12, PAM-13, PAM-14, PAM-15, PAM-16, PAM-17 |

`roles/users/tasks/main.yml` also carries `USR`'s, `SUDO`'s and `LOGIN`'s
tasks, cited where they sit; this spec's citations name only the five PAM
tasks. `roles/users/defaults/main.yml` likewise also carries the other
three specs' defaults. `PAM-8` has no citation in the test file: neither
property test in this suite asserts the legacy-profile-removal task's
presence or its `state: absent`; it is exercised only by
`tests/verify_bootstrap.yml`, which `VRFY` owns.

## Key decisions

**Why a single profile, ordered incorrectly, silently failed to lock
accounts.** Before `ec94b3d`, this role deployed one
`pam-auth-update` profile, `/usr/share/pam-configs/faillock`, with
`Priority: 512` and a single `Auth-Type: Primary` block:

```
Auth:
  required  pam_faillock.so preauth
Auth-Final:
  [default=die]  pam_faillock.so authfail
```

`Auth:` and `Auth-Initial:` are the two field names `pam-auth-update`
recognizes for a profile's primary authentication stanza; `Auth-Final:` is
not one of them — it was invented for this file, not a real
`pam-auth-update` keyword. (`Password-Final:` *is* a real field, on the
`Password-Type` side rather than `Auth-Type`; the old template's
`Auth-Final:` reads like a false analogy from that genuinely-existing
name, applied to the wrong type of stanza.) Debian's own `pam_unix` profile
(`/usr/share/pam-configs/unix` on any Debian host) declares `Priority: 256`
for its own `Auth-Type: Primary` block. `pam-auth-update` assembles
`common-auth` by splicing every enabled profile's stanzas into the stack in
priority order, highest first — so a profile's *entire* `Auth:`/
`Auth-Initial:` content lands at the one priority its `Auth-Type: Primary`
block declares. With everything this old profile wanted to contribute
packed into one `Priority: 512` block — ahead of `pam_unix`'s 256 — the
`authfail` action had nowhere correct to land: it needs to react to
`pam_unix`'s own verdict on the password just presented, which does not
exist yet at priority 512, three-hundred-and-fifty-six priority-points
before `pam_unix` has had its turn. The result, per `ec94b3d`'s own commit
message, was that `pam_faillock`'s `authfail` behaviour ended up positioned
ahead of `pam_unix` in the assembled stack rather than behind it — the
reverse of where the module needs to sit to observe a genuine failure —
which left `sudo` unable to reach its own password prompt reliably, and
left `PAM-2`'s `deny=5` with no correctly-timed `[default=die]` action ever
enforcing it. An account could accumulate failures indefinitely and never
actually be locked out, because the one stanza responsible for denying
past the limit was never running in a position where a limit had
meaningfully been reached.

The fix splits the single profile into two, each carrying its own priority
matched to which side of `pam_unix` its job requires: `faillock-preauth`
(`PAM-6`) keeps `Priority: 512`, correctly ahead of `pam_unix`'s 256,
because checking "is this account already locked out" has to happen before
a password is even requested. `faillock-authfail` (`PAM-7`) moves to its
own profile at `Priority: 128`, correctly behind `pam_unix`'s 256, because
recording "did the attempt that just ran fail" has to happen after
`pam_unix` has produced that verdict. Splitting into two profiles, rather
than trying to give one profile two priorities, is necessary because a
`pam-auth-update` profile's `Priority:` field is one value for the whole
file — there is no way to declare a single profile whose `Auth:` content
should be spliced into two different places in the same stack.

**`even_deny_root = true` is deliberate, not a default left unexamined.**
`pam_faillock` ships with root exempted from lockout by default, and many
deployments leave that exemption in place precisely because locking out
root risks locking out the one account every other recovery mechanism
assumes will still work. This bootstrap does not have that assumption to
protect: `INV-3` already leaves root with no remote login path at all, so
root is reached only by escalating from the manual or automation account,
both of which `PAM-2` through `PAM-4` already protect with the same
lockout policy. Exempting root from that policy would only reopen the
brute-force surface `PAM-5` closes, one layer downstream, for the account
that matters the most once reached — so this bootstrap accepts the
opposite trade-off: root is locked out under the identical policy, timed
identically (`root_unlock_time` reuses `pam_faillock_unlock_time` rather
than a separate variable), never permanently.

## Failure modes

- **`even_deny_root` combined with `LOGIN-4`'s console restriction can
  leave an operator without a fast recovery path, though not a permanent
  one.** `LOGIN-4` restricts *root's* console login to a fixed TTY list;
  the manual account is not restricted by `pam_securetty`/`securetty` and
  may log in on any console tty. But the manual account's own escalation
  path is `sudo` (`SUDO-2`), which requires a password and is exactly what
  `PAM-2`–`PAM-5` protect. If the manual account itself accumulates five
  failed `sudo` password attempts — a mistyped password entered too many
  times, not necessarily an attack — `pam_faillock` locks *that account
  out of sudo* for `pam_faillock_unlock_time` (600 seconds by default),
  under the same policy `PAM-5` applies to root. During that window the
  operator retains SSH and console login as the manual account (neither is
  gated by `pam_faillock`'s account-lockout state the way `sudo`'s
  password prompt is), but cannot reach root through `sudo` or `su` until
  either the timeout elapses or something runs `faillock --user
  <manual_user_name> --reset`. The automation account offers a second path
  that does not require waiting: it authenticates over SSH by key only, is
  never subject to a `sudo` password prompt (`SUDO-3`), and can run
  `faillock --reset` non-interactively as root the moment its own Ansible
  connection reaches the host — so recovery does not strictly depend on
  the manual account's own timeout, provided the automation account's key
  and connectivity are intact. `INV-6` requires every narrowing mechanism
  to be recoverable with console access alone; this one is recoverable
  with console access alone only by waiting out the timer, and faster with
  SSH access via the automation account. No requirement in this spec and
  no test in either suite exercises this scenario end to end.
- **`PAM-6`, `PAM-7`, and `PAM-17` have no citation inside their own
  templates, by design (see `## Approach`), which means a reviewer reading
  only `faillock-preauth-pam-config.j2` or `faillock-authfail-pam-config.j2`
  in isolation finds no pointer back to this spec at all.** The citation
  lives on the task that deploys each file in
  `roles/users/tasks/main.yml`. This is a deliberate, narrower version of
  the principle that code cites specs by requirement ID, applied here to avoid a citation
  that would itself constitute the kind of change (a line in a
  `pam-auth-update` source file with no comment syntax) `PAM-9`'s handler
  would react to.
- **`PAM-9`'s test does not confirm the handler is wired to the right
  tasks, only that the string `pam-auth-update` appears somewhere in the
  combined tasks-and-handlers text.** A regression that moved the
  `notify:` line off one of the three tasks that should carry it, or
  changed the handler's command to enable the wrong profile names, would
  pass `test_tasks_enable_faillock_via_pam_auth_update` unchanged.
- **The handler's `changed_when: true` means `pam-auth-update` runs, and is
  reported as a change, on every single play where any of the three
  notifying tasks itself reports `changed` — which, absent from
  `PAM-8`'s removal task, happens on every run against a host that still
  has the legacy file present, and otherwise only when a profile's
  rendered content actually differs.** `pam-auth-update` itself is
  idempotent — re-running it with the same enabled profiles produces the
  same `common-auth`, no matter how many times it is invoked — but Ansible
  has no way to know that from the command's own exit status, since the
  module has no notion of "no-op." `changed_when: true` is the honest
  admission of that: every notified run of this handler is reported as a
  change whether or not `common-auth`'s bytes actually differ afterward,
  which is a cosmetic inaccuracy in run output, not a correctness problem,
  since re-running `pam-auth-update --enable faillock-preauth
  faillock-authfail` with those two profiles already enabled leaves the
  file exactly as it was.
- **No test in either suite runs `pam-auth-update` and inspects the
  resulting `/etc/pam.d/common-auth`.** Every assertion in
  `tests/property/test_pam_hardening_properties.py` reads a task file, a
  handler file, or a rendered template as text; none of them confirms that
  `faillock-preauth`'s stanza actually lands ahead of `pam_unix`'s in the
  real assembled stack, or that `faillock-authfail`'s actually lands
  behind it — only that each source file declares the priority that should
  produce that ordering. `tests/verify_bootstrap.yml` is the only place
  this project confirms the ordering on a live host, by `grep`-ing
  `/etc/pam.d/common-auth` for the sequence `preauth` → `pam_unix` →
  `authfail`, and that check is outside this spec's Modify list, owned by
  `VRFY`.
- **`docs/pam-hardening.md` describes the pre-`ec94b3d` single-profile
  deployment, not the current one.** It states "PAM profile:
  `/usr/share/pam-configs/faillock`" — the path `PAM-8` now removes — with
  no mention of `faillock-preauth` or `faillock-authfail`. This plan
  changes comments, docstrings and citations only, not documentation
  prose, so the divergence is recorded in the project's findings rather
  than corrected here.
- **The property suite's substring checks are file-wide, not
  same-line.** `test_faillock_conf_has_configurable_settings` and the
  resource-limit equivalents confirm a setting name and its variable name
  each appear somewhere in the rendered template, independently — the same
  class of weakness the `login-policy` and `sudo-hardening` designs record
  for their own templates. A regression that hardcoded a value on the
  directive line while leaving the variable name orphaned in an unrelated
  comment would still pass.
- **`PAM-1` and `PAM-16`'s "deployed from a template" claim is not tested
  against the file `pam_faillock`/`pam_limits` actually read at
  authentication or session-open time.** Every test in this suite checks
  what Ansible renders and where it places it, not that a live PAM stack
  consults that exact path.

## Interactions

**What this spec assumes of others:**

- `USR` — the manual and automation accounts already exist before any task
  here runs; this spec locks out whichever account authenticates through
  `common-auth`, `USR`'s accounts included, without needing to know either
  account's name.
- `SUDO` — `sudo`'s own PAM service consults `common-auth`, which is what
  makes `SUDO-2`'s password requirement subject to this spec's lockout in
  the first place; this spec assumes `SUDO` keeps requiring a password from
  the manual account, since a passwordless prompt would give
  `pam_faillock` nothing to count.
- `INV-3`, `INV-6` — root has no remote login path, and every
  access-narrowing mechanism is recoverable using console access alone (or,
  as this spec's `## Failure modes` records, using the automation
  account's own SSH access); `PAM-5`'s choice to lock root out under the
  same policy as every other account is only acceptable because both hold.

**What others may assume of this spec:**

- `LOGIN` — `LOGIN_RETRIES` and `LOGIN_TIMEOUT` (`LOGIN-8`, `LOGIN-9`) are
  `/bin/login`'s own console-prompt attempt and time budget, entirely
  separate from this spec's cross-service failure counter; this spec's
  requirements do not feed, consult, or otherwise interact with either
  `LOGIN` value, and `LOGIN`'s spec should not assume they do.
- `SSH` and the `fail2ban` spec — SSH accepts no passwords at all
  (`INV-2`), so it never presents `pam_faillock` a failed password attempt
  to count; the SSH surface's brute-force resistance is the `fail2ban`
  spec's mechanism, not this one's, and it works by an entirely different
  method (parsing connection/authentication logs and adding firewall
  rules) rather than by consulting `common-auth`. That spec is now
  written: `F2B-8` through `F2B-11` are the mechanism, and
  `specs/fail2ban/design.md`'s `## Interactions` records the reciprocal
  side of this split against `PAM-2` through `PAM-7` by ID, including the
  half this spec keeps — a source address means nothing at a console, so
  those requirements remain the only bound on password guessing there.
- `VRFY` — post-bootstrap verification and the integration suite may rely
  on `faillock.conf`, both PAM profiles, the legacy profile's absence, and
  `50-hardening.conf` matching this spec's settings exactly, including the
  ordering `tests/verify_bootstrap.yml` independently confirms in
  `/etc/pam.d/common-auth`, when confirming lockout and resource-limit
  behaviour on a live host.
