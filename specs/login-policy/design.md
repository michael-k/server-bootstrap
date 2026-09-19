# Login Policy Hardening — Design

## Approach

Like `SUDO`, this spec owns a small, contiguous subset of one flat task
file shared with three other specs: four tasks under a
`# Login Policy Hardening` block in `roles/users/tasks/main.yml`, sitting
between `SUDO`'s block and `PAM`'s. Three of the four tasks render a
template — `login.defs.j2`, `securetty.j2`, `shell-timeout.sh.j2` — and
those templates are where this spec's real content lives; the fourth,
`pam_securetty`, is a single `lineinfile` edit to an existing PAM file.

None of the four tasks carries a `notify:`. That is deliberate, not an
oversight this spec is recording as a gap: `/etc/login.defs` and
`/etc/securetty` are read fresh by `/bin/login` on each invocation, the
`/etc/pam.d/login` edit is read fresh by PAM on each authentication, and
`/etc/profile.d/shell-timeout.sh` is sourced fresh by each new login
shell. Nothing here is consulted by a long-running daemon that would need
restarting or reloading for a change to take effect; the next login,
console session, or new shell simply sees the new file.

Deploying all three templates changes what is `changed`-reported on a
run, since Ansible's `template` module compares rendered content and each
now differs from its pre-citation state by a handful of `#`-comment lines.
That is a rendered-output change to three destination files
(`/etc/login.defs`, `/etc/securetty`,
`/etc/profile.d/shell-timeout.sh`) and, per the paragraph above, none of
it triggers a restart or reload — the comment lines land in files whose
consumers already re-read them on every use.

## Implementation map

| Path | Realises |
|---|---|
| `roles/users/tasks/main.yml` | LOGIN-1, LOGIN-3, LOGIN-4, LOGIN-5, LOGIN-6 |
| `roles/users/templates/login.defs.j2` | LOGIN-1, LOGIN-2, LOGIN-7, LOGIN-8, LOGIN-9 |
| `roles/users/templates/securetty.j2` | LOGIN-4 |
| `roles/users/templates/shell-timeout.sh.j2` | LOGIN-5, LOGIN-6 |
| `roles/users/defaults/main.yml` | LOGIN-5, LOGIN-7, LOGIN-8, LOGIN-9 |
| `tests/property/test_login_policy_properties.py` | LOGIN-1, LOGIN-2, LOGIN-3, LOGIN-4, LOGIN-5, LOGIN-6, LOGIN-7, LOGIN-8, LOGIN-9 |

`roles/users/tasks/main.yml` and `roles/users/defaults/main.yml` also
carry `USR`'s, `SUDO`'s and `PAM`'s tasks and defaults; this spec's
citations name only the four login-policy tasks and the four
`login_policy_*` defaults listed above. `roles/users/tasks/main.yml` also
still carries one deliberately-retained legacy citation, `2.4`, on the
block that creates the automation account and its SSH access, noted there
as belonging to `ssh-hardening`; it names nothing this spec covers.

## Key decisions

**`umask 027` over Debian's implicit `022`.** `022` leaves new files
group- and other-readable; `027` removes the "other" bits only, so a file
is still readable by the creating user's own group — which matters for
service accounts that share a group to exchange files — while closing the
default off from every account outside it. `007` (removing group access
too) was not chosen: `USR-8`'s supplementary-group model already uses
group membership as the intended sharing mechanism between accounts, and
`007` would defeat that by default everywhere a process left its
new-file permissions at the umask's mercy.

**The idle timeout is advisory, not enforcement.** `readonly TMOUT`
(`LOGIN-6`) stops one specific thing: a shell that has already sourced
`/etc/profile.d/shell-timeout.sh` from reassigning or unsetting `TMOUT`
with an ordinary shell statement later in the same session. It does not
stop, and this spec does not claim it stops, several other ways the
timeout never applies at all:

- `readonly` is a property of one running shell process, not of the
  variable's value once it crosses into a child's environment.
  `export TMOUT` makes a *plain* environment variable visible to child
  processes; a shell started fresh in that environment — for example
  `bash --noprofile`, or `exec` into a new shell — inherits `TMOUT=600`
  as an ordinary variable, not as one still marked `readonly`, and can
  reassign or unset it from there with no error.
