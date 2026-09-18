# Filesystem Hardening — Requirements

**Prefix:** `FS`

## Purpose

This spec covers turning `/tmp`, `/var/tmp` and `/dev/shm` from ordinary
world-writable directories into directories a payload can be written to but
not executed from: mounting each with `noexec`, `nosuid` and `nodev`,
delivered as systemd mount units and drop-in overrides rather than
`/etc/fstab` entries, and made to take effect within the same run wherever
the role is able to arrange that. Unlike `NET` and `HOST`, this capability
has no enabling variable and no defaults file at all — it always applies,
identically, to every host in the fleet.

## Scope

### In scope

- Mounting `/tmp` with `noexec`, `nosuid` and `nodev`, whichever of the two
  candidate unit strategies (a drop-in override on an existing `tmp.mount`
  unit, or a full bind-mount unit) applies on a given host.
- Mounting `/var/tmp` with `noexec`, `nosuid` and `nodev`, bind-mounted onto
  `/tmp`.
- Mounting `/dev/shm` with `noexec`, `nosuid` and `nodev` via a drop-in
  override on its base unit.
- Delivering all three as systemd mount units and drop-in overrides rather
  than `/etc/fstab` entries.
- Reloading systemd and remounting `/tmp` and `/dev/shm` within the same run
  when their configuration changes.
- Enabling and starting the `/tmp` and `/var/tmp` mount units.
- Whether a changed mount configuration takes effect immediately or needs a
  later reboot or restart, and whether the operator is told which.

### Out of scope

- Hardening any directory other than `/tmp`, `/var/tmp` and `/dev/shm`.
- Independent, post-bootstrap confirmation that the live mounts actually
  carry these options, owned by `VRFY`.
- Where this capability sits relative to the rest of the run, owned by
  `PRJ-12`.
- The package-manager-driven reboot notice for a new kernel or library,
  owned by `PRJ-10` — a stale `/var/tmp` mount is a different reason to
  restart than the one that notice watches for.

## Security invariants

**Upholds:** INV-9
**Allowances claimed:** none

INV-9 is upheld by `FS-1` through `FS-3`, together with `FS-5`'s immediate
remount: each mount's options are deployed declaratively from a template
that renders the same content on every run, enabling and starting a mount
unit only ever adds active/enabled state and never removes it, and a
remount re-asserts the same three options every time it fires — so no
re-run can leave any of the three mounts more permissive than an earlier
run left it.

## Requirements

### FS-1 — /tmp mounted with noexec, nosuid, nodev

THE Bootstrap SHALL mount `/tmp` with the `noexec`, `nosuid` and `nodev`
options, whether by a drop-in override on an existing `tmp.mount` unit or by
a full bind-mount unit when no `tmp.mount` unit exists.

**Why:** `/tmp` is world-writable, and it does not matter how a payload gets
there — an upload handler, a mail attachment, a compromised service
unpacking an archive — an unprivileged process can always write to it.
Without `noexec`, `nosuid` and `nodev`, that same process can also execute
what it wrote, run it setuid to gain a privilege it should not have, or use
it to reach a device node — the standard staging ground that turns "a file
landed in a writable directory" into "arbitrary code ran," with nothing
about the write step itself indicating that an execution followed.
**Verified:** both candidate `/tmp` unit templates — the drop-in override,
used when a `tmp.mount` unit already exists, and the full bind-mount unit,
used when it does not — set `noexec`, `nosuid` and `nodev` in their
`Options=` line; a task selects between them based on whether a `tmp.mount`
unit is already present. The property suite asserts all three options, plus
the bind-mount details, on the full bind-mount unit template; the drop-in
override template carries the same options but is not exercised by the
property suite.

### FS-2 — /var/tmp mounted with noexec, nosuid, nodev

THE Bootstrap SHALL mount `/var/tmp` with the `noexec`, `nosuid` and `nodev`
options, bind-mounted onto `/tmp`.

