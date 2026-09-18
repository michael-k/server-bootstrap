# Networking — Requirements

**Prefix:** `NET`

## Purpose

This spec covers giving a target host a static, globally routable IPv6
address through netplan, alongside the DHCPv4 address the host already gets
from its provider. It exists for providers — IONOS is the motivating case —
whose IPv6 delegation is not reliably obtained through DHCPv6 or SLAAC alone,
so a fixed address and a fixed gateway have to be written to the host's own
network configuration instead. The capability is optional and additive: a
host that never sets a static address is not a subject of this spec at all.

## Scope

### In scope

- The no-op path when no static IPv6 address is configured.
- The netplan configuration written when a static IPv6 address is configured:
  DHCPv4 alongside the static address, and which interfaces it targets.
- The default gateway used for the static address, and its overridability.
- The format a static IPv6 address must be supplied in.
- The ownership and permissions of the deployed netplan file.
- Applying a changed netplan configuration, and only a changed one.
- Confirming that a global IPv6 address actually exists once the
  configuration has been applied.
- Whether applying the configuration can strand the connection Ansible is
  using to run the play.

### Out of scope

- The provider's own DHCPv4 and DHCPv6/SLAAC behaviour, which this spec
  neither configures nor verifies beyond enabling DHCPv4 alongside the static
  address.
- Firewall rules governing traffic to the resulting address, owned by `FW`.
- Tailscale's own addressing, owned by `TS`.
- The host's name, owned by `HOST`.
- Where this capability sits relative to the rest of the run, owned by
  `PRJ-12`.

## Security invariants

**Upholds:** INV-9
**Relies on:** INV-4 — a reachable address is only useful to an attacker if
the firewall admits it.
**Allowances claimed:** none

INV-9 is upheld by `NET-1` and `NET-6`: a host with no static address
configured is left untouched, and a configured host has its netplan file
reapplied only when the rendered configuration actually changes, rather than
unconditionally on every run.

This spec does not itself keep the resulting address from being reached — that
is what INV-4's default-deny firewall does. Making an interface globally
reachable and leaving it ungoverned would be exactly the exposure INV-1
forbids; this spec's job ends at making the address exist, and it relies on
`FW` to decide what may reach it.

## Requirements

### NET-1 — No-op without a configured static address

THE Bootstrap SHALL leave a host's network configuration exactly as the
provider delivered it when `static_ipv6_address` is not set.

**Why:** Most target hosts never set this variable, so "do nothing to
networking" is the default outcome for the whole fleet. A role that wrote some
netplan file regardless — even one that just re-encoded the existing DHCPv4
lease — would replace the provider's own cloud-init-generated network file on
every host, including ones nobody expects this role to touch. Nothing about a
missing or blank static address would fail loudly; it would surface only much
later, as a host whose network file nobody remembers Ansible now owns.
**Verified:** the netplan deployment task and the post-apply reachability
check both guard on `static_ipv6_address | default('') | length > 0`, and the
property suite asserts that guard is present on the deployment task and that
the variable defaults to the empty string.

### NET-2 — Netplan combines DHCPv4 with the static IPv6 address

WHERE `static_ipv6_address` is set, THE Bootstrap SHALL configure the host's
wired ethernet interfaces, matched as `en*`, with DHCPv4 enabled and
`static_ipv6_address` added to their static addresses.

**Why:** The providers this role targets still hand out a working DHCPv4
lease even when their IPv6 delegation is not reliable; dropping DHCPv4 in
favour of the static IPv6 address would trade a flaky IPv6 path for a broken
IPv4 one. That failure would not announce itself either — the host would
simply stop answering on IPv4, with nothing in the run's output pointing at
the netplan file as the cause.
**Verified:** the netplan template enables `dhcp4` on an ethernet stanza
matched to `en*` and appends `static_ipv6_address` to that stanza's
`addresses` list; the property suite asserts the DHCPv4 flag, the interface
match, and the address variable's use are each present.

### NET-3 — Gateway defaults to the provider's, overridable

THE Bootstrap SHALL route the static IPv6 address's default route through
`static_ipv6_gateway`, defaulting to `fe80::1`.

