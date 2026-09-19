# Logging — Design

## Approach

The role is a single task file with three tasks and no branching: render
`journald.conf.j2` to `/etc/systemd/journald.conf` (`LOG-1`, `LOG-2`,
`LOG-3`), create `/var/log/journal` with restricted ownership and mode
(`LOG-5`), and flush handlers immediately so a changed configuration restarts
journald within the same run rather than waiting for the play to end
(`LOG-4`). The template's content is pinned by two defaults,
`journald_max_disk_usage` and `journald_max_retention_time`; there is no
enabling variable, so journald is configured identically on every host this
role runs against.

## Implementation map

| Path | Realises |
|---|---|
| `roles/logging/tasks/main.yml` | LOG-1, LOG-2, LOG-3, LOG-4, LOG-5 |
| `roles/logging/defaults/main.yml` | LOG-2, LOG-3 |
| `roles/logging/templates/journald.conf.j2` | LOG-1, LOG-2, LOG-3 |
| `roles/logging/handlers/main.yml` | LOG-4 |

## Key decisions

**`500M` and `1month` as the defaults.** At up to `500M` — journald
XZ-compresses rotated journal files by default, so the on-disk cost is
usually well under the configured ceiling — that is a bounded, predictable
slice of a small VPS's disk, and a month of that volume is generally enough
to cover the kind of incident whose first sign appears weeks after the event,
without requiring every host to have its cap raised just to get useful
history. The cost is real: it is disk committed to logs rather than to
anything else, on hosts where disk is often the tightest resource. Either
default is one inventory line to override, but the built-in trade has to
start small enough that no host is silently made to spend `500M` on logging
it never asked for.

**Whichever cap is hit first wins.** `LOG-2`'s disk cap and `LOG-3`'s
retention time are independent settings journald enforces together, not in
sequence: if logging volume is high enough to hit the disk cap before a
month elapses, entries are discarded to stay under the disk budget
regardless of their age, so the "one month" `LOG-3` promises is conditional
on the `LOG-2` budget lasting that long. Neither this role nor its tests
detect that condition — see Failure modes.

**Persistent storage set explicitly, not left to journald's `auto`
default.** `Storage=persistent` is set unconditionally rather than relying
on `/var/log/journal`'s existence to flip journald's own `auto` default into
persistent mode, so persistence does not depend on task ordering between the
template deploy and the directory-creation task. This makes `LOG-5`'s
directory task, in one sense, redundant with what journald would create for
itself the moment `Storage=persistent` takes effect — but the task's value is
that it re-asserts ownership and mode on every run, rather than only at
whatever moment journald happened to first create the directory on its own,
which is what makes the permissions declarative (`INV-9`) instead of an
accident of first-boot timing.

**Restart handled by an immediate flush, not left for the next reboot.**
Mirroring `FS-5`'s pattern for mount options, a configuration change here is
made to take effect within the same run via `ansible.builtin.meta:
flush_handlers`, rather than trusting whatever later point in the play
happens to flush handlers naturally. Unlike `FS-6`'s gap for an
already-active mount unit, there is no equivalent gap here: `systemd`'s
`state: restarted` is unconditional, so it always restarts a running
`systemd-journald`, active or not.

## Failure modes

- **Neither `LOG-2` nor `LOG-3` is enforced independently.** journald applies
  both limits together, so a burst of noisy logging can push entries out of
  the journal well before the configured retention time elapses. Nothing in
  the role, and no test, distinguishes "discarded because retention expired"
  from "discarded because the disk cap was reached early" — an operator
  relying on the retention default to bound how far back they can look has no
  way to learn, short of reading the journal's actual disk usage, that the
  cap reached its limit first.
- **`LOG-1` through `LOG-3` are verified as rendered configuration, never as
  observed journald behavior.** Every assertion reads the template or the
  deployed file for the expected directive; nothing starts journald against a
  small disk cap and confirms it actually stops growing the journal at that
  size, or against a short retention time and confirms old entries are
  actually gone. The one behavioral test that touches a live journald writes
  a single entry and reads it back in the same run — it demonstrates logging
  works, not that any of the three limits are enforced.
- **`LOG-5`'s reassertion is not exercised by any test.** The directory task
  is unconditional, the same pattern `SWAP-12` uses for `/swapfile`'s mode,
  so it is expected to repair a manually drifted owner, group or mode on the
  next run. No test drifts the permission and checks that a re-run corrects
  it — the convergence is architectural, not demonstrated.
- **The shared unit-test module originally carried a legacy `11.4` citation
  on a test that is not about logging.** `tests/unit/test_system_services.py`'s
  `TestFail2banConfiguration::test_template_deploy_notifies_restart` loads and
  asserts on the `fail2ban` role's own "deploy fail2ban jail configuration"
  task, not `logging`'s; its original docstring read `"Req 11.4 pattern"`
  purely to name a notify-on-deploy pattern the two roles happen to share,
  never to claim it verified anything about journald. Rewriting that bare
  `11.4` mechanically to `LOG-4` would have created exactly the wrong
  citation this plan exists to prevent: a spec-check-visible `LOG-4` citation
  from a test whose own text denied verifying `LOG-4`. The fix was to drop
  the numeric citation from that test entirely rather than launder it — the
  docstring now names the shared pattern in plain English and points at
  `fail2ban` as its owner. `F2B` has since been written, and that docstring
  now carries `F2B-15` — fail2ban's own requirement for the pattern — which
  is the citation it should always have had; what it still does not carry is
  any `LOG` citation, which was the point. This spec's `LOG-4`
  `**Verified:**` line never credited that test.
- **The task named "Ensure journald configuration directory exists" creates
  `/var/log/journal`, which is the journal's storage directory, not
  journald's configuration.** journald's configuration is the file
  `/etc/systemd/journald.conf`, deployed by a separate, preceding task. This
  reads as a misleading name rather than a substantive divergence — the task
  itself is what `LOG-5` describes, correctly, regardless of what it is
  called — and the plan's no-behavior-change rule means the name is recorded
  here rather than corrected, since an Ansible task name is visible playbook
  output that a rename would change.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task needs root privilege to write
  `/etc/systemd/journald.conf` and to create and `chown` `/var/log/journal`.
- `PRJ-4` — `journald` and the `systemd-journal` group are Debian's systemd
  stack, not a generic Linux assumption.
- `PRJ-12` — the run-level ordering that places this role relative to the
  rest of the play.

**What others may assume of this spec:**

- `SUDO`, `USR` — the audit trail `INV-7` requires for privilege escalation
  is only durable because this spec keeps journald's storage persistent;
  those specs decide what gets logged and by whom, this one keeps it around
  long enough to be read.
- `VRFY` — post-bootstrap verification re-confirms `Storage=persistent` in
  the deployed configuration, independently of this role's own template.