**Why:** `/var/tmp` is, like `/tmp`, world-writable and meant for temporary
files. Leaving it on its default options would hand an attacker a second
staging ground, identical in effect to `/tmp`, that writes-then-executes a
payload just as readily — quietly undoing what `FS-1` closed by simply
using a different directory.
**Verified:** the `/var/tmp` mount unit binds `/tmp` onto `/var/tmp` and
sets `noexec`, `nosuid` and `nodev` in its `Options=` line, ordered after
and requiring `tmp.mount`; the property suite asserts the bind source and
destination, each required option, and the ordering.

### FS-3 — /dev/shm mounted with noexec, nosuid, nodev

THE Bootstrap SHALL mount `/dev/shm` with the `noexec`, `nosuid` and
`nodev` options via a drop-in override on its base unit.

**Why:** `/dev/shm` backs POSIX shared memory and is world-writable tmpfs
by default — exactly as exploitable a write-then-execute staging ground as
`/tmp`. Being memory-backed rather than disk-backed also means a payload
run from it leaves nothing on disk once the process exits, so an incident
responder looking for how an intrusion started would find no file at all,
only a gap, if this mount permitted execution.
**Verified:** the drop-in override's `Options=` line names `noexec`,
`nosuid` and `nodev`, replacing the base unit's own `Options=` line in
full; the property suite asserts each required option is present and that
the drop-in carries no `[Unit]` or `[Install]` section of its own.

### FS-4 — Delivered as systemd mount units and drop-ins, not /etc/fstab

THE Bootstrap SHALL implement `FS-1` through `FS-3` as systemd mount units
and drop-in overrides, never as `/etc/fstab` entries.

**Why:** `/etc/fstab` is only consulted by the kernel's mount tooling at
boot (or an explicit `mount -a`); a hardening control that lived there
alone would leave the actively running filesystem exactly as unprotected as
before, between the moment this play finishes and the host's next reboot —
potentially the mount's entire useful life on a VPS provisioned once and
left running for months, with nothing about a successful `fstab` edit
indicating that the live mount never changed.
**Verified:** all three destinations this role writes to are systemd unit
or drop-in paths under `/etc/systemd/system/`, deployed with the template
module and activated with the systemd module; no task in the role writes to
`/etc/fstab`.

### FS-5 — /tmp and /dev/shm hardening takes effect without waiting for a reboot

WHEN the `/tmp` drop-in override or the `/dev/shm` drop-in override
changes, THE Bootstrap SHALL remount the corresponding filesystem with
`noexec`, `nosuid` and `nodev` in the same run.

**Why:** Templating a new `Options=` line only changes what systemd will
apply the next time it assembles the mount — normally at boot. Without an
immediate remount, a run that reports the drop-in as changed would leave
the live, already-mounted `/tmp` or `/dev/shm` exactly as exploitable as
before, with the play reporting success as though the very
write-then-execute attack `FS-1` and `FS-3` exist to close were already
closed.
**Verified:** the two remount tasks are conditioned on their corresponding
deploy task's registered `changed` result and run `mount -o
remount,noexec,nosuid,nodev` — the exact three options this spec requires —
immediately once a changed drop-in is deployed, independent of the unit
file's other, non-security options.

### FS-6 — Operator told when a changed mount unit needs a restart or reboot

THE Bootstrap SHALL tell the operator when a hardened mountpoint's
already-active unit needs a manual restart or a reboot before a changed
configuration takes effect.

**Why:** A full bind-mount unit — used for `/var/tmp` always, and for
`/tmp` whenever no `tmp.mount` unit already exists — that is already active
is not remounted or restarted by this role when its definition changes:
enabling and starting an already-started unit is a no-op. A re-run would
report success while the live mount keeps whatever options it already had,
so a host whose `/var/tmp` mount, or a `/tmp` mounted this way, was ever
weaker than this role now templates it keeps permitting exactly the
write-then-execute attack `FS-1` and `FS-2` exist to close, with nothing in
the run's output telling the operator that only a restart or a reboot — not
the completed play — will close it.
**Traceability:** pending — no task compares `var-tmp.mount`'s (or, when
the bind-mount strategy applies, `tmp.mount`'s) active options against its
deployed unit file, no restart is triggered for either, and no message
distinguishes this case from a mountpoint whose remount already ran; the
operator can only learn that a restart or reboot is still needed by reading
this spec or the role's source.