- `/etc/profile.d/*.sh` is read by `/etc/profile`, which only a shell
  invoked as a *login* shell reads at all, and only if that shell is one
  of the POSIX-family shells whose `/etc/profile` sources
  `/etc/profile.d/`. A shell that is not a login shell, or a login shell
  from a different family entirely (this repository does not restrict
  `USR-7`'s configurable login shell to any particular one), never
  executes this file in the first place, and `TMOUT` is never set for it
  at all — not merely unset, never present.
- Nothing here re-asserts the timeout for a shell that outlives the
  session that first sourced it, such as one left running inside `screen`
  or `tmux` and reattached later.

Given that, the honest description of what this control is worth: it
raises the bar against a user casually turning the timeout off in the
shell they are already in, and does nothing against a user who starts a
different shell, or whose shell was never going to read the file at all.
`docs/login-policy.md` currently states the opposite — "The timeout is
read-only and cannot be disabled by users" — which this spec does not
repeat; that documentation claim is recorded as a divergence in the
project's findings rather than corrected here, since this plan changes
comments, docstrings and citations only, not documentation prose.

**`LOGIN-8`/`LOGIN-9`'s defaults are set to match SSH's, by hand, not by
a shared variable.** `login_policy_retries: 3` and
`login_policy_timeout: 30` were chosen to equal `ssh_max_auth_tries` and
`ssh_login_grace_time` (`roles/ssh_hardening/defaults/main.yml`) so the
console and network login paths present the same attempt and time budget.
The two pairs of variables are otherwise unconnected: nothing computes
one from the other, and nothing checks at run time or in either test
suite that they still agree. Changing one default without the other
would silently leave the console and network paths mismatched, and
nothing in this project would report it.

**`/etc/securetty` lists both virtual and serial console TTYs, and
excludes pseudo-terminals on purpose.** The two lists together are what
let this bootstrap's threat model treat "the console" as one thing
regardless of whether a given host's out-of-band access happens to be a
KVM-style virtual console or a serial one — both are treated as
equally trusted, physical-access-equivalent paths. The property that
actually does the security work, per this spec's `## Security invariants`
section, is not which specific TTYs are named but that no `pts/` device
is: that is what keeps a network-terminated session from ever presenting
a tty this file accepts.

## Failure modes

- **`LOGIN-7`, `LOGIN-8`, and `LOGIN-9`'s shared property test is
  file-wide, not same-line.** `test_login_defs_has_hardened_settings`
  checks that a setting name (e.g. `UMASK`) and its variable name (e.g.
  `login_policy_umask`) each appear somewhere in the rendered template,
  independently. A regression that hardcoded a value on the directive
  line while leaving the variable name orphaned in an unrelated comment
  would still pass. This is the same class of weakness recorded in the
  `sudo-hardening` and `user-accounts` designs' own failure modes, in the
  same role.
- **`LOGIN-1`'s preservation tests prove three lines survived, not that
  nothing else changed.** `test_login_defs_preserves_uid_ranges`,
  `test_login_defs_preserves_encrypt_method`, and
  `test_login_defs_preserves_home_mode` each check one specific directive
  against Debian's shipped value. None of them, individually or together,
  confirms the template's other, untested directives (`MAIL_DIR`,
  `PASS_MAX_DAYS`, `TTYPERM`, and the rest) still match Debian's defaults;
  a change to any of those would pass every test in this suite.
- **No test exercises an actual login, at the console or otherwise.**
  Every assertion in `tests/property/test_login_policy_properties.py`
  reads a task file or a rendered template as text. Nothing starts
  `/bin/login`, nothing authenticates against `/etc/pam.d/login`, and
  nothing confirms `pam_securetty` (`LOGIN-3`) actually consults
  `/etc/securetty` (`LOGIN-4`) rather than the two simply coexisting on
  disk unconnected. The integration suite is the only place any of this
  role's behaviour runs against a live host, and it is outside this
  spec's Modify list.
- **Whether the idle timeout ever applies to a given account is entirely
  outside this spec's control.** As `## Key decisions` describes, the
  mechanism depends on the account's login shell being one that reads
  `/etc/profile.d/` as a login shell — a fact `USR-7` decides, not this
  spec — and no test in either suite creates a shell session of any kind
  to check that it does.
- **`pam_securetty` and `/etc/securetty` restrict root only.** By design
  (and stated in `docs/login-policy.md`), the manual account created by
  `USR` is not subject to either mechanism and may log in on any tty; this
  is not a gap in this spec's requirements, but a reader should not infer
  from `LOGIN-4` that any account's console access is restricted, only
  root's.

## Interactions

**What this spec assumes of others:**

- `USR` — both accounts already exist, with the login shell `USR-7`
  assigns, before any task here runs; whether that shell ever sources
  `/etc/profile.d/shell-timeout.sh` (`LOGIN-5`, `LOGIN-6`) is a property
  of that choice, not of anything this spec controls.
- `SSH` and `INV-3`, `INV-6` — sshd's own `PermitRootLogin no` is the
  first, primary barrier against remote root login; this spec's
  `pam_securetty`/`securetty` pair (`LOGIN-3`, `LOGIN-4`) is the fallback
  that holds if that barrier is ever bypassed, and both remain
  console-recoverable.

**What others may assume of this spec:**

- `PAM` — `LOGIN_RETRIES` and `LOGIN_TIMEOUT` (`LOGIN-8`, `LOGIN-9`) are
  `/bin/login`'s own console-prompt attempt and time budget, entirely
  separate from `pam_faillock`'s cross-service failed-authentication
  counter; `PAM`'s spec should not assume this one enforces, feeds, or
  otherwise interacts with its own lockout mechanism.
- `SSH` — this spec's `LOGIN-8`/`LOGIN-9` defaults are set to match SSH's
  `MaxAuthTries`/`LoginGraceTime` by design, but nothing here depends on
  SSH's values or checks them; `SSH`'s spec should not assume a change to
  its own defaults is reflected here, or vice versa.
- `VRFY` — post-bootstrap verification and the integration suite may rely
  on `/etc/login.defs`, `/etc/securetty` and
  `/etc/profile.d/shell-timeout.sh` matching this spec's settings exactly
  when independently confirming login hardening on a live host.
