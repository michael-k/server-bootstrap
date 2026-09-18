# Networking — Design

## Approach

The role is a single tasks file of two guarded tasks plus one handler. Both
tasks share the same `static_ipv6_address | default('') | length > 0`
condition, so the whole role collapses to a no-op with that one variable
unset. When it is set, the first task templates a netplan file and notifies a
handler that runs `netplan apply` only when the template changed; the second
task then polls for a global-scope IPv6 address, failing the run if one never
appears.

## Implementation map

| Path | Realises |
|---|---|
| `roles/networking/tasks/main.yml` | NET-1, NET-2, NET-5, NET-6, NET-7 |
| `roles/networking/templates/50-cloud-init.yaml.j2` | NET-2, NET-3 |
| `roles/networking/defaults/main.yml` | NET-1, NET-3, NET-4 |
| `roles/networking/handlers/main.yml` | NET-6 |

## Key decisions

**netplan, not `/etc/network/interfaces`.** The target platform (`PRJ-4`)
renders its network configuration through netplan and systemd-networkd; on a
Debian 13 cloud image there is no `ifupdown` in the boot path for a file under
`/etc/network/interfaces` to reach. Writing there would not fail — it would
be silently ignored by a renderer that never reads it, while the host kept
whatever netplan already had. netplan is also where cloud-init itself already
writes the host's boot-time network configuration, at the exact path this role
targets (`NET-5`); reusing that file's name means this role's definition is
the only one netplan sees, rather than a second file whose keys would have to
be reconciled against the provider's original one.

**The default gateway is provider-specific because the semantics it encodes
are.** `fe80::1` is not a generic default: it is IONOS's convention of routing
a statically-assigned prefix through a link-local next-hop rather than a
globally-addressed one. A provider that hands out a normal global gateway
address would need a different value entirely, which is exactly why
`static_ipv6_gateway` is a variable and not a literal in the template
(`NET-3`) — the default documents what this role was built against, not a
value expected to be universal.

**The reachability check is a separate task from the deploy task.** `NET-2`
states what gets written; `NET-7` states that writing it actually worked.
Folding the check into the deploy task would hide a real distinction: the
`ansible.builtin.template` task can only report whether the rendered file
differs from what is on disk, never whether the configuration it describes
came up. A `netplan apply` that silently produces no usable address needs a
task that looks at the running network stack, not the file, to catch it.

## Failure modes

- **`static_ipv6_address` is malformed** (missing or wrong prefix length).
  Nothing in this role validates the value before it reaches the template;
  the best case is `NET-7`'s reachability check catching the resulting
  absence of a global address and failing the run. The worst case is an
  address that is syntactically valid but wrong, which `NET-7` cannot
  distinguish from a correct one that happens to route badly.
- **`netplan apply` breaks the running connection.** `NET-8` states the
  requirement; this role does not currently guarantee it. See
  `specs/networking/requirements.md`'s `NET-8` for the honest status of this
  gap.
- **The reachability check exhausts its retries.** The run fails at that
  task with the host left on whatever netplan already applied — this is the
  designed outcome of `NET-7`, not a partial-configuration risk: the netplan
  file itself was already written and applied by the time this check runs.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — the deploy task, the apply handler and the reachability check all
  need root privilege; templating to `/etc/netplan/` and running `netplan
  apply` would fail otherwise.
- `PRJ-4` — the platform floor guarantees netplan and systemd-networkd are
  the host's network renderer, which is what makes writing to
  `/etc/netplan/` meaningful at all.

**What others may assume of this spec:**

- `FW` — governs what may reach the address this spec makes routable; this
  spec relies on `FW`'s default-deny posture (INV-4) rather than restricting
  reachability itself.
- `PRJ-12` — this role runs early in the fixed order, before Tailscale and
  SSH hardening, so a static IPv6 address (when configured) is in place
  before anything that might bind to it.
