# Filesystem Hardening Design

## Goal

Prevent execution of uploaded payloads from temporary directories by mounting `/tmp`, `/dev/shm`, and `/var/tmp` with `noexec,nosuid,nodev`.

## Approach

New Ansible role `filesystem_hardening` using systemd mount units. `/tmp` stays on disk (no tmpfs) to avoid RAM pressure on low-memory VPS instances.

## Mount Configuration

| Mountpoint | Unit Type | What | Where | Options |
|---|---|---|---|---|
| `/tmp` | `tmp.mount` | bind `/tmp` | `/tmp` | `bind,rw,noexec,nosuid,nodev` |
| `/dev/shm` | `dev-shm.mount.d/hardening.conf` | drop-in override | `/dev/shm` | `rw,nosuid,nodev,noexec` |
| `/var/tmp` | `var-tmp.mount` | bind `/tmp` | `/var/tmp` | `bind,rw,noexec,nosuid,nodev` |

### Why bind-mount for /tmp

A tmpfs `/tmp` consumes RAM. On a 512MB VPS this is unacceptable. A bind-mount of `/tmp` onto itself with restricted options keeps `/tmp` on the root filesystem while adding security restrictions. No RAM cost.

### Why bind-mount /var/tmp to /tmp

Eliminates `/var/tmp` as a bypass path. Traditional `/var/tmp` persists across reboots, but on a VPS with no batch jobs depending on this, the trade-off is acceptable.

### Why drop-in override for /dev/shm

`/dev/shm` is already mounted as tmpfs by systemd. A drop-in `.conf` file in `/etc/systemd/system/dev-shm.mount.d/` adds the restrictive options without replacing the entire unit. Note: the `Options=` directive in a drop-in fully replaces the base unit's options, so we include the complete desired option set (`rw,nosuid,nodev,noexec`).

### Interaction with systemd's packaged tmp.mount

Debian ships a `tmp.mount` unit (usually masked or inactive) that mounts `/tmp` as tmpfs. Placing our custom `tmp.mount` in `/etc/systemd/system/` overrides the packaged unit, which is the standard systemd override mechanism. The packaged unit is effectively masked by the custom one.

## Role Structure

```
roles/filesystem_hardening/
├── defaults/main.yml           # empty — intentionally no configuration (see "No Configuration Variables")
├── tasks/main.yml              # deploy units, daemon-reload, start/enable mounts
├── templates/
│   ├── tmp.mount.j2            # /tmp bind-mount unit
│   ├── dev-shm.mount.conf.j2  # /dev/shm drop-in override
│   └── var-tmp.mount.j2       # /var/tmp bind-mount to /tmp
└── handlers/main.yml           # systemctl daemon-reload
```

## Playbook Placement

Inserted after `system_updates` and before `system_config` in `site.yml`. Existing role comments (#2 through #10) are renumbered accordingly. Early placement ensures hardened mounts are active before other roles write to `/tmp`.

```yaml
- role: system_updates
  tags: ["system_updates", "updates"]

- role: filesystem_hardening
  tags: ["filesystem_hardening", "filesystem", "hardening", "security"]

- role: system_config
  tags: ["system_config", "hostname", "time"]
```

## Systemd Unit Details

### tmp.mount

```ini
[Unit]
Description=Hardened /tmp mount
Conflicts=umount.target
Before=local-fs.target umount.target
After=swap.target

[Mount]
What=/tmp
Where=/tmp
Type=none
Options=bind,rw,noexec,nosuid,nodev

[Install]
WantedBy=local-fs.target
```

Default dependencies are kept (no `DefaultDependencies=no`) so systemd provides the implicit `After=sysinit.target` ordering, ensuring the root filesystem is mounted read-write before the bind-mount is attempted.

### dev-shm.mount.d/hardening.conf

```ini
[Mount]
Options=rw,nosuid,nodev,noexec
```

This fully replaces the base unit's `Options=` line. We include `rw,nosuid,nodev` (which Debian's base unit already sets) plus `noexec` (our addition). This makes the drop-in self-contained and correct regardless of what the base unit specifies.

