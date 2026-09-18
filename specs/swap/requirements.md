# Swap — Requirements

**Prefix:** `SWAP`

## Purpose

This spec covers giving a target host swap space so that a memory spike
degrades performance instead of killing a process: an optional compressed
in-RAM swap device (zram), an optional disk-backed swap file at
`/swapfile`, the priority relationship that makes the kernel reach for the
fast one first, and the persistence that brings both back after a reboot.
Unlike `TIME` and `FS`, neither half of this capability is on by default —
`zram_enabled` is false and `disk_swap_size` is empty, so a host is a
subject of this spec only once an operator asks for one or both.

## Scope

### In scope

- Whether zram swap is configured at all (`zram_enabled`) and how large it
  is (`zram_size`, as a percentage of RAM or an absolute size).
- Installing the package that provides the zram swap service.
- Creating the zram device, compressing it with lz4, formatting it as swap,
  activating it, and bringing it back on boot.
- The zram device's swap priority (`zram_swap_priority`).
- Whether disk swap is configured at all (`disk_swap_size`).
- Creating `/swapfile`, restricting it to root, formatting it, activating
  it, and recording it in `/etc/fstab`.
- The requirement that zram outrank disk swap whenever both are configured.
- Skipping swap configuration entirely when neither is configured.

### Out of scope

- Kernel memory-management tuning beyond swap priority — `vm.swappiness`,
  `vm.vfs_cache_pressure`, overcommit policy and the OOM killer's own
  scoring are not configured here.
- Swap partitions and swap on a block device other than the zram device;
  only a swap file and zram are offered.
- Encrypting swap at rest. `SWAP-12` restricts who can read `/swapfile`
  while the host runs; it does not make the bytes on disk unreadable to
  someone holding the disk.
- Independent, post-bootstrap confirmation that swap is actually active with
  the intended priorities, owned by `VRFY`.
- Where this capability sits relative to the rest of the run, and the
  run-level gate that skips the role when it has nothing to do, owned by
  `PRJ-12`.

## Security invariants

**Upholds:** INV-9
**Allowances claimed:** none

INV-9 is upheld by `SWAP-12` above all: `/swapfile`'s mode is re-asserted
declaratively on every run that reaches the disk swap path, unconditionally
and independently of whether the file was created by this run, so no re-run
can leave the file more readable than an earlier run left it. The rest of
the role converges the same way — the zram configuration is rendered from a
template that produces the same content for the same variables, activating
swap only ever adds swap to the kernel's list, and the `/etc/fstab` entry is
only ever added.

Swap deserves the attention because of what it holds. Any page the kernel
evicts can end up in swap: decrypted secrets, private keys a daemon read
into memory, session tokens, the contents of a password prompt. A
world-readable `/swapfile` therefore exposes whatever the host was thinking
about, to any local account, without touching the process that owns it.

## Requirements

### SWAP-1 — Zram swap configurable and off by default

THE Bootstrap SHALL accept `zram_enabled` as a configurable variable
determining whether zram swap is configured, defaulting to off.

**Why:** Zram trades CPU for RAM, and whether that trade is worth making
depends on the host — a CPU-bound worker gains nothing from compressing
pages it will decompress moments later. Defaulting to on would impose that
trade silently on every host in the fleet, because a host with zram enabled
looks exactly like one without it until someone profiles it: no task fails,
no warning is printed, and the cost shows up only as compression work
attributed to the kernel rather than to a decision this playbook made.
**Verified:** the role's defaults define `zram_enabled` as `false`, and the
zram task file is included only under a condition on it; the unit suite
asserts the inclusion is conditioned on `zram_enabled`, and the property
suite asserts both the condition and the `false` default.

### SWAP-2 — Zram size configurable as a percentage of RAM or an absolute size

THE Bootstrap SHALL accept `zram_size` as a configurable variable expressed
either as a percentage of total RAM or as an absolute size.

