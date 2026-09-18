# Sudo Hardening — Design

## Approach

Like `USR`, this spec owns a scattered subset of one flat task file shared
with three other specs — seven tasks, interleaved with `USR`'s account
creation and `LOGIN`/`PAM`'s hardening further down the same file — plus
the template that renders this spec's one shared defaults file.

The seven tasks fall into three groups. First, `sudo` is installed
(`SUDO-1`), a precondition for everything that follows and the only task
of this spec's that runs before either account exists. Second, once each
account exists (`USR`'s work), it is granted sudo through its own
`sudoers.d` file: password-required for the manual account (`SUDO-2`),
passwordless for the automation account (`SUDO-3`). These two tasks sit
physically beside the account-creation tasks they depend on, rather than
grouped together, because each grant is part of finishing that one
account's setup. Third, a block of four tasks that runs after `USR`'s SSH
access group tasks handles what is shared rather than per-account: the
`wheel` group and the manual account's membership in it (`SUDO-11`,
`SUDO-12`), the shared sudo defaults file (`SUDO-4`, which fans out to
`SUDO-5` through `SUDO-10` inside the template it deploys), and the
`pam_wheel` restriction on `su` (`SUDO-13`).

The defaults file itself is one Jinja template rendered to a single
`sudoers.d` drop-in, `00-sudo-security`, so every directive it sets is
reviewed and changed in one place and applied identically to every
bootstrapped host.

## Implementation map

| Path | Realises |
|---|---|
| `roles/users/tasks/main.yml` | SUDO-1, SUDO-2, SUDO-3, SUDO-4, SUDO-11, SUDO-12, SUDO-13 |
| `roles/users/templates/00-sudo-security.j2` | SUDO-5, SUDO-6, SUDO-7, SUDO-8, SUDO-9, SUDO-10 |
| `roles/users/defaults/main.yml` | SUDO-7 |
| `tests/unit/test_users.py` | SUDO-2, SUDO-3 |
| `tests/property/test_user_properties.py` | SUDO-2, SUDO-3 |
| `tests/property/test_sudo_hardening_properties.py` | SUDO-4, SUDO-5, SUDO-6, SUDO-7, SUDO-8, SUDO-9, SUDO-10, SUDO-11, SUDO-13 |

`roles/users/tasks/main.yml` also carries `USR`'s, `LOGIN`'s and `PAM`'s
tasks; `tests/unit/test_users.py` and `tests/property/test_user_properties.py`
also carry `USR`'s tests. This spec's citations name only the tasks and
tests listed above; the rest belong to those specs.

No requirement here has an `## Implementation map` row with no test: rows
are listed by file, and a file can appear in the map while individual
requirements it realises (`SUDO-1`, `SUDO-12`) have no test coverage —
recorded under Failure modes, not hidden by omitting the file.

## Key decisions

**Per-user `sudoers.d` files over a shared group entry.** Both grants could
instead have been one line each in a shared file, or a single sudoers rule
naming a group both accounts belong to. Per-user files were chosen because
they keep each account's privilege legible and independently revocable:
deleting `/etc/sudoers.d/ansible` removes exactly one account's access and
touches nothing else, where a shared file or group rule would require
editing a line inside a document that also states another account's
privileges, with the ordinary risks of a hand-edit to a file `visudo`
happens to still accept. It also lets the two grants differ in the one way
they need to — the automation account's `NOPASSWD` — without a conditional
inside a single template deciding which principal gets which behaviour.
The cost is that adding an account's sudo grant is now a task of its own
rather than a line change to an existing one, which is USR's and this
spec's shared assumption throughout: an account this bootstrap creates
gets exactly the escalation this spec grants it by name, never blanket
membership in something else already grants.

**`wheel` for `su`, while sudo uses per-user files.** `su` and `sudo` are
restricted by genuinely different mechanisms — PAM for one, sudoers for
the other — and `pam_wheel` has no equivalent to a per-user drop-in file;
its only unit of restriction is a single named group. Given that, `wheel`
is the natural fit for `su` specifically, and using it does not create the
same shared-entry problem per-user sudoers files were chosen to avoid,
because `su`'s only property that matters here is binary: is the caller a
member or not. There is nothing for `su` to grant differently per
account the way `sudo`'s password requirement differs between the two
accounts, so a single group with a fixed membership (`SUDO-12`) is not a
compromise the way a shared sudoers entry would have been — it is the
correct-shaped mechanism for a binary decision.

