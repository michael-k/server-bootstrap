# Logging — Requirements

**Prefix:** `LOG`

## Purpose

This spec covers configuring journald, systemd's logging service, so that the
host's logs survive a reboot: persistent storage on disk, a configurable
ceiling on how much disk the journal may consume, a configurable retention
time after which old entries are discarded, the directory those entries are
actually written into and its permissions, and restarting journald so a
changed configuration takes effect within the same run rather than at the
next reboot. Unlike `SWAP`, this capability has no enabling variable — it
always applies, identically, to every host in the fleet; only the disk-usage
cap and the retention time are configurable.

## Scope

### In scope

- Whether journald persists logs to disk at all (`Storage=persistent`).
- The maximum disk space the persistent journal may use
  (`journald_max_disk_usage`), defaulting to `500M`.
- The maximum time journal entries are retained before being discarded
  (`journald_max_retention_time`), defaulting to `1month`.
- Creating the directory journald writes persistent entries into, and its
  ownership and permissions.
- Restarting journald within the same run when its configuration changes.

### Out of scope

- Journal compression (`Compress=yes`) and forwarding to syslog
  (`ForwardToSyslog=no`) — the role sets a fixed value for each, but neither
  is a security control and neither is configurable, so this spec does not
  track them as requirements.
- Which services log what, or how an individual service's own logging is
  configured — this spec covers journald's storage policy only, not the
  content that ends up in it.
- Independent, post-bootstrap confirmation that persistent storage and its
  limits are actually in effect, owned by `VRFY`.
- Where this capability sits relative to the rest of the run, owned by
  `PRJ-12`.
- What privileged actions get logged, and who is a named principal allowed
  to take them — owned by `SUDO` and `USR`. This spec keeps the record; it
  does not decide what gets recorded or who may act.

## Security invariants

**Upholds:** INV-7, INV-9
**Allowances claimed:** none

INV-7 requires both that privilege escalation is restricted to named
principals who authenticate to escalate, unless a registered allowance
covers the grant, and that its use leaves an audit trail. This spec is what makes
the second half real rather than nominal: sudo, and everything else on the
host, logs through journald, and a log that lives only in `/run` is erased by
the next reboot before anyone reads it. `LOG-1`'s persistence is what turns
"journald recorded it" into an audit trail that outlives the session it was
recorded in; `LOG-2` and `LOG-3` bound how much of that trail is kept and for
how long, without either of which the disk itself would eventually bound it
instead.

INV-9 is upheld by the same mechanism that upholds it elsewhere in this
tree: the configuration is deployed declaratively from a template that
renders the same content for the same variables on every run, and `LOG-5`'s
directory permissions are re-asserted unconditionally on every run rather
than only on the run that first created the directory — so no re-run can
leave the journal's storage more permissive, or its configuration weaker,
than an earlier run left it.

## Requirements

### LOG-1 — Journald persists logs to disk

THE Bootstrap SHALL configure journald to store logs persistently on disk.

**Why:** journald's own default (`Storage=auto`) keeps entries only in
`/run/log/journal`, a tmpfs, unless `/var/log/journal` already exists. That
tmpfs is indistinguishable from a persistent journal during day-to-day
operation — every command works, every log query returns the expected
entries — right up until the host reboots or crashes, at which point
everything recorded since boot is gone. A reboot is also the moment an
operator is least likely to be watching, so the loss of the very history that
would explain why the host rebooted is discovered only when someone goes
looking for it afterward.
**Verified:** the rendered `journald.conf` sets `Storage=persistent`
unconditionally, on every host; the unit and property suites both assert the
directive's literal presence in the rendered template, and a behavioral test
confirms journald accepts a log entry and returns it within the same run. No
test reboots the host, or otherwise confirms that an entry written before a
restart is still readable after one — persistence is checked at the level of
the configuration directive, not by observing a reboot.

### LOG-2 — Maximum journal disk usage configurable, default 500M

