# Time Synchronization — Design

## Approach

The role's time-sync behaviour lives in one task file, `time_sync.yml`,
imported unconditionally from `system_config`'s `tasks/main.yml` — unlike
`HOST`'s `hostname.yml`, which is imported only when `system_hostname` is
set. Every task in the file is itself guarded on `time_sync_service`, so
exactly one of two parallel branches (chrony, systemd-timesyncd) actually
does anything on a given run: install the package (chrony only — timesyncd
ships with systemd), stop and disable the other candidate service, template
its configuration file, enable and start it, then run a status command and
display its output. Each branch's template-deployment task notifies its own
restart handler, which fires only when the rendered configuration changed.

## Implementation map

| Path | Realises |
|---|---|
| `roles/system_config/tasks/time_sync.yml` | TIME-1, TIME-2, TIME-4, TIME-5 |
| `roles/system_config/templates/chrony.conf.j2` | TIME-1, TIME-3 |
| `roles/system_config/templates/timesyncd.conf.j2` | TIME-1, TIME-3 |
| `roles/system_config/defaults/main.yml` | TIME-1, TIME-3 |
| `roles/system_config/handlers/main.yml` | TIME-1 |

## Key decisions

**chrony is the default, not systemd-timesyncd.** chrony ships with its own
drift file (`driftfile /var/lib/chrony/drift`) that lets it estimate the
host's hardware clock's own rate of drift and correct for it between polls,
a refinement systemd-timesyncd's simpler SNTP client does not attempt.
chrony's `makestep` also steps the clock immediately on a large initial
offset rather than only slewing it, which matters on a freshly booted VPS
whose clock can start out seconds or minutes wrong. systemd-timesyncd
remains a supported, lighter alternative — `time_sync_service` exists
precisely so a host that does not need chrony's accuracy can use it instead
— but the default favours the service built specifically for accurate time
synchronization over the one built into an init system for a simpler case.

**One task file with two fully-guarded branches, not two task files.**
`hostname.yml` is imported conditionally as a whole; `time_sync.yml` cannot
be, because it always has work to do (`time_sync_service` always has a
value). Splitting it into `chrony.yml` and `timesyncd.yml`, each imported
under its own `when`, was rejected: the two branches already share nothing
but the file they live in, so a split would trade one guarded file for two,
with no guard removed and no logic simplified.

**Verification is a status query, not an assertion.** The task that runs
`chronyc tracking` or `timedatectl timesync-status` registers the output and
displays it, but does not evaluate it — see `TIME-6`'s `**Traceability:**`
note. This was a deliberate choice to document rather than to fix: the
"Verify … synchronisation status" task names promise more than the
`ansible.builtin.debug` step after them delivers, and `TIME-6` is written to
state the property this spec should have, not to describe the status quo as
sufficient.

## Failure modes

- **`ntp_servers` names only unreachable servers.** Both service branches
  will still install, configure, enable and start successfully — none of
  `TIME-1`, `TIME-4` or `TIME-5` depend on network reachability — and the
  clock will simply never synchronize. `TIME-6`'s pending status means
  nothing in this role's own tasks catches that outcome.
- **The synchronization check is read, not enforced.** As `TIME-6`
  documents, a "Not synchronised" chrony status or an equivalent
  not-yet-synced timesyncd status does not fail the run; it is visible only
  in the play's `debug` output, which an operator has to read.
- **`time_sync_service` is set to a value other than `"chrony"` or
  `"timesyncd"`.** Every task in the file guards on an equality check
  against one of those two literals; a third value causes every task to
  skip, leaving the host with no time synchronization service installed,
  enabled or started at all, and no task reporting a failure — the run
  simply does nothing and reports success.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task here needs root privilege to install packages, write
  `/etc/chrony/chrony.conf` or `/etc/systemd/timesyncd.conf`, and manage
  services via systemd.
- `PRJ-4` — chrony and systemd-timesyncd, the package names, and the systemd
  unit management this spec relies on are Debian's, not a generic Linux
  assumption.

**What others may assume of this spec:**

- `VRFY` — post-bootstrap verification checks time synchronization
  independently of this spec's own (non-asserting) status display.

**Shared role directory with `HOST`:** `roles/system_config/` holds both
this spec's task file (`time_sync.yml`) and `HOST`'s (`hostname.yml`),
imported from the same `tasks/main.yml` and sharing one `defaults/main.yml`
and one `handlers/main.yml`. The two capabilities never touch each other's
code path: `time_sync.yml` is imported unconditionally and switches on
`time_sync_service`, `hostname.yml`'s guard is
`system_hostname is defined and system_hostname | length > 0`, and neither
task file references a variable or a handler the other defines. This spec
cites only `time_sync.yml`'s own tasks, the two time-sync handlers, and the
`time_sync_service`/`ntp_servers` portion of the shared defaults file,
leaving every `HOST-N` citation in the same directory exactly as Task 10
left it.