**Why:** `fe80::1` is the link-local next-hop IONOS's network expects. A host
on a different provider that inherited this default without overriding it
would still look fully configured — address assigned, default route present —
while every packet leaving the local segment is silently dropped at a gateway
that does not exist on that network. Making the value configurable is what
keeps a provider-specific default from becoming a provider-specific failure
everywhere else.
**Verified:** the netplan template's default route uses `static_ipv6_gateway`
as its `via` address, and the role's defaults set it to `fe80::1`; the
property suite asserts both.

### NET-4 — Address supplied with its prefix length

THE Bootstrap SHALL document, in the role's default variables, that
`static_ipv6_address` must be supplied as an address together with its prefix
length.

**Why:** netplan's `addresses` list takes CIDR-notation entries. Get the
prefix length wrong — or a provider-issued address pasted in without one — and
`netplan apply` does not necessarily fail: the underlying network
configuration can be silently rejected or misapplied by the renderer, leaving
the interface with no usable static address while the task that deployed the
file reports success. There is no schema validation in this role to catch a
malformed value before it reaches the host, so the format the value must take
is the one thing standing between a working address and `NET-7` catching the
failure after the fact.
**Verified:** the role's default variables document the required format
inline, with a concrete address-and-prefix example.

### NET-5 — Netplan file ownership and mode

THE Bootstrap SHALL deploy the netplan configuration file to
`/etc/netplan/50-cloud-init.yaml` owned by root with mode `0600`.

**Why:** The deployed file is the host's active network and routing
definition, and it fully replaces whatever cloud-init generated at first
boot. A mode that let any account other than root read or write it would let
a compromised low-privilege account silently redirect the host's default
route or overwrite its address the next time netplan reconciles — netplan
applies whatever the file says, with no distinction between an operator's
change and anyone else's.
**Verified:** the template deployment task sets `owner: root`, `group: root`
and `mode: "0600"` on the destination; the property suite asserts the `0600`
mode literal is present.

### NET-6 — netplan apply is triggered solely by a configuration change

THE Bootstrap SHALL trigger `netplan apply` solely by a change to the
deployed netplan configuration file.

**Why:** A file written to disk without an apply step leaves the running
network stack on its previous configuration until the next unrelated reboot;
the play would report success while the static IPv6 address does not exist on
the interface yet, and nothing says so. Applying unconditionally on every run,
in turn, would mean an already-converged host bounces its own network
interface on every idempotent re-run for no reason — a needless risk to the
very connection the run depends on, and a violation of INV-9's spirit even
where it does not change the end state.
**Verified:** the template deployment task notifies the "Apply netplan
configuration" handler, which runs `netplan apply`, and a notified handler
fires only when its notifying task reports a change; the property suite
asserts the notification and the handler's command are both present.

### NET-7 — Global IPv6 reachability confirmed after applying

THE Bootstrap SHALL fail the run if no global-scope IPv6 address is present on
the host within the retry window after applying the static configuration.

**Why:** A syntactically valid netplan file can still fail to produce a
working address — a wrong prefix length, an interface match that misses the
real NIC name, a route that never comes up — and none of those failure modes
necessarily makes `netplan apply` itself exit non-zero. Without this check,
the run would report success while the host has silently lost the IPv6
reachability it was just told to configure, discoverable only whenever
something later depends on it.
**Verified:** the "Wait for public IPv6 address" task polls
`ip -6 addr show scope global` with retries and fails once those retries are
exhausted without a match; the property suite asserts the task exists.

### NET-8 — Applying the configuration must not strand the running connection

THE Bootstrap SHALL leave the Ansible connection to the target host intact
after applying a changed netplan configuration.

**Why:** `netplan apply` can restart the interface carrying the very SSH
connection Ansible is using to run the play. A wrong static address or
gateway is exactly the mistake `NET-3` and `NET-4` exist to prevent, and if
one gets through anyway, the moment `netplan apply` runs is where it stops
being a configuration error and starts being a host nobody can reach — the
most consequential silent failure this feature can produce, and the textbook
case of an operator locked out mid-run.

**Traceability:** pending — the handler runs `netplan apply` synchronously
via `ansible.builtin.command`, with no async/poll pattern, no pre-apply
connectivity check, no use of `netplan try` (which reverts automatically if
not confirmed within a timeout), and no rescue block. Nothing in the role
verifies, or attempts to preserve, the connection Ansible is using to run the
play; if the applied configuration breaks reachability, the run simply hangs
or fails at that task with no distinguishable diagnosis and no automatic
recovery.
