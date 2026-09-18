# Swap — Design

## Approach

The role is a dispatcher plus two independent task files. `tasks/main.yml`
includes `zram.yml` when `zram_enabled` is true and `disk_swap.yml` when
`disk_swap_size` is non-empty; the two sides share nothing but the priority
variables that relate them, so a host may have either, both, or — the
default — neither.

The two sides converge in opposite ways. Zram is **declarative and
delegated**: the role installs `zram-tools`, renders one configuration file
from a template, and enables and starts the service, which is what actually
creates the device, formats it and activates it. The role then verifies the
outcome from the kernel's side — it waits for the device node, requires the
device to appear in the active swap areas, and reads the compression
algorithm back and asserts it is lz4. Nothing about the device is asserted
from the template alone.

Disk swap is **imperative and chained**: allocate the file, restrict it,
format it, activate it, record it in `/etc/fstab`. Each step after the first
is conditioned on the previous step having reported a change, which is what
makes the sequence idempotent — but it also means that on any run where
`/swapfile` already exists the whole chain after the permission task is
skipped. The one step that is deliberately unconditional is the `0600` mode
(`SWAP-12`), which is re-asserted on every run rather than only on the run
that created the file.

## Implementation map

| Path | Realises |
|---|---|
| `roles/swap/tasks/main.yml` | SWAP-1, SWAP-10, SWAP-17 |
| `roles/swap/defaults/main.yml` | SWAP-1, SWAP-2, SWAP-9, SWAP-10, SWAP-16 |
| `roles/swap/tasks/zram.yml` | SWAP-3, SWAP-4, SWAP-5, SWAP-6, SWAP-7, SWAP-8, SWAP-9 |
| `roles/swap/templates/zram.conf.j2` | SWAP-2, SWAP-4, SWAP-5, SWAP-9, SWAP-16 |
| `roles/swap/handlers/main.yml` | SWAP-4, SWAP-5, SWAP-9 |
| `roles/swap/tasks/disk_swap.yml` | SWAP-11, SWAP-12, SWAP-13, SWAP-14, SWAP-15, SWAP-16 |

## Key decisions

**lz4, not zstd.** zstd compresses considerably better than lz4 at the same
memory budget, which for a swap device translates directly into more
effective headroom per byte of RAM spent. It was rejected anyway, because
the moment zram is used is the moment the host is already short of memory
and under load: every fault against a swapped-out page pays a decompression
before the faulting process can continue. lz4's decompression is roughly an
order of magnitude faster than zstd's, and it is decompression latency —
not compression ratio — that decides whether the host degrades or stalls
under exactly the pressure zram exists to absorb. The cost of the choice is
real: an lz4 zram device holds meaningfully less than a zstd one of the same
size, so `SWAP-2`'s size has to be set larger to reach the same effective
headroom. `SWAP-5` is written so that this is checked rather than assumed —
the role reads the algorithm back from the kernel and fails if it is not
lz4, because a service that silently substituted an algorithm would produce
a working device with different performance and no complaint.

**Zram at priority 100, `/swapfile` at priority 10.** When several swap
areas are active, the kernel fills the highest-priority one first and only
spills into the next when it is full. Giving zram the higher number makes
the fast, RAM-backed, compressed area absorb the first wave of reclaim, and
leaves the disk file as the slower reserve for a spike zram alone cannot
hold. The alternative — leaving both on the kernel's auto-assigned negative
priorities — would order them by activation order, which is not a decision
anyone made and would vary between a first run and a reboot. The gap of 90
between the two values is deliberate slack, so a host that adds a third swap
area later can be slotted between them without renumbering either. Both
values are ordinary role defaults and an inventory may override either;
`SWAP-16` states the relationship that must hold, and the failure mode below
records that nothing enforces it at run time.

**`fallocate`, not `dd`, to create the swap file.** `dd` writes every byte;
`fallocate` asks the filesystem to reserve the extents, which is close to
instantaneous even for a multi-gigabyte file and is why creating swap does
not dominate the run's wall time. The trade is that the reservation is only
valid where the filesystem gives `swapon` contiguous, fully-allocated
extents — ext4, Debian's default here, does; a copy-on-write filesystem such
as Btrfs does not, and `swapon` refuses the file as having holes. That
failure is loud (the activation task fails), which is why it is recorded as
a constraint rather than guarded against: `PRJ-4`'s Debian floor is what
makes the assumption safe.

**Verification is read back from the kernel, not asserted from the
template.** The zram side could have been considered done once the
configuration file was written and the service started. It is not: the role
waits for the device node, requires the device in the kernel's swap list,
and compares the kernel's reported algorithm against lz4. This is the
opposite of the disk-swap side, where the role issues the commands itself
and therefore knows they ran. Delegating device creation to a service means
the only honest confirmation is the one that asks the kernel what actually
happened.

