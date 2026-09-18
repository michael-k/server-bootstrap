# Time Synchronization — Requirements

**Prefix:** `TIME`

## Purpose

This spec covers keeping a target host's clock synchronized to a reliable
network time source: selecting and configuring exactly one of chrony or
systemd-timesyncd, configuring the NTP servers it uses, enabling and
starting the chosen service, and checking that synchronization is actually
active once the service has started rather than assuming a started service
is a synchronized one. Unlike `HOST` and `NET`, this capability is not
optional — `time_sync_service` always has a default, so every host in the
fleet is a subject of this spec.

## Scope

### In scope

- Installing and configuring the service selected by `time_sync_service`
  (`chrony` or `timesyncd`).
- Ensuring that exactly one of the two candidate services is active.
- The NTP server list (`ntp_servers`) and its configurability.
- Enabling the selected service to start on boot.
- Starting the selected service.
- Checking that synchronization is actually active after starting the
  service, rather than assuming it.

### Out of scope

- The host's name, owned by `HOST`.
- Confirming, after the run, that the clock is synchronized — the
  independent, post-bootstrap check is owned by `VRFY`.
- Certificate validation and log correlation themselves, which merely
  depend on an accurate clock rather than being part of producing one.

## Security invariants

**Upholds:** INV-9
**Allowances claimed:** none

INV-9 is upheld by `TIME-1` through `TIME-5`: installing, configuring,
enabling and starting the selected service each report a change only when
the running state actually differs from what is configured, rather than
reapplying unconditionally on every run.

An accurate clock is a security precondition, not housekeeping. TLS/SSL
certificate validation depends on comparing a certificate's validity window
against the host's own clock, so a host whose clock has drifted can accept
an expired certificate or reject a valid one, with nothing naming the clock
as the cause. Correlating logs and audit trails across hosts during an
incident likewise depends on their clocks agreeing with each other; a
drifted host's timestamps silently misplace its events in that timeline,
with nothing marking them as suspect.

## Requirements

### TIME-1 — Selected service installed and configured

WHERE `time_sync_service` selects a service, THE Bootstrap SHALL install and
configure that service, either chrony or systemd-timesyncd.

**Why:** Debian images do not ship both NTP clients pre-installed and
pre-configured against a chosen server list; without this, a host's clock
runs on whatever fallback source (or none) the image shipped with, and stays
there. Nothing fails when a clock free-runs — the host simply drifts,
silently, and nothing distinguishes it from a correctly synchronized host
until something else fails first, such as a certificate check or a log
correlation, and the drifted clock turns out to have been the reason.
**Verified:** the tasks that install and template the two candidate
services are each guarded on `time_sync_service`; the unit and property
suites assert the install task, the template deployment, and the
destination path for whichever service is selected.

### TIME-2 — Exactly one time synchronization service active

THE Bootstrap SHALL stop and disable the candidate time synchronization
service that `time_sync_service` did not select.

**Why:** chrony and systemd-timesyncd can both occupy the NTP client role at
once, each independently stepping or slewing the system clock against its
own view of the network. Neither service errors when the other is also
running — the host's clock instead becomes the product of two uncoordinated
correction loops, an intermittent, unrepeatable drift that reads as a flaky
network or a hardware clock problem, not as the actual cause: two time
daemons disagreeing with each other.
**Verified:** the task file stops and disables systemd-timesyncd when
chrony is selected, and stops and disables chrony when systemd-timesyncd is
selected, each tolerating the other service already being absent; the
property suite asserts both directions.

### TIME-3 — NTP server list configurable, defaulting to the Debian pool

THE Bootstrap SHALL configure the selected service to use the servers listed
in `ntp_servers`, defaulting to the Debian NTP pool.

**Why:** A hardcoded server list would leave every host in the fleet
depending on the same handful of servers, with no way to point a host at an
internal time source or a different pool without editing the role itself.
That would not fail either — the default pool works for most hosts — but it
silently forecloses the one case where it does not, until someone needs a
different source and can only get it by editing code that looks like fixed
infrastructure rather than configuration.
**Verified:** both service templates render the configured `ntp_servers`
list into their respective NTP-server directives, and the role's default
variables set it to the Debian pool; the unit suite renders both templates
against custom and default server lists and asserts every server appears in
the rendered output.

### TIME-4 — Selected service enabled on boot

THE Bootstrap SHALL enable the selected time synchronization service to
start on boot.

**Why:** A service that is merely started now but not enabled reverts, on
the very first reboot, to whatever the image's default was — silently, with
nothing in this run's output pointing at the missing boot-enablement as the
reason a rebooted host later drifts.
**Verified:** the systemd task for the selected service sets `enabled:
true`; the property suite asserts the flag is present.

### TIME-5 — Selected service started

THE Bootstrap SHALL start the selected time synchronization service.

**Why:** Installing and configuring a service is not the same as it
running — an installed-but-stopped NTP client leaves a host's clock exactly
where it was before this spec's other requirements did anything, with every
other precondition satisfied (a configured server list, a boot-enabled
unit) and still no clock discipline actually happening.
**Verified:** the systemd task for the selected service sets `state:
started`; the property suite asserts it.

### TIME-6 — Synchronization checked after starting, not assumed

THE Bootstrap SHALL check the selected service's synchronization state after
starting it, rather than treating a started service as a synchronized one.

**Why:** A time synchronization service can be installed, configured,
enabled and running while its clock is still unsynchronized — immediately
after start, before its first successful poll, or continuously if every
configured server is unreachable. `chronyc tracking` and `timedatectl
timesync-status` both report a definite "not yet synchronised" state rather
than erroring in that situation, so a run that starts the service and stops
looking would report success on a host whose clock never actually moved
toward correct, with nothing distinguishing that host from one that
synchronized within milliseconds.

**Traceability:** pending — the task runs `chronyc tracking` (or
`timedatectl timesync-status`), registers the output, and displays it with
`ansible.builtin.debug`, but nothing evaluates that output: there is no
`failed_when` and no `assert` against it. A host whose selected service
reports "Not synchronised" (chrony) or an equivalent not-yet-synced status
(timesyncd) still passes this task, and the run reports success identically
to a host that is actually synchronized — the two are distinguishable only
by an operator who reads the displayed status by eye.