THE Bootstrap SHALL accept `journald_max_disk_usage` as a configurable
variable capping the persistent journal's disk usage, defaulting to `500M`.

**Why:** without a cap, a chatty service — a crash-looping unit, a debug log
left on, an attacker generating noise to bury their own trail — can grow the
journal without bound, and on a small VPS "without bound" means the root
filesystem itself running out of space. That failure surfaces in whatever
service next tries to write to disk, not in the logging configuration that
allowed it, so an operator debugging a "disk full" incident has no reason to
suspect journald until they check its actual usage.
**Verified:** the rendered configuration sets `SystemMaxUse` from
`journald_max_disk_usage`, and the role's defaults define it as `500M`; the
unit suite renders both the default and a custom value and asserts the
directive, and the property suite asserts the same across generated valid
values. No task or test confirms journald actually enforces the configured
cap on a live host — `SystemMaxUse` is trusted to work as documented rather
than observed doing so.

### LOG-3 — Journal retention time configurable, default 1 month

THE Bootstrap SHALL accept `journald_max_retention_time` as a configurable
variable capping how long journal entries are retained, defaulting to
`1month`.

**Why:** without a retention cap, journald keeps entries until the disk cap
(`LOG-2`) forces it to start discarding the oldest ones, which means the
oldest surviving entry — and therefore how far back an incident investigation
can see — is decided implicitly by how much log volume accumulated, not by
any conscious retention decision. An operator who assumes "at least a month
of history" on the strength of the default has no way to tell, from the
running host, that a noisy week silently pushed everything older out days
early.
**Verified:** the rendered configuration sets `MaxRetentionSec` from
`journald_max_retention_time`, and the role's defaults define it as
`1month`; the unit suite renders both the default and a custom value and
asserts the directive, and the property suite asserts the same across
generated valid values. As with `LOG-2`, nothing confirms journald actually
discards entries older than the configured value on a live host.

### LOG-4 — Journald restarted when its configuration changes

THE Bootstrap SHALL restart journald when its configuration changes.

**Why:** journald reads `/etc/systemd/journald.conf` only at startup;
templating a new file changes what journald will use next time it starts —
normally at the host's next reboot — but does nothing to the already-running
daemon. Without an immediate restart, a run that changes
`journald_max_disk_usage` or `journald_max_retention_time`, or turns on
persistence for the first time, would report success while the live daemon
keeps enforcing whatever limits — or lack of persistence — it started with,
for as long as the host stays up, which on a VPS provisioned once can be
months.
**Verified:** the template deployment task notifies a handler that restarts
`systemd-journald`, and the role flushes handlers immediately afterward
rather than waiting for the play to end, so the restart happens within the
same run. The unit and property suites both assert the notify relationship
and the immediate flush; no test starts journald, changes the configuration,
and confirms the running daemon's actual limits changed — the restart is
verified as a triggered action, not as an observed effect.

### LOG-5 — Persistent journal directory created with restricted permissions

THE Bootstrap SHALL create `/var/log/journal`, owned by `root` and the
`systemd-journal` group, with mode `2755`.

**Why:** this is the directory journald actually writes persistent entries
into; its group and mode are what let members of the `systemd-journal` group
read the journal without making it world-readable, and the setgid bit is what
keeps files journald creates inside it owned by that group rather than
reverting to root's alone. A directory left with different ownership or mode
doesn't stop logging — journald degrades in a way nothing here reports:
entries the `systemd-journal` group can no longer read become effectively
private to root, and the loss of read access is discovered only by whichever
tool or person next tries to read the journal and cannot.
**Verified:** the role creates `/var/log/journal` with owner `root`, group
`systemd-journal` and mode `2755`, unconditionally on every run; the property
suite asserts the path, ownership and mode, and a behavioral test confirms
the directory exists on a bootstrapped host. No test simulates a manually
drifted permission and confirms a re-run repairs it — the unconditional task
is expected to converge on every run, the same way `SWAP-12`'s mode
reassertion does, but that convergence is not itself exercised by any test.