**The automation account joins neither `wheel` nor gets a password.** Both
choices follow from the same fact: the account has exactly one legitimate
way to escalate, sudo, and it already has that. Adding it to `wheel` would
open a second path — `su` — that nothing exercises and nothing needs, for
no benefit; requiring a sudo password would ask an unattended SSH session
for an interactive answer nothing is present to give. Both omissions are
symmetric with what the manual account gets: `wheel` membership and a
sudo password it is expected to supply, because that account's escalation
is, by design, an interactive one.

**`requiretty` is global; the exemption is per-account, not per-mechanism.**
An alternative would have been to leave `requiretty` off entirely and rely
on `NOPASSWD` plus a restrictive `sudoers.d` file to keep the automation
account's non-interactive sudo safe. `requiretty` was kept globally instead
because it closes a path neither of the per-user files addresses on its
own: an interactive account's credentials reused from a context with no
terminal at all, such as a cron job running as the manual account with a
cached or otherwise-supplied credential. Scoping the exemption to
`deploy_user_name` specifically, rather than dropping `requiretty`
altogether, keeps that path closed for every account except the one that
has a documented reason to need it.

## Failure modes

- **`SUDO-1` has no test coverage of any kind.** Neither suite references
  the package-installation task; a regression that removed it would pass
  every test in both suites and only surface on a base image that did not
  already ship `sudo`, at the first task that tries to use it.
- **`SUDO-12`'s membership task has no test coverage of any kind.** Neither
  suite references the manual account's addition to `wheel`. The
  integration suite's only assertion in this area is that the automation
  account, which is *not* a member, is refused by `su` — evidence for the
  restriction (`SUDO-13`) working, not evidence that the manual account is
  actually let through. A regression that dropped this one task would
  leave the manual account locked out of `su` at exactly the moment
  `INV-3`/`INV-6` make it the operator's only recourse, and nothing in
  this project's test suite would catch it.
- **The property suite's substring checks are file-wide, not task-scoped.**
  Every assertion in `tests/property/test_sudo_hardening_properties.py`
  searches the whole rendered template or the whole tasks file for a
  substring, the same shape of weakness recorded in the user-accounts
  design's failure modes. A directive moved to the wrong task, or a
  `visudo` validation moved off the task that needs it and onto an
  unrelated one, would not be caught by any of these tests.
- **`test_no_logfile_directive` proves an absence, not a property.** It
  guards the decision recorded under `SUDO-8` not to add a separate
  `logfile` directive; it is not evidence that syslog/journald logging
  itself works, and a template that logged nowhere at all would pass it
  just as cleanly as the current one does.
- **No test confirms a `wheel` member can actually use `su`, or that a
  password-authenticated sudo session actually prompts for one.** Every
  assertion in this spec's scope checks a task's parameters or a rendered
  file's content, never an authenticator's behaviour. The integration
  suite's `su`-related test checks only the negative case (a non-member is
  refused); nothing checks the positive one.
- **The manual account's password requirement is only as strong as
  `USR-3`'s.** `SUDO-2` requires a password for sudo, but whether that
  password is a working hash rather than an unusable literal string is
  entirely `USR-3`'s concern, recorded in the user-accounts design's own
  failure modes. This spec's requirement is satisfied by the sudoers file
  saying `ALL=(ALL:ALL) ALL` regardless of whether the account behind it
  can actually authenticate.

## Interactions

**What this spec assumes of others:**

- `USR` — both accounts exist, with the uids and names `USR` fixes, before
  either sudo grant is written; the manual account's supplementary groups
  are appended rather than replaced, so this spec's `wheel` membership
  (`SUDO-12`) is not undone by a re-run of the account tasks.
- `PRJ-2` — every task here writes to `/etc/sudoers.d/` or `/etc/pam.d/`,
  which needs root.
- `INV-3`, `INV-6` — root has no remote login path and every narrowing
  mechanism is console-recoverable, which is what makes the manual
  account's sudo and `su` access the operator's actual recourse rather
  than a redundant path alongside a root login that no longer exists.

**What others may assume of this spec:**

- `LOGIN` and `PAM` — this spec's tasks in `roles/users/tasks/main.yml` sit
  before theirs in file order, but neither spec's tasks depend on this
  one's having run first; the shared ordering is incidental to the file,
  not a dependency either spec relies on.
- `VRFY` — post-bootstrap verification and the integration suite may rely
  on both accounts having exactly the sudo access this spec grants, and on
  `su` refusing an account outside `wheel`, when independently confirming
  the host's escalation surface.
- `PRJ` — a purpose repository built on this bootstrap may rely on the
  automation account's passwordless sudo to run its own privileged
  automation without supplying an interactive credential, and on the
  manual account's sudo requiring a password as the interactive fallback
  `INV-3`'s absence of remote root makes load-bearing.
