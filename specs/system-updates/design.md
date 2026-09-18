# System Updates — Design

## Approach

The role is a single tasks file run in three steps: refresh the package
index, apply the upgrade together with cleanup, then check for and report a
pending reboot. All three steps use `ansible.builtin.apt`, `ansible.builtin.stat`
and `ansible.builtin.command` directly — there is no custom script and no
handler, because every step is a single declarative module call.

## Implementation map

| Path | Realises |
|---|---|
| `roles/system_updates/tasks/main.yml` | UPD-1, UPD-2, UPD-3, UPD-4, UPD-5, UPD-6 |
| `roles/system_updates/defaults/main.yml` | UPD-1, UPD-2, UPD-3, UPD-4 |

## Key decisions

**`dist` is the default upgrade type for Debian stable.** apt's `safe`
strategy (the module's `yes` is an alias for it) will not install or remove a
package to satisfy a changed dependency, which means it silently defers
exactly the upgrades most likely to matter for security — a kernel ABI bump or
a library split into a new package. `dist` (a synonym of `full` in the
`ansible.builtin.apt` module) resolves those dependency changes instead of
skipping them, which is the behaviour a Debian stable host needs from an
unattended run that has no one available to approve a dependency change by
hand.

**Autoremove and autoclean run as part of the same upgrade task, not as
separate steps.** Both parameters are keywords of the same `apt` module call
that performs the upgrade, so orphaned packages and stale package files are
cleared in the same idempotent action that created them, rather than in a
separate task that could be skipped, reordered, or left to drift out of sync
with the upgrade it is meant to follow.

**The reboot check happens in this role, immediately, with package-level
detail.** `PRJ-10` also checks the same reboot-required marker at the very end
of the whole run, but only as a plain warning — it has no record of which
packages caused it, because by then several other roles have run. This role's
own check runs right after the upgrade that would have created the marker, so
it can still read `/var/run/reboot-required.pkgs` and name the packages
responsible while that information is still current.

## Failure modes

- **The upgrade task fails partway** (a held package, a network interruption,
  a mirror timeout). `apt`/`dpkg` transactions are not left half-applied at the
  package level, so `PRJ-13` covers the rest: the run is fixed and re-run
  rather than rolled back.
- **A reboot is required and never taken.** The notification fires and the
  run continues; nothing in this role or in `PRJ-10` forces the operator to
  act on it.
- **The reboot-required marker exists but its packages file does not.** The
  notification task falls back to a fixed placeholder string rather than
  failing, so the operator still learns a reboot is needed even without the
  package-level detail.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task here runs with root privilege; none of `apt`,
  `stat` or reading `/var/run/reboot-required.pkgs` would succeed otherwise.
- `PRJ-12` — this role is placed first in the fixed order, so the packages
  every later capability configures are already at the versions this role
  leaves behind.

**What others may assume of this spec:**

- `PRJ-10` — the reboot-required marker this role's upgrade may create is
  still present, unconsumed, for the run's own end-of-run check to read.