**Why:** A percentage suits a fleet of differently-sized hosts; an absolute
size suits a host whose memory budget is already spoken for. Supporting
only one form would force the other case to be expressed by hand per host.
The silent failure is in the conversion rather than the choice: a value in
neither form — `2GB`, `2048`, a typo — is not rejected, it falls through to
a hardcoded 50% of RAM, so the operator gets a working zram device of a
size they did not ask for, with nothing in the run's output naming the
value that was discarded.
**Verified:** the rendered configuration selects a percentage directive for
a value ending in `%`, converts a `G`/`g` value to megabytes and passes an
`M`/`m` value through, and falls back to 50% for anything else; the
defaults define `zram_size`. The unit suite renders all three accepted
forms and asserts the resulting directive; the property suite asserts each
branch exists in the template across generated percentage and absolute
sizes. No test exercises the fallback branch, and nothing anywhere reports
that a value took it.

### SWAP-3 — Zram swap service installed

WHERE zram is enabled, THE Bootstrap SHALL install the `zram-tools`
package.

**Why:** Nothing in a stock Debian image creates or manages a zram swap
device. Without the package that provides the service, the configuration
file this role writes is a file no program reads, the service it later
enables does not exist, and the host runs with the memory headroom the
operator believed they had configured.
**Verified:** the zram task file installs `zram-tools` with the package
module, refreshing the package cache first; the property suite asserts the
module, the package name and the desired state.

### SWAP-4 — Zram device created at the configured size

WHERE zram is enabled, THE Bootstrap SHALL create a zram device sized
according to `SWAP-2`'s configured value.

**Why:** A zram device that does not exist, or one the service failed to
size, leaves the host with the memory pressure behaviour it had before —
and the failure is asynchronous: the configuration file is written and the
service is started successfully, while the device itself appears (or does
not) some moments later, in the kernel, where a successful Ansible task has
no visibility. A run that stopped at "service started" would report success
on a host with no swap device at all.
**Verified:** the size directive is rendered into the service's
configuration file, and the role then waits for the device node to appear
before continuing, failing the run if it does not within the timeout. That
wait confirms the device exists; nothing in the role, and no test,
re-reads the device's actual size to confirm it matches what was
configured. The integration suite asserts the device node exists on a
bootstrapped host.

### SWAP-5 — Zram device compressed with lz4

WHERE zram is enabled, THE Bootstrap SHALL configure the zram device to
compress with lz4.

**Why:** The compression algorithm is the whole economics of zram: it is
paid on every page in and every page out, precisely when the host is
already under memory pressure and least able to absorb a slow decompress.
A different algorithm still produces a working swap device — nothing fails,
nothing warns — it just makes reclaim slower than the design assumed, which
surfaces as latency under load rather than as a configuration error.
**Verified:** the rendered configuration sets the algorithm to lz4, and the
role reads the device's own reported algorithm back from the kernel after
the service has started and asserts lz4 is the active one, so a service
that silently substituted another algorithm fails the run rather than
passing it. The unit suite asserts the rendered directive, the property
suite asserts both the directive and the read-back assertion, and the
integration suite reads the algorithm from a bootstrapped host.

### SWAP-6 — Zram device formatted as swap

WHERE zram is enabled, THE Bootstrap SHALL ensure the zram device is
formatted as swap space.

**Why:** A zram device is a block device like any other; until swap
metadata is written to it, the kernel will not accept it as swap. An
unformatted device is not an error state the host reports — it is simply a
block device nobody uses, on a host that believes it has swap.
**Verified:** the role never runs `mkswap` against the zram device itself;
formatting is done by the zram swap service, on its own, when it starts.
What the role does is require that the device appears in the kernel's list
of active swap areas, which cannot happen for a device carrying no swap
metadata — so formatting is confirmed only indirectly, as a precondition of
`SWAP-7`. No unit, property or integration test checks the formatting step
separately from activation.

### SWAP-7 — Zram device active as swap

WHERE zram is enabled, THE Bootstrap SHALL activate the zram device as
swap.

**Why:** Every preceding requirement can hold — package installed,
configuration written, service started, device created and formatted —
while the device is still not in the kernel's list of swap areas, and
nothing about that state announces itself. The host simply has no more
memory headroom than it started with, and finds out under load, when a
process is killed rather than paged.
**Verified:** the role queries the kernel's active swap areas after
starting the service and fails the run unless the zram device is among
them; the property suite asserts that query and its failure condition, and
the integration suite confirms the device is active as swap on a
bootstrapped host.

