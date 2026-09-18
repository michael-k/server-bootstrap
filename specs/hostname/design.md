# Hostname — Design

## Approach

The role's hostname behaviour lives in one task file, `hostname.yml`,
imported conditionally from `system_config`'s `tasks/main.yml` — the same
file that unconditionally imports `time_sync.yml` for `TIME`. Three plain
tasks run in sequence when `system_hostname` is set: `ansible.builtin.hostname`
sets the running name and notifies a handler; `ansible.builtin.copy` writes
`/etc/hostname` for persistence; `ansible.builtin.lineinfile` keeps the
`127.0.1.1` line in `/etc/hosts` pointed at the same name. There is no
template and no dedicated defaults file section beyond the single
`system_hostname` variable, which also carries the guard that makes the
whole file a no-op.

## Implementation map

| Path | Realises |
|---|---|
| `roles/system_config/tasks/hostname.yml` | HOST-1, HOST-2, HOST-3 |
| `roles/system_config/tasks/main.yml` | HOST-4 |
| `roles/system_config/defaults/main.yml` | HOST-1, HOST-4 |
| `roles/system_config/handlers/main.yml` | HOST-1 |

## Key decisions

**Three tasks, not one.** `HOST-1` (the running hostname), `HOST-2`
(persistence to `/etc/hostname`) and `HOST-3` (`/etc/hosts` consistency) are
three independent facts about the host, each with its own failure mode if
skipped — a stale running name, a name that reverts on reboot, and a name
that resolves nowhere locally. Folding them into one task would not change
what runs, but it would hide that a change to one (say, dropping the
`/etc/hosts` line to "simplify" the role) silently drops a specific,
nameable guarantee rather than an unspecified part of "hostname handling".

**`/etc/hosts` is rewritten by line match, not by template.** The role does
not own the whole file — cloud-init and other entries in it are not this
role's concern — so `lineinfile` replaces only the `127.0.1.1` line by regexp
match, leaving every other line in `/etc/hosts` exactly as it was.

## Failure modes

- **`system_hostname` is malformed** (not a valid hostname per RFC 1123).
  Nothing in this role validates the value before it reaches
  `ansible.builtin.hostname`; the module itself is the only thing that could
  reject it, and this spec does not verify that it does.
- **The "Verify hostname persistence" handler is effectively inert.** It
  runs `hostname` and registers the output as `hostname_check`, but nothing
  reads that variable afterward — there is no assertion and no display of
  it. It neither confirms `HOST-1` succeeded nor fails the run if it did not;
  see the findings note for this task for the full detail.
- **`/etc/hosts` already has no `127.0.1.1` line, or has more than one.** The
  `lineinfile` task only replaces a line matching `^127\.0\.1\.1\s+`; if no
  line matches, `lineinfile` appends one instead, which is the intended
  outcome and not a failure. Ansible's own `lineinfile` semantics on a file
  with more than one matching line are outside this role's control.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task here needs root privilege to change the running
  hostname and to write `/etc/hostname` and `/etc/hosts`.
- `PRJ-4` — the file paths and permissions this spec writes (`/etc/hostname`
  at `0644`, the `127.0.1.1` convention) are Debian's, not a generic Linux
  assumption.

**What others may assume of this spec:**

- `PRJ-9` — the pre-run configuration summary reports the configured
  hostname; it reads the same `system_hostname` variable this spec acts on,
  rather than the host's actual running name.
- `VRFY` — post-bootstrap verification checks the running hostname against
  `system_hostname` independently of anything in this spec.

**Shared role directory with `TIME`:** `roles/system_config/` holds both
this spec's task file (`hostname.yml`) and `TIME`'s (`time_sync.yml`),
imported from the same `tasks/main.yml` and sharing one `defaults/main.yml`
and one `handlers/main.yml`. This is acceptable because the two capabilities
never touch each other's code path: `hostname.yml`'s guard is
`system_hostname is defined and system_hostname | length > 0`, `time_sync.yml`
is imported unconditionally and switches on the unrelated
`time_sync_service` variable, and neither task file references a variable or
a handler the other defines. The shared directory is a historical grouping
of two small "system configuration" concerns bundled at the role level, not
a coupling between what they do — each spec cites only its own task file,
and this spec's rewrite of the legacy `Requirement 6.x` citations leaves
every `Requirement 12.x` citation in the same directory untouched, for
Task 11 (`TIME`) to rewrite on its own.