### var-tmp.mount

```ini
[Unit]
Description=Hardened /var/tmp mount (bind to /tmp)
Conflicts=umount.target
Before=local-fs.target umount.target
After=tmp.mount
Requires=tmp.mount

[Mount]
What=/tmp
Where=/var/tmp
Type=none
Options=bind,rw,noexec,nosuid,nodev

[Install]
WantedBy=local-fs.target
```

Default dependencies are kept for the same boot-ordering reasons as `tmp.mount`.

## Task Sequence

The `tasks/main.yml` follows this order:

1. **Deploy `/tmp` mount unit** — `ansible.builtin.template` to `/etc/systemd/system/tmp.mount`, notify `daemon-reload` handler
2. **Create `/dev/shm` drop-in directory** — `ansible.builtin.file` to create `/etc/systemd/system/dev-shm.mount.d/`
3. **Deploy `/dev/shm` drop-in override** — `ansible.builtin.template` to the drop-in directory, notify `daemon-reload` handler
4. **Deploy `/var/tmp` mount unit** — `ansible.builtin.template` to `/etc/systemd/system/var-tmp.mount`, notify `daemon-reload` handler
5. **Flush handlers** — ensures daemon-reload runs before enabling mounts
6. **Enable and start `tmp.mount`** — `ansible.builtin.systemd` with `enabled: true, state: started`
7. **Remount `/dev/shm`** — `ansible.builtin.command: mount -o remount /dev/shm` only when the drop-in template changed (using a register + when pattern)
8. **Enable and start `var-tmp.mount`** — `ansible.builtin.systemd` with `enabled: true, state: started`

Using `state: started` (not restarted) means already-active mounts with correct options are left alone. The `remount` approach for `/dev/shm` avoids unmounting an active tmpfs.

## Idempotency

- Template tasks only notify handlers when files actually change (Ansible's built-in behavior)
- `state: started` on mount units is a no-op if the mount is already active
- `/dev/shm` remount only triggers when the drop-in template changes (registered variable)
- Safe to re-run: no disruption on subsequent executions

## Handlers

Single handler: `Reload systemd daemon` using `ansible.builtin.systemd: daemon_reload: true`, triggered when any unit file changes. Follows the same pattern as existing roles.

## Verification

Three new checks in `tests/verify_bootstrap.yml`:

1. `/tmp` has `noexec,nosuid,nodev` in mount output
2. `/dev/shm` has `noexec,nosuid,nodev` in mount output
3. `/var/tmp` has `noexec,nosuid,nodev` in mount output

Each check uses `ansible.builtin.command: findmnt -n -o OPTIONS <mountpoint>` and asserts the required options are present.

## Property Tests

New file `tests/property/test_filesystem_hardening_properties.py` covering:

- All three mountpoints include `noexec`, `nosuid`, `nodev` in generated options
- Options explicitly include `rw` (not left implicit)
- `/var/tmp` unit depends on `tmp.mount` (After + Requires)
- `/dev/shm` override is a drop-in conf, not a full unit replacement
- Bind-mount units use `Type=none` with `bind` option
- Neither `tmp.mount` nor `var-tmp.mount` sets `DefaultDependencies=no`
- Handler triggers on unit file changes
- Negative test: a template missing `noexec` fails the options check

## Recovery

If mount configuration is incorrect and `/tmp` becomes unusable after reboot, recovery involves booting into rescue mode and removing or fixing the unit files in `/etc/systemd/system/`. This is standard for systemd mount changes.

## No Configuration Variables

This role requires no user-facing configuration. It always applies the same restrictions. This keeps it simple and eliminates misconfiguration risk. The empty `defaults/main.yml` reflects this intentional decision.