### SWAP-8 — Zram swap re-established on boot

WHERE zram is enabled, THE Bootstrap SHALL enable the zram swap service to
start on boot.

**Why:** A zram device lives in RAM and does not survive a reboot; unlike a
swap file, there is nothing left on disk to re-activate. A service that was
started but never enabled therefore leaves the host with swap exactly until
its first reboot and none afterwards — and the reboot is the moment a host
is least watched, so the loss is discovered later, by the process that was
killed rather than paged.
**Verified:** the role sets the service to be enabled on boot as well as
started; the property suite asserts the enablement flag.

### SWAP-9 — Zram swap priority configurable

WHERE zram is enabled, THE Bootstrap SHALL assign the zram device the swap
priority given by `zram_swap_priority`.

**Why:** When more than one swap area is active, the kernel fills the
highest-priority area first. Leaving the zram device on the kernel's
default (a negative, auto-assigned priority) would make the ordering an
accident of activation order rather than a decision — and either ordering
produces a host with the right total amount of swap, so the wrong one is
invisible except as unexplained disk I/O during reclaim.
**Verified:** the rendered configuration sets the service's priority
directive from `zram_swap_priority`, and the defaults define it; the unit
suite asserts the rendered value, and the property suite asserts the
directive uses the variable.

### SWAP-10 — Disk swap configurable and off by default

THE Bootstrap SHALL accept `disk_swap_size` as a configurable variable
determining whether a disk swap file is configured, defaulting to unset.

**Why:** Disk swap consumes disk the operator may have allocated for
something else, and on a small VPS that allocation is often the binding
constraint. Defaulting to a size would quietly take that space on every
host — and a full root filesystem fails far from here, in whatever service
runs out of room first, with no trace pointing back at a swap file this
playbook created without being asked.
**Verified:** the role's defaults define `disk_swap_size` as an empty
string, and the disk swap task file is included only when it is non-empty;
the unit suite asserts the inclusion is conditioned on `disk_swap_size`,
and the property suite asserts both the condition and the empty default.

### SWAP-11 — Swap file created at /swapfile at the configured size

WHERE `disk_swap_size` is set, THE Bootstrap SHALL create a swap file at
`/swapfile` of that size.

**Why:** Without the file there is no disk swap, and the requirement fixes
both the path and the size so the rest of this spec has something definite
to restrict, format, activate and persist. A fixed path also means a re-run
recognises the file it created last time rather than accumulating another
one beside it — an accumulation that would show up only as disk space
disappearing.
**Verified:** the role allocates the file at `/swapfile` at the configured
size, and skips the allocation when the path already exists, so a re-run
neither re-allocates nor grows it. The property suite asserts the
allocation command, the configured size and the skip condition; the
integration suite confirms the file exists on a bootstrapped host. Nothing
compares an existing `/swapfile`'s size against the currently configured
`disk_swap_size`, so a changed size is not applied to a file that already
exists.

### SWAP-12 — Swap file readable only by root

WHERE `disk_swap_size` is set, THE Bootstrap SHALL set `/swapfile`'s mode
to `0600`.

**Why:** Swap holds whatever the kernel evicted from memory, and the kernel
does not discriminate: decrypted secrets, private keys a daemon read in,
session tokens, a password typed at a prompt. A swap file readable by other
local accounts hands all of that over by a plain read, with no privilege
escalation, no exploit, and nothing at all in any log — the owning process
is never involved and never knows. `0600` is what keeps the file's contents
to root, and it is the only control in this spec that protects secrets
rather than availability.
**Verified:** the role sets `/swapfile` to mode `0600` owned by `root`, on
every run that reaches the disk swap path rather than only on the run that
created the file, so a file left more permissive by any other means is
restricted again on the next run. The unit suite asserts the mode and path
on the task, the property suite asserts the mode, owner and group, and the
integration suite reads the mode back from a bootstrapped host.

### SWAP-13 — Swap file formatted as swap

WHERE `disk_swap_size` is set, THE Bootstrap SHALL format `/swapfile` as
swap space.

