# Hostname — Requirements

**Prefix:** `HOST`

## Purpose

This spec covers giving a target host a stable, self-consistent identity: an
optional, operator-chosen hostname that is applied to the running kernel,
survives a reboot, and resolves locally the way software on the host expects
it to. The capability is optional and additive — a host that never sets
`system_hostname` keeps whatever name it already had, and is not a subject
of this spec at all.

## Scope

### In scope

- Setting the target host's running hostname to a configured value.
- Persisting that hostname so it survives a reboot.
- Keeping `/etc/hosts` consistent with the configured hostname.
- The no-op path when no hostname is configured.

### Out of scope

- Choosing what hostname to use, which is an inventory decision for whoever
  runs the bootstrap.
- Time synchronization, which happens to be configured by tasks in the same
  role directory (`roles/system_config/`) — owned by `TIME`.
- The hostname line in the pre-run configuration summary, owned by `PRJ-9`.
- Confirming, after the run, that the running hostname matches the
  configured value — owned by `VRFY`.

## Security invariants

**Upholds:** INV-9
**Allowances claimed:** none

INV-9 is upheld by `HOST-1` through `HOST-3`: each converges the host's
hostname state toward the same configured value on every run — the
`ansible.builtin.hostname` module reports a change only when the running
name actually differs, and the two file-writing tasks report a change only
when their rendered content differs — rather than reapplying unconditionally
on every run. `HOST-4` upholds it more directly still: a host with no
hostname configured is left completely untouched.

## Requirements

### HOST-1 — Hostname set to the configured value

WHERE `system_hostname` is set, THE Bootstrap SHALL set the target host's
running hostname to `system_hostname`.

**Why:** `sudo`, systemd, and most logging and monitoring agents read the
running hostname to identify the machine they're on. Left unset, none of
them error — they simply keep reporting the identity the image or provider
assigned, so a host silently never becomes the one its inventory entry says
it is, and nothing about that mismatch is visible until someone compares the
two by hand.
**Verified:** the `ansible.builtin.hostname` task runs with `name` bound to
`system_hostname`; the property suite asserts the task and the variable
binding are both present.

### HOST-2 — Hostname persisted across reboots

WHERE `system_hostname` is set, THE Bootstrap SHALL write `system_hostname`
to `/etc/hostname`, owned by root with mode `0644`.

**Why:** `ansible.builtin.hostname` changes only the kernel's running
hostname; nothing reloads that value at boot unless it is also on disk. Left
out, the failure would not appear at the end of this run — it would appear
silently, one reboot later, when the host reverts to its original name with
no error and no task reporting anything wrong, undoing `HOST-1` as if it had
never run.
**Verified:** the "Update /etc/hostname for persistence" task writes
`system_hostname` followed by a newline to `/etc/hostname` with `owner:
root`, `group: root` and `mode: "0644"`; the property suite asserts the
destination path, content and permissions.

### HOST-3 — `/etc/hosts` kept consistent with the configured hostname

WHERE `system_hostname` is set, THE Bootstrap SHALL map `system_hostname` to
`127.0.1.1` in `/etc/hosts`.

**Why:** Many programs on a Debian host — `sudo` among them — resolve the
local hostname through `/etc/hosts` before ever consulting DNS. A hostname
with no matching entry there, and no DNS record for itself either, does not
fail with an error: it stalls, for several seconds, on every `sudo`
invocation and on any daemon that resolves its own name at startup, which
reads as a slow or flaky network rather than as the missing line that
actually caused it.
**Verified:** the "Update /etc/hosts with new hostname" task uses
`ansible.builtin.lineinfile` to replace the line matching `^127\.0\.1\.1\s+`
with `127.0.1.1       {{ system_hostname }}`; the property suite asserts the
path, the match expression and the replacement line.

### HOST-4 — No-op without a configured hostname

THE Bootstrap SHALL leave a host's hostname, `/etc/hostname` and
`/etc/hosts` untouched when `system_hostname` is not set.

**Why:** Most hosts in this project's fleet never set `system_hostname` and
keep whatever name the image or provider assigned. A role that ran
regardless — even one that harmlessly re-asserted the host's existing name —
would still rewrite `/etc/hostname` and `/etc/hosts` on every host on every
run, turning a capability most hosts should never see touch into one that
touches every host's identity files whether it was asked to or not.
**Verified:** the hostname tasks are imported only `when: system_hostname is
defined and system_hostname | length > 0`; the property suite asserts that
guard is present and that `system_hostname` defaults to the empty string.