**`/etc/fstab` for the swap file, no persistence mechanism for zram.** The
asymmetry is not an oversight. `/swapfile` survives a reboot as a file, so
something must tell the next boot to use it (`SWAP-15`). A zram device does
not survive at all — there is nothing on disk to re-activate — so its
persistence is the service's boot enablement (`SWAP-8`) and nothing else.

## Failure modes

- **A `zram_size` in an unrecognised form is silently replaced by 50% of
  RAM.** The template branches on a trailing `%`, then `G`/`g`, then
  `M`/`m`, and its final `else` emits a hardcoded 50% percentage directive.
  A value such as `2GB`, a bare `2048`, or a typo therefore produces a
  working zram device of a size nobody chose. No task validates the
  variable, no test exercises the fallback branch, and the run's output does
  not mention that a configured value was discarded.
- **The swap file is activated only on the run that formats it.** Both the
  format and the activation steps are conditioned on the preceding step
  having changed, so a run that finds `/swapfile` already present skips
  both. On a host where the file exists but is not currently active as swap
  — after a manual `swapoff`, or a previous run interrupted between
  formatting and activation — this role reports success while the host has
  no disk swap, and only a reboot (via the `/etc/fstab` entry) restores it.
  `SWAP-14`'s `**Verified:**` line states this rather than claiming
  convergence the chain does not provide.
- **A changed `disk_swap_priority` is never written into an existing
  `/etc/fstab` entry.** The duplicate check matches on the `/swapfile` path
  alone and the entry is added only when no match is found, so the priority
  recorded in `/etc/fstab` is whichever value was configured on the run that
  first created the entry. A later change to `disk_swap_priority` is applied
  to the running kernel only on a host that also re-created the file, and to
  `/etc/fstab` not at all — so a reboot can restore the *old* ordering
  `SWAP-16` describes, on a host whose inventory says otherwise.
- **Nothing enforces `SWAP-16` at run time.** The zram and disk priorities
  are independent variables rendered into two different files. An inventory
  that sets `disk_swap_priority` above `zram_swap_priority` inverts the
  intended ordering with no task failing and no warning printed. The
  property suite's check compares the two *defaults* in the role's defaults
  file, which an override does not touch; only the integration suite reads
  the live ordering back, and only for the fixed configuration its fixture
  bootstraps.
- **Re-rendering the zram configuration deactivates and reactivates swap.**
  The template task notifies a handler that restarts the zram swap service,
  and restarting it means the device is removed from the kernel's swap areas
  and re-added. Removing an active swap area forces every page currently
  swapped out on it back into RAM, which on a memory-pressured host can be
  slow, and can fail outright if there is not enough free memory to take the
  pages back. This is the role's existing behaviour for any change to
  `zram_size` or `zram_swap_priority` — the rewrite of this file's comments
  into `SWAP-N` citations triggers it once, on the next run, for the same
  reason.
- **`SWAP-6` is confirmed only as a precondition of `SWAP-7`.** The role
  never formats the zram device itself; the service does. The only evidence
  the role collects is that the device appears in the kernel's active swap
  areas, which an unformatted device cannot do. There is no separate check,
  in the role or in any test, that distinguishes "not formatted" from "not
  activated" — a failure of either is reported as the same single failure.
- **`test_zram_priority_higher_than_disk` in the unit suite proves
  nothing about the role.** It asserts that its own fixture's `100` is
  greater than its own fixture's `10`; it never reads the role's defaults,
  its templates, or its tasks. The assertion cannot fail for any change
  anyone makes to `roles/swap/`. It is cited against `SWAP-16` because that
  is the requirement it names, but `SWAP-16`'s `**Verified:**` line credits
  the property and integration suites, which do read the role, rather than
  this test.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task needs root privilege to install a package, write
  `/etc/default/zramswap` and `/etc/fstab`, allocate and `chmod` a file at
  the filesystem root, and run `mkswap`, `swapon` and `systemctl`.
- `PRJ-4` — the `zram-tools` package, the `zramswap` service and
  `/etc/default/zramswap` are Debian's packaging of zram, not a generic
  Linux assumption; the device node `/dev/zram0` and
  `/sys/block/zram0/comp_algorithm` are the kernel's.
- `PRJ-12` — the run-level condition that skips this role entirely unless
  one side is configured lives with the play's role ordering, alongside the
  role's own two inclusion conditions that realise `SWAP-17`.
- `PRJ-9` — the pre-run configuration summary reports whether zram and disk
  swap are configured, which is the operator's chance to notice that a host
  is about to get swap it was not meant to have, or none when it was.

**What others may assume of this spec:**

- `VRFY` — post-bootstrap verification confirms swap state independently of
  this role's own in-run checks.
- `PRJ-25` — the disk swap chain is what makes a re-run quiet on this role:
  the allocation is skipped when `/swapfile` exists, which skips the format
  and the activation in turn, and the `/etc/fstab` entry is added only when
  the duplicate check finds none. The `0600` permission task is the one
  unconditional step, and it reports no change once the mode already
  matches.
