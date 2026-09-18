# Filesystem Hardening — Design

## Approach

The role is a single task file with two mutually exclusive strategies for
`/tmp` — chosen by the exit code of `systemctl cat tmp.mount` — plus one
drop-in strategy for `/dev/shm` and one full-unit strategy for `/var/tmp`.
Every unit or drop-in is deployed with `ansible.builtin.template`, and each
deploy task notifies the same `Reload systemd daemon` handler; a
`flush_handlers` meta task forces that reload to happen before the
remaining tasks enable, start or remount anything, so systemd's own view of
the units is never stale when they are queried or manipulated. `/tmp` and
`/dev/shm` are then remounted immediately whenever their respective drop-in
changed; `/var/tmp`, and `/tmp` when the bind-mount strategy applies, are
only enabled and started, which is a no-op on a host where the equivalent
unit was already active.

## Implementation map

| Path | Realises |
|---|---|
| `roles/filesystem_hardening/tasks/main.yml` | FS-1, FS-2, FS-3, FS-4, FS-5, FS-6 |
| `roles/filesystem_hardening/templates/tmp.mount.j2` | FS-1, FS-4 |
| `roles/filesystem_hardening/templates/tmp.mount.conf.j2` | FS-1, FS-4 |
| `roles/filesystem_hardening/templates/var-tmp.mount.j2` | FS-2, FS-4 |
| `roles/filesystem_hardening/templates/dev-shm.mount.conf.j2` | FS-3, FS-4 |
| `roles/filesystem_hardening/handlers/main.yml` | FS-4 |

## Key decisions

**Systemd mount units and drop-ins, not `/etc/fstab`.** `/etc/fstab` is
only read at boot (or on an explicit `mount -a`); a hardening control
written only there would leave the live mount untouched until the host next
reboots, which can be months away on a VPS that is provisioned once and
left running. A systemd unit, by contrast, is something this role can also
start or remount on the same run that changes the file (`FS-5`), converging
the live state immediately rather than merely scheduling a future one, and
it lets the role query and reapply the deployed state declaratively on
every run (`INV-9`) instead of trusting a static file no tooling here
re-reads.

**`/dev/shm` uses a drop-in, not a full unit replacement.** `/dev/shm`'s
base unit already exists — systemd ships it and mounts it as tmpfs at
boot — so replacing it outright would mean this role owning `Type=`,
`What=` and `Where=` it never chose, and keeping them in sync with whatever
Debian's own unit changes to in a future release. A drop-in changes only
`Options=`, at the cost that a drop-in's `Options=` line replaces the base
unit's in full rather than merging with it — which is why the template
repeats `rw`, `nosuid` and `nodev` explicitly alongside its own `noexec`
(`FS-3`), rather than assuming the base unit still supplies them.

**`/tmp` stays disk-backed, bind-mounted onto itself, rather than moving to
tmpfs.** A tmpfs `/tmp` consumes RAM, which is scarce on the small VPS
instances this playbook targets. Bind-mounting `/tmp` onto itself adds the
restricted options without changing where its bytes live; `/var/tmp` is
then bind-mounted onto that same hardened `/tmp` (`FS-2`) rather than
mounted independently, which both reuses the restriction and removes
`/var/tmp` as a distinct bypass path, at the cost of the persistence across
reboots a separate `/var/tmp` would otherwise have.

## Failure modes

- **The `/tmp` drop-in template (`tmp.mount.conf.j2`) has no
  property-test coverage.** The property suite exercises the full
  bind-mount unit template (`tmp.mount.j2`) for `noexec,nosuid,nodev`,
  `Type=none`, `bind` and `rw`, but no test ever reads
  `tmp.mount.conf.j2` — the template Strategy A actually deploys whenever a
  base `tmp.mount` unit already exists, which the role's own comment states
  is systemd's normal shipped state. `FS-1` is genuinely implemented either
  way and cited in both templates, but a regression in the drop-in
  template's `Options=` line would not be caught by `make test-property`.
- **`/var/tmp`'s (and, under the bind-mount strategy, `/tmp`'s)
  already-active unit is not remounted or restarted when its definition
  changes.** `FS-6` documents this as pending: `ansible.builtin.systemd`'s
  `state: started` is a no-op on a unit that is already active, so a
  template change to `var-tmp.mount.j2` (or, under Strategy B,
  `tmp.mount.j2`) is picked up by the next `mount -a` at boot or a manual
  `systemctl restart`, never by this role's own run.
- **No configuration surface to mis-set.** Unlike `TIME` or `NET`, this
  role has no defaults file and nothing an operator selects — there is no
  equivalent failure mode to a mis-set variable, since nothing here is
  configurable.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task needs root privilege to write unit files under
  `/etc/systemd/system/` and to run `mount`, `systemctl` and
  `systemctl daemon-reload`.
- `PRJ-4` — systemd mount units, drop-in override directories, and the
  `tmp.mount`/`dev-shm.mount` naming this role builds on, are Debian's, not
  a generic Linux assumption.

**What others may assume of this spec:**

- `VRFY` — re-confirms, independently and after the run, that `/tmp`,
  `/var/tmp` and `/dev/shm` actually carry `noexec`, `nosuid` and `nodev`
  via `findmnt`, rather than trusting this role's own templates to describe
  the live state.
- `PRJ-10` — the reboot notice `PRJ-10` prints is driven by the package
  manager's own reboot-required marker; it does not fire for `FS-6`'s gap,
  so `FS-6`'s own pending state is currently the only place a stale
  `/var/tmp` (or bind-mounted `/tmp`) is named at all.
