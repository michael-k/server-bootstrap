# System Updates — Requirements

**Prefix:** `UPD`

## Purpose

This spec covers keeping the target host's installed packages current during
the bootstrap run: refreshing the package index, applying the available
upgrades, clearing the debris an upgrade leaves behind, and telling the
operator when a reboot is needed before those upgrades actually take effect.
`PRJ-12` places this capability first in the run precisely because every other
spec assumes the host it configures already carries current security patches;
this is the spec that makes that assumption true.

## Scope

### In scope

- Refreshing the package index, and how long a previous refresh remains valid.
- Applying available package upgrades, and which upgrade strategy is used.
- Removing packages an upgrade leaves with no remaining dependents.
- Removing package files an upgrade leaves behind that can no longer be
  fetched.
- The package refresh's behaviour in check mode.
- Detecting that installed upgrades require a reboot, and how that is
  surfaced.

### Out of scope

- Actually rebooting the host, which this spec deliberately never does.
- Where this capability sits relative to the rest of the run, and why package
  updates come first — owned by `PRJ-12`.
- The reboot notice printed once at the very end of the whole run — owned by
  `PRJ-10`.
- Installing specific packages a particular capability depends on (for
  example a firewall or intrusion-prevention daemon), which is owned by that
  capability's own spec.

## Security invariants

**Upholds:** INV-9
**Allowances claimed:** none

INV-9 is upheld by `UPD-2` through `UPD-5`: each acts through a declarative
`apt` parameter that converges toward the target package state — installing
what is missing, removing what has no remaining dependents, clearing what can
no longer be fetched — rather than reapplying an action unconditionally on
every run, and `UPD-5` additionally guarantees the package-index refresh
itself reports no change once the host has already converged.

## Requirements

### UPD-1 — Bounded package index refresh

THE Bootstrap SHALL refresh the target host's package index using a cache
validity bounded by `apt_update_cache_valid_time`.

**Why:** An index refreshed unconditionally on every run adds a network round
trip to the package mirror on every idempotent re-run, including ones that
change nothing else. An index that is never refreshed does not fail loudly
either: the upgrade step below would keep consulting a package list that grows
more stale with every run, silently missing security fixes published since the
last refresh while reporting success every time.
**Verified:** the package-index task's `cache_valid_time` parameter is wired
to `apt_update_cache_valid_time` instead of a literal, and the property suite
asserts the configured default lies within a reasonable multi-minute-to-hours
band rather than being pinned to a single value.

### UPD-2 — Upgrade with a configured strategy, defaulting to full dependency resolution

THE Bootstrap SHALL apply the target host's available package upgrades using
the strategy configured in `apt_upgrade_type`, defaulting to `dist`.

**Why:** apt's conservative upgrade strategy silently declines any update that
would need to install or remove a package to satisfy a changed dependency —
exactly the case a kernel or library security fix on Debian stable often is.
A host using that strategy would keep reporting a clean upgrade while carrying
an unpatched package, with nothing in the run's output pointing at the gap.
**Verified:** the upgrade task's `upgrade` parameter is wired to
`apt_upgrade_type` instead of a literal, and the property suite asserts the
configured default is `dist`.

### UPD-3 — Configurable removal of orphaned dependencies

THE Bootstrap SHALL make the removal of packages the upgrade leaves with no
remaining dependents configurable through `apt_autoremove`.

**Why:** A package pulled in only as another package's dependency does not
stop being installed once that other package is upgraded away from needing
it. Left alone indefinitely, such orphans accumulate on a host that is never
rebuilt from scratch, consuming disk and standing as installed software that
nothing in the inventory declares or accounts for.
**Verified:** the upgrade task's `autoremove` parameter is wired to
`apt_autoremove` instead of a literal, and the property suite asserts the
variable defaults to enabled.

### UPD-4 — Configurable cleanup of unfetchable package files

THE Bootstrap SHALL make the removal of downloaded package files that can no
longer be fetched configurable through `apt_autoclean`.

**Why:** The local package-file cache grows without bound across repeated
runs otherwise, and on a small VPS's disk this is not merely cosmetic: an apt
operation that cannot write to a full disk fails in a way that looks like a
network or repository problem rather than the exhausted storage that actually
caused it.
**Verified:** the upgrade task's `autoclean` parameter is wired to
`apt_autoclean` instead of a literal, and the property suite asserts the
variable defaults to enabled.

### UPD-5 — Clean check mode for the package index refresh

THE Bootstrap SHALL NOT report the package index refresh as a change in check
mode.

**Why:** Ansible's `apt` module reports the index refresh as changed in check
mode unconditionally, even when the configured cache validity means a real run
would skip it entirely. Left unmarked, this task would report a change on
every check-mode run against an already-converged host, burying the one real
change a reviewer is looking for underneath permanent noise from a task that
never touches an installed package.
**Verified:** the refresh task declares `changed_when: false`, and the
integration suite's check-mode run against a bootstrapped host lists which
tasks reported changed when the recap is not clean.

### UPD-6 — Reboot is surfaced, never performed

THE Bootstrap SHALL notify the operator, once an upgrade has installed
packages that require it, that a reboot is needed, without rebooting the host
itself.

**Why:** Rebooting automatically would drop the very SSH connection the run
uses to configure everything that comes after package updates, aborting the
run partway through the machine state the rest of this spec tree assumes is
complete. Never mentioning it at all would leave the host running a superseded
— potentially vulnerable — kernel or library with nothing telling the operator
that a fix is one restart away.
**Verified:** a reboot-required marker check runs immediately after the
upgrade, and a notification naming the packages that require it fires only
when that marker is present; no task in the role invokes a reboot.