**Why:** An allocated file is a region of zeroed disk; the kernel refuses
it as swap until swap metadata is written into it. Nothing reports an
unformatted swap file — it is an ordinary file taking up ordinary disk
space on a host that believes it has swap.
**Verified:** the role formats `/swapfile` with `mkswap`, conditioned on
the allocation having just happened, so a re-run does not re-format a file
that is already in use. The property suite asserts the format command and
that condition.

### SWAP-14 — Swap file active as swap

WHERE `disk_swap_size` is set, THE Bootstrap SHALL activate `/swapfile` as
swap.

**Why:** A formatted swap file is not swap until the kernel is told to use
it; until then the host has spent the disk and gained none of the headroom.
The failure is quiet in both directions — the run reports success, and the
host behaves exactly as it did before, right up to the moment a memory
spike kills a process that could have been paged.
**Verified:** the role activates `/swapfile` with the configured priority,
conditioned on the file having just been formatted in the same run. A run
that finds `/swapfile` already present therefore activates nothing: on a
host where the file exists but is not currently in use as swap — after a
manual `swapoff`, or a previous run that failed between formatting and
activation — the run reports success while no disk swap is active, and the
`SWAP-15` entry only restores it at the next reboot. The property suite
asserts the activation command and its condition; the integration suite
confirms `/swapfile` is active as swap on a freshly bootstrapped host,
which is the path where the condition does hold.

### SWAP-15 — Swap file re-activated on boot

WHERE `disk_swap_size` is set, THE Bootstrap SHALL record `/swapfile` in
`/etc/fstab` so it is activated again on boot.

**Why:** Activating swap affects only the running kernel; the record on
disk is what makes it survive a reboot. Without it, a host silently loses
its disk swap the first time it restarts, and the loss is indistinguishable
from a host that never had any — the file is still there, the right size,
with the right mode, simply unused.
**Verified:** the role adds an `/etc/fstab` entry naming `/swapfile`, the
`swap` type and the configured priority, and adds it only after a check
that finds no existing entry for that path, so a re-run does not duplicate
it. That check matches the path alone: an entry that already exists is left
exactly as it is, so a later change to the configured priority is not
written into `/etc/fstab` and takes effect only on hosts that had no entry
yet. The unit suite asserts the entry names the path, the type and the
priority variable, the property suite asserts the entry, the duplicate
check and its condition, and the integration suite reads the entry back
from a bootstrapped host.

### SWAP-16 — Zram preferred over disk swap

WHERE zram and disk swap are both configured, THE Bootstrap SHALL give the
zram device a higher swap priority than `/swapfile`.

**Why:** Zram is compressed RAM and disk swap is disk; a page reclaimed to
zram costs microseconds of CPU, one reclaimed to `/swapfile` costs disk
I/O, on a host already struggling. The default priorities — 100 for zram
against 10 for the swap file — encode that ordering. Nothing enforces it:
an operator who raises `disk_swap_priority` above `zram_swap_priority`, or
lowers the zram one, inverts the ordering without any task failing, and the
result is a host that is slower under memory pressure in a way no log line
attributes to a swap priority.
**Verified:** the role's defaults set `zram_swap_priority` to 100 and
`disk_swap_priority` to 10, and each is rendered into its respective
configuration; the property suite reads both values out of the defaults
file and asserts the zram one is greater. That assertion is made against
the defaults only — no task compares the two values at run time, so an
inventory that overrides either is not checked by anything. The integration
suite does check the live ordering, reading both priorities back from the
kernel on a host bootstrapped with both kinds of swap enabled.

### SWAP-17 — Swap configuration skipped when neither kind is configured

WHERE neither zram nor disk swap is configured, THE Bootstrap SHALL skip
swap configuration.

**Why:** With both defaults off, most hosts want nothing from this
capability, and a role that ran anyway would install a package and write a
configuration file on hosts that asked for neither — changes that alter a
host's package set without any operator ever choosing them, and that would
be attributed to this playbook only by someone reading its source.
**Verified:** each of the two task files is included under its own
condition — zram on `zram_enabled` being true, disk swap on
`disk_swap_size` being non-empty — so neither runs when its side is
unconfigured and nothing else in the role does any work; the unit suite
asserts both conditions, and the property suite asserts them together with
the defaults that leave both sides off.
