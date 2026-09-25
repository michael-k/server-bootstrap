# Firewall — Requirements

**Prefix:** `FW`

## Purpose

This spec is the host's outer boundary: the one place that decides which
packets reach a listening socket at all. Every other access control in the
project acts on traffic that has already been admitted here — sshd
authenticates a connection the firewall let through, fail2ban bans a source
that already reached the daemon, PAM and sudo act on a session that already
exists. A default-deny input policy is what makes the rest of the project's
hardening a defence of the few paths that are open rather than an argument
about every port a provider image might have left listening.

The posture is deliberately small: drop everything inbound, accept the
replies to what this host started, accept loopback and ICMP, and open
exactly one service — SSH — by one of three mutually exclusive routes, plus
the UDP port the tailnet that route runs over needs for itself.
Without this spec a bootstrapped host would carry Debian's empty ruleset,
which filters nothing at all: every socket any package opened would be
reachable from the internet, and `INV-1` would be a statement about sshd
alone rather than about the host. With it, each hole this spec opens in
the input chain has a row in the exposure registers of
`specs/project/security-invariants.md`, and a rule a purpose repo adds
through the drop-in directory this spec provides is registered by that
repository (`PRJ-28`).

## Scope

### In scope

- The single dual-stack `inet` table, and the decision to express both
  address families in one table rather than two.
- The three base chains and their policies: input and forward default to
  drop, output to accept.
- The unconditional input accepts that make the drop policy usable:
  established and related connections, loopback traffic, ICMPv4 and ICMPv6.
- The tailnet-only SSH rule, the interface name it matches, and the
  WireGuard UDP port that must be open for that tailnet to exist.
- The open SSH rule taken when neither Tailscale nor port knocking is
  configured, and the port both SSH rules name.
- Replacing the loaded ruleset on every deployment rather than adding to it.
- The deployed file: its path, ownership and mode, and the nftables service
  that reads it at boot and on reload.
- The drop-in directory and the `include` that makes it the supported
  extension point for purpose-specific repositories.

### Out of scope

- The port-knocking branch of the ruleset — the knock sets, the staged
  accept rules, the explicit drop of the knock ports, the set-membership SSH
  accept and the four `firewall_port_knocking_*` defaults. They live in this
  role's files but belong to the port-knocking spec, which owns them as
  `KNOCK-1` through `KNOCK-11`. This spec states only that a third branch
  exists and that it is mutually exclusive with the other two.
- Choosing the SSH port. `SSH-13` owns it; `FW-14` consumes it so that the
  rule and the daemon cannot name different ports.
- Bringing up the tailnet, publishing its addresses and proving it works
  before anything is narrowed to it — owned by `TS`.
- Binding sshd itself to the tailnet addresses — owned by `SSH-18`. That
  narrowing and `FW-10` are two independent controls on the same path, not
  one control stated twice.
- Banning individual source addresses after repeated authentication
  failures — owned by the fail2ban spec, which writes its own table into the
  same kernel ruleset this spec flushes.
- Restoring public reachability on a host whose tailnet has broken — owned
  by the emergency-access spec, whose break-glass script edits `FW-10`'s
  rule in the deployed ruleset and reloads the service itself. This spec
  provides the file and the reload it uses; it does not provide the
  recovery, and nothing here detects that recovery is needed. That the
  script edits the very file `FW-16` re-renders makes the two specs'
  interaction a failure mode worth naming, but it is named in `design.md`,
  and the script and its gating belong to that spec.
- Any rule a purpose repository adds through the drop-in directory. This
  spec owns the mechanism and guarantees the rules are loaded; it says
  nothing about what they open. What a purpose repository owes for each
  hole it opens is `PRJ-28`'s.
- Confirming after the fact that the deployed ruleset is the one the kernel
  is enforcing — owned by `VRFY`.

## Security invariants

**Upholds:** INV-1, INV-4, INV-9, INV-10
**Relies on:** INV-6, INV-8
**Allowances claimed:** ALW-2, ALW-4, ALW-5, ALW-6, ALW-7, ALW-8

`INV-4` is this spec, almost word for word: `FW-2` is the single `inet`
table that makes one policy govern both address families, and `FW-3` and
`FW-4` are the two `policy drop` statements it names. The invariant's
"no separate, looser IPv6 path" clause is a property of the table's
construction rather than of any rule — there is no second table for one
family to diverge in.

`INV-1` and `INV-10` are upheld by registering each hole this spec opens,
not by opening none. `INV-1` forbids a public exposure that no allowance
in the public exposure register covers, and `INV-10` forbids a tailnet
exposure that no allowance in the tailnet exposure register covers, so each
requirement here that opens a hole claims its row. On the public side,
`FW-12` claims `ALW-2` for the WireGuard port, because Tailscale's WireGuard
traffic arrives from the internet and the tunnel that `FW-10` narrows SSH
to cannot exist without it. `FW-13` claims `ALW-4` for SSH on every
interface on a host with neither a tailnet nor a knock sequence, which is
the configuration where the alternative is no access at all. `FW-8` and
`FW-9` claim `ALW-5` for ICMP. On the tailnet side, `FW-10` claims `ALW-6`
for SSH on the tailnet interface, and `FW-8`, `FW-9` and `FW-12` claim
`ALW-7` and `ALW-8`, because their rules name no interface and so match the
tailnet interface too. Which tailnet peers may send at all is the tailnet's
own policy, which this repository does not manage.

`INV-9` is upheld by `FW-15` and `FW-16` together. `FW-16` deploys the
ruleset from a template that converges to the same file on every run, and
`FW-15` makes that file the whole of what the kernel holds rather than the
newest layer on top of it — so there is no state a previous run established
that a re-run could leave partly in place, and no rule an earlier revision
created that could outlive its own deletion. The convergence is a property
of the two together: a declarative deploy with no flush would accumulate,
and a flush with an imperative deploy would have nothing reliable to flush
to.

The reliance on `INV-8` is `FW-10`'s. Narrowing SSH to one interface is not
reversible from the network: if the tailnet interface is absent, renamed or
not carrying traffic, the rule matches nothing and the host has no open SSH
path. Nothing in this role checks any of that — `FW-11` takes the interface
name on trust from a variable. The safety argument is entirely `TS-15`,
`TS-16` and `TS-21`, which establish that the interface exists, that the
client is `Running` and that traffic crosses it, together with `TS-22`,
which requires all of that to have finished before the narrowing is applied.
The address checks `TS` also performs are not part of this argument, because
this spec matches an interface and never an address.

`INV-6` is the last resort behind that reliance, and this spec earns it by
keeping the narrowing in a file rather than in kernel state. The
emergency-access spec's script edits `FW-10`'s rule in `/etc/nftables.conf`
directly, reloads the service, and needs no network to do either, so a host
whose tailnet has failed can be reopened from its provider console alone.
The obligation that creates on this spec is recorded in `design.md`: the
script matches `FW-10`'s rendered rule as literal text, so that text is an
interface other code depends on.

## Requirements

### FW-1 — nftables is the packet filter

THE Bootstrap SHALL install the `nftables` package on every host.

**Why:** the ruleset this spec deploys is nftables syntax loaded by the
nftables service, and neither exists without the package. Debian ships it
with no ruleset of its own, so installing it changes nothing by itself —
which is the point: the filtering begins with the file `FW-16` deploys and
not a moment earlier.
**Verified:** `test_property_17_nftables_dual_stack_configuration` asserts
the string `name: nftables` appears in the tasks file. That same string
appears on the two service tasks in that file as well, so the assertion does
not distinguish the package task from them.

### FW-2 — One dual-stack `inet` table

THE Bootstrap SHALL express the entire ruleset in a single `inet` table,
defining no separate IPv4-only or IPv6-only table.

**Why:** `INV-4` requires the drop policy to hold for both address families,
and the surest way to guarantee that is to leave no second place for one
family's rules to live. In an `inet` table a chain sees both families, so a
policy is written once and a rule is family-specific only where it says so
(`FW-8` and `FW-9` are the only two of this spec's rules that do; the
port-knocking branch adds more of its own). Two tables would be two
rulesets to keep in agreement forever, and the failure mode of that
divergence — IPv6 quietly looser than IPv4 — is invisible to anyone testing
over IPv4.
**Verified:** `test_uses_inet_family` and `test_inet_table_covers_both_stacks`
assert `table inet filter` is present in the rendered output and that
`table ip filter` and `table ip6 filter` are not;
`test_property_17_nftables_dual_stack_configuration` makes the same three
assertions against the raw template text. The rendered ruleset for each of
the three SSH branches was also checked to parse with `nft -c -f`.

### FW-3 — Input chain defaults to drop

THE Bootstrap SHALL give the input chain a default policy of `drop`.

**Why:** this is the whole of the default-deny posture `INV-4` names and the
premise `INV-1` rests on. A policy decides every packet no rule matched, so
with `drop` a service this spec forgot — a package that opened a socket, a
daemon an operator installed later — is refused rather than reachable. The
alternative default would make the ruleset a list of things to block, which
can only ever be as complete as the author's imagination.
**Verified:** `test_input_chain_default_drop` asserts
`hook input priority 0; policy drop;` is in the rendered output, and
`test_property_18_nftables_stateful_firewall_rules` asserts a `policy drop`
line follows `chain input` in the template. `verify_bootstrap.yml`'s
`Verify FW-3: NFTables default input policy is drop` matches
`type filter hook input.*policy drop` against a live `nft list ruleset`,
and the integration suite's
`test_non_ssh_port_blocked_despite_listening_service` starts a real listener
on port 8080 inside the VM and fails if it can be reached, while
`test_only_ssh_reachable_after_knock` requires ten common ports to be
unreachable. Those two are aimed at the policy itself. Other integration
tests — an SSH connection refused before a knock, refused after a knock on a
tailnet-restricted host, or refused from outside the tailnet, among them —
also depend on this policy to drop the packet, but each is written as
evidence that a branch's access control refuses what it should, and would be
read that way by anyone diagnosing its failure.

### FW-4 — Forward chain defaults to drop

THE Bootstrap SHALL give the forward chain a default policy of `drop`, and
add no rule to it.

**Why:** a bootstrapped host is an endpoint, not a router. `INV-4` names the
forward chain alongside the input chain because a host that forwards is a
path into networks behind it, and the exposure that creates is not visible
in any check of the host's own services. Leaving the chain empty rather than
writing an explicit drop rule keeps the guarantee a property of the chain's
construction: there is no rule to delete and no ordering to get wrong.
**Verified:** `test_forward_chain_default_drop` asserts
`hook forward priority 0; policy drop;` is in the rendered output, and
`test_property_18_nftables_stateful_firewall_rules` asserts a `policy drop`
line follows `chain forward` in the template. `verify_bootstrap.yml`'s
`Verify FW-4: NFTables default forward policy is drop` matches it against a
live ruleset. Nothing asserts the chain is empty, and nothing sends a
packet through it.

### FW-5 — Output chain accepts

THE Bootstrap SHALL give the output chain a default policy of `accept`.

**Why:** egress filtering is a policy this bootstrap does not attempt, and
an explicit `accept` says so rather than leaving the chain's behaviour to be
inferred. The chain is defined rather than omitted for the same reason
`SSH-18` always renders a `ListenAddress` pair: a stated default cannot
drift into some other value, and a later spec that wants to filter egress
has a chain to add rules to. What makes this safe on the inbound side is
`FW-6` — the replies to outbound connections come back through the input
chain, so an open output chain does not weaken the input policy.
**Verified:** `test_output_chain_defined` asserts only that `chain output {`
appears in the rendered output;
`test_property_18_nftables_stateful_firewall_rules` is the one test that
asserts a `policy accept` line follows `chain output`. Nothing checks it on
a live host.

### FW-6 — Established and related connections accepted

THE Bootstrap SHALL accept inbound packets belonging to an established or
related connection, before any service-specific rule.

**Why:** this is the rule that makes the firewall stateful, and without it a
`drop` input policy would break every outbound connection the host makes —
the reply to a DNS query, an `apt` download or a Tailscale handshake is an
inbound packet, and matching those by service would mean opening ports for
each. Placing it first is not only a performance choice, though most packets
do match it: an outbound-initiated exchange must not depend on the
conditional rules below, which differ between the three SSH branches.
**Verified:** `test_established_related_accepted` asserts
`ct state established,related accept` is in the rendered output;
`test_property_18_nftables_stateful_firewall_rules` asserts the same against
the template and that its line number is lower than the last line carrying
both `tcp dport` and `accept`. `verify_bootstrap.yml`'s
`Verify FW-6: NFTables allows established/related connections` matches
`ct state.*established.*related.*accept` against a live ruleset.

### FW-7 — Loopback traffic accepted

THE Bootstrap SHALL accept inbound packets arriving on the loopback
interface.

**Why:** local services address each other over `127.0.0.1` and `::1`, and
those packets traverse the input chain like any other. Under `FW-3`'s drop
policy, omitting this rule breaks local service communication in ways that
look like application faults rather than firewall faults. The rule matches
the interface rather than the address, so it covers both families at once
and cannot be satisfied by a remote packet forging a loopback source
address.
**Verified:** `test_loopback_accepted` asserts `iif lo accept` is in the
rendered output; `test_property_18_nftables_stateful_firewall_rules` asserts
the same against the template and that it precedes the last
`tcp dport`/`accept` line. `verify_bootstrap.yml`'s
`Verify FW-7: NFTables allows loopback traffic` matches `iif.*lo.*accept` or
`iifname.*lo.*accept` against a live ruleset.

### FW-8 — ICMPv4 accepted

THE Bootstrap SHALL accept inbound ICMPv4.

**Why:** ICMP is not optional traffic that happens to be useful for
diagnostics. Path MTU discovery depends on `fragmentation needed`, and a
host that drops it produces connections that establish and then hang on the
first large packet — a failure that looks like anything but a firewall rule.
Reachability testing is the lesser benefit. The exposure accepted in
exchange is that the host answers `ping`, which reveals that it exists;
against an address a provider assigned and an attacker can scan anyway, that
is worth the failures dropping ICMP causes. The rule names no
interface, so the exposure is registered twice: as `ALW-5` for public
sources and, on a tailnet host, as `ALW-7` for tailnet peers.
**Verified:** `test_icmp_rules_for_both_stacks` asserts
`ip protocol icmp accept` is in the rendered output, and
`test_property_17_nftables_dual_stack_configuration` asserts it against the
template. Nothing sends an ICMP packet to a bootstrapped host, and nothing
checks the live ruleset for the rule.

### FW-9 — ICMPv6 accepted

THE Bootstrap SHALL accept inbound ICMPv6.

**Why:** the IPv6 case is stronger than the IPv4 one, and `INV-4`'s "no
separate path for one family" cuts both ways — parity here means not
crippling one family rather than not loosening it. ICMPv6 carries neighbour
discovery and router advertisement, so dropping it does not degrade
diagnostics, it breaks IPv6 on the host outright: no neighbour resolution
and no address autoconfiguration, so a host that drops it cannot reach the
addresses it advertises it has. The rule is broad — every ICMPv6 type,
not just the load-bearing ones — which is the accepted cost of not
enumerating them. As with `FW-8`, the exposure is registered as `ALW-5`
and, on a tailnet host, as `ALW-7`.
**Verified:** `test_icmp_rules_for_both_stacks` asserts
`ip6 nexthdr icmpv6 accept` is in the rendered output, and
`test_property_17_nftables_dual_stack_configuration` asserts it against the
template. As with `FW-8`, nothing exercises it on a live host. Note that a
live `nft list ruleset` renders the rule as `ip6 nexthdr ipv6-icmp accept`,
so a future verification check must match the normalised spelling rather
than the one written here.

### FW-10 — SSH accepted only on the tailnet interface when Tailscale is enabled

THE Bootstrap SHALL, when `firewall_tailscale_enabled` is true, accept
inbound SSH only on packets arriving on the Tailscale interface.

**Why:** for the service that matters most, this is what lets SSH need no
row in the public exposure register at all: on an enrolled host, SSH is
reachable only from inside the tailnet,
and an attacker on the public internet has no packet they can send that the
input chain will accept on the SSH port. What it leaves open to tailnet
peers is registered as `ALW-6`, because `INV-10` does not trust a peer for
being on the tailnet. Matching the *interface* rather
than a source address is what makes that true — a source address can be
forged, an interface a packet arrived on cannot. It is also why
`firewall_tailscale_ipv4`, which this role inherits, is read by no rule
here — see `design.md`'s `## Failure modes`. Against a host the `SSH` spec
has already bound to its tailnet addresses, this is the second of two
independent controls: `SSH-18` makes the daemon absent from public
addresses, `FW-10` makes the packets never arrive. Either alone would keep
a public client out, and `SSH-18`'s is the stronger of the two because an
absent service cannot be exposed by a filtering mistake; the point of
having both is that a mistake in one is not a mistake in the other. One
consequence of that pairing is that the break-glass path must undo both,
and it does — which is why this rule's *rendered text* is depended on
outside this spec, and cannot be reworded freely. See `design.md`'s
`## Interactions`.
**Verified:** `test_ssh_restricted_to_tailscale_when_enabled` and
`test_ssh_not_allowed_from_all_when_tailscale_enabled` render the template
with Tailscale enabled and assert the interface-qualified rule is present
and that no unqualified SSH accept line exists;
`test_property_19_nftables_ssh_access_control` asserts the
`iifname "{{ firewall_tailscale_interface }}"` form is in the template. No
test isolates this rule on a live host: the tailscale integration suite's
`test_ssh_closed_from_host` confirms SSH is unreachable from outside the
tailnet, but sshd's own binding is narrowed at the same time, and
`test_ssh_closed_without_firewall` deliberately removes the firewall to
prove the *other* control works alone. Nothing does the converse.

### FW-11 — Tailnet interface name configurable

THE Bootstrap SHALL match `FW-10`'s rule against the interface named by
`firewall_tailscale_interface`, which SHALL default to the `TS` role's
configured interface name.

**Why:** the rule narrows access to one interface, so naming the wrong one
is the same as having no SSH rule at all. Deriving the name from the same
variable the Tailscale role configures its client with is what stops the two
disagreeing — a deployment that renames the interface changes it in one
place. Nothing in this role checks that the interface exists; the name is
taken on trust, which is where the reliance on `INV-8` comes from.
**Verified:** `test_custom_tailscale_interface_name` renders with
`firewall_tailscale_interface` set to `ts0` and asserts the rule names it.
`test_property_19_nftables_ssh_access_control` asserts
`firewall_tailscale_interface:` appears in the defaults file; its check that
the default derives from the Tailscale role is written as
`"{{ tailscale_interface" in defaults_content or "tailscale_interface" in defaults_content`,
and the second alternative is satisfied by the variable's own name, so that
assertion cannot fail. See `design.md`'s `## Failure modes`.

### FW-12 — WireGuard port accepted when Tailscale is enabled

THE Bootstrap SHALL, when `firewall_tailscale_enabled` is true, accept
inbound UDP on the port named by `firewall_wireguard_port`, on every
interface, and SHALL NOT open that port when Tailscale is disabled.

**Why:** `FW-10` narrows SSH to a tunnel, and the tunnel has to be reachable
for that to be a route in rather than a lockout. Tailscale's WireGuard
traffic arrives from the internet on a public interface, so this rule cannot
be narrowed the way `FW-10` is. It is registered as `ALW-2`, and because
the rule names no interface it also matches the tailnet interface, which is
`ALW-8`. The exposure is small and the protocol is the reason: WireGuard is
designed not to answer a packet it cannot authenticate, so the port offers
nothing to a peer without a key. The second clause matters as much as the
first: a host with no tailnet has no reason to accept the traffic, and
opening it anyway would be exposure with no allowance to cover it.
**Verified:** `test_wireguard_allowed_when_tailscale_enabled`,
`test_wireguard_not_present_when_tailscale_disabled` and
`test_custom_wireguard_port` render both branches and assert the rule's
presence, absence and configured port.
`test_property_19_nftables_ssh_access_control` asserts the
`udp dport {{ firewall_wireguard_port }}` form is in the template. The
default value is not effectively checked anywhere: the property suite's
assertion is
`"firewall_wireguard_port: 41641" in defaults_content or ("firewall_wireguard_port:" in defaults_content)`,
whose second alternative any value satisfies, and the unit tests read 41641
from their own fixture rather than from the defaults file.

### FW-13 — SSH accepted on all interfaces when nothing narrower is configured

THE Bootstrap SHALL accept inbound SSH on every interface when
`firewall_tailscale_enabled` and `firewall_port_knocking_enabled` are both
false.

**Why:** the three SSH branches are mutually exclusive by construction, and
this is the last of them — the branch taken by a host with no tailnet and no
knock sequence, where the alternative to accepting SSH is a host nobody can
administer. It is exposure, registered as `ALW-4`. What keeps it
defensible is everything the `SSH` spec does to the connections this rule
admits: public keys only, no root, no passwords. The branch is written
explicitly rather than as the absence of a rule so that
its condition is visible and so that a fourth state — no SSH rule at all —
cannot arise from a flag combination nobody considered.
**Verified:** `test_ssh_allowed_from_all_when_tailscale_disabled` renders
with both flags false and asserts the unqualified accept is present and the
interface-qualified one is not.
`test_property_19_nftables_ssh_access_control` extracts the template's
`{% else %}` branch and asserts it contains no `iifname`. No test in the
default suite renders the middle branch alongside this one to confirm the
three are mutually exclusive, and the integration suite bootstraps with port
knocking enabled, so this branch is never exercised on a live host.

### FW-14 — SSH port taken from the SSH spec's port

THE Bootstrap SHALL name the port from `firewall_ssh_port` in every SSH
rule, and `firewall_ssh_port` SHALL default to `ssh_port`.

**Why:** the firewall rule and sshd's own `Port` directive are two
statements about the same number, and a host where they disagree is a host
that is either unreachable or listening on a port the firewall does not
admit. Deriving one from the other makes them agree by construction rather
than by review: `SSH-13` is the single source, and an inventory that
overrides `ssh_port` moves both. The `| default(22)` fallback exists only
for a play that consumes this role without the `ssh_hardening` role, which
`site.yml` never does.
**Verified:** `test_custom_ssh_port_in_rules` and
`test_custom_ssh_port_with_tailscale` render with port 2222 on the open and
tailnet branches and assert the rendered rule names it and that port 22 is
gone. `verify_bootstrap.yml`'s `Verify FW-14: SSH port is accessible through
firewall` searches a live ruleset for `tcp dport <ssh_port>`. The derivation itself is not effectively tested: the
property suite's assertion is
`"{{ ssh_port" in defaults_content or "ssh_port" in defaults_content`, whose
second alternative is satisfied by the string `firewall_ssh_port:` itself.

### FW-15 — The deployed ruleset replaces what is loaded

THE Bootstrap SHALL flush the loaded ruleset as part of applying the
deployed one.

**Why:** without this, every load would add to what the kernel already
holds, so a re-run would accumulate duplicate rules and — worse — a rule an
earlier revision of the template created would survive its own deletion
forever. `INV-9` asks that a re-run never weaken what an earlier run
established; a flush makes the deployed file the complete statement of the
host's firewall, so that what a reviewer reads is what the kernel enforces.
The flush is part of the same transaction as the rest of the file, which is
what makes it safe: a ruleset that fails to parse applies nothing and leaves
the running rules untouched. It also removes tables this file does not
define, which is how a reload discards another tool's rules — see
`design.md`'s `## Failure modes`.
**Verified:** `test_flush_ruleset_present` asserts `flush ruleset` is in the
rendered output. The transaction behaviour was measured rather than
asserted: loading a ruleset whose drop-in directory contained a syntax error
left the previously loaded rules in place unchanged, and reloading the file
after another tool had created a second table removed that table. Nothing in
the test suite covers either.

### FW-16 — Ruleset deployed to the path the service reads

THE Bootstrap SHALL deploy the rendered ruleset to `/etc/nftables.conf`,
owned by root, group root, mode `0644`.

**Why:** `/etc/nftables.conf` is the file the packaged nftables service
loads, so the path is not a convention but the whole mechanism by which a
rendered template becomes rules the kernel holds — including after a reboot,
which is the only way the ruleset survives one. Nothing saves the running
configuration; it is re-read from this file every time. Root ownership is
what makes the firewall's behaviour a root-only decision: the file is
world-readable, which reveals the posture to any local account, and
world-writable would let any of them rewrite it before the next load.
**Verified:** `test_property_17_nftables_dual_stack_configuration` and
`test_property_21_nftables_service_persistence` assert
`dest: /etc/nftables.conf`, `mode: "0644"`, `owner: root`, `group: root`
and `src: nftables.conf.j2` all appear in the tasks file. The assertions are
file-wide rather than task-scoped, so they establish the strings are present
somewhere in the role's tasks, not that they sit on the deployment task.

### FW-17 — nftables service enabled at boot

THE Bootstrap SHALL enable the nftables service, so the deployed ruleset is
loaded on every boot.

**Why:** this and `FW-16` together are the whole of the persistence
guarantee. A ruleset loaded by hand lives in kernel memory and is gone at
the next reboot, so a host whose service is not enabled would come up
unfiltered — and unfiltered is not "as before", it is wide open, because a
host with no base chains filters nothing at all. The window is also the
worst possible one: a reboot is exactly when an operator is not watching.
**Verified:** `test_property_18_nftables_stateful_firewall_rules` and
`test_property_21_nftables_service_persistence` assert `enabled: true`
appears in the tasks file, the latter also walking the task list to confirm
a systemd task that names `nftables` carries it — a walk whose idea of where
one task ends is a fixed line offset, and which currently separates this
task from `FW-18`'s by a single line; see `design.md`'s `## Failure modes`.
`verify_bootstrap.yml`'s `Verify FW-17: NFTables service is enabled`
asserts the unit's `UnitFileState` is `enabled` on a live host.

### FW-18 — nftables service started

THE Bootstrap SHALL start the nftables service.

**Why:** a first run must end with the rules in force, not with a correct
file waiting for a reboot. On a host where the service was not previously
running, this task is what first loads the ruleset: `FW-19`'s handler does
not fire until the next handler flush after this role, which the logging
role forces as its last task, so without this the host would spend the
emergency-access, fail2ban and logging roles unfiltered. That is a shorter
span than "the rest of the play" — `swap` runs after the flush — and it is
still every role that opens or reacts to network exposure.
**Verified:** `test_property_18_nftables_stateful_firewall_rules` and
`test_property_21_nftables_service_persistence` assert `state: started`
appears in the tasks file, the latter confirming it sits on a systemd task
naming `nftables` — subject to the same one-line task-boundary margin noted
under `FW-17`. `verify_bootstrap.yml`'s `Verify FW-18: NFTables service is active` asserts
the unit's `ActiveState` is `active`, and the integration suite's
`test_bootstrap_configures_firewall` asserts `systemctl is-active nftables`
succeeds after a real run. Both say less than they appear to: the unit is
`Type=oneshot` with `RemainAfterExit=yes`, so `active` records that the last
load exited zero, not that the rules are still loaded.

### FW-19 — nftables reloaded when the ruleset changes

THE Bootstrap SHALL reload nftables when, and only when, the deployed
ruleset changes.

**Why:** a deployed file the kernel has not been given is a run that reports
success while the host still enforces the previous rules — the most
misleading outcome available, because every file-reading check would pass.
Using a handler rather than an unconditional restart is what keeps a re-run
that changes nothing from disturbing a working firewall. The reload
re-executes the whole file, `FW-15`'s flush and `FW-21`'s include alike, as
one transaction, so a drop-in that has since become invalid fails the reload
and leaves the loaded rules exactly as they were.
**Verified:** `test_property_18_nftables_stateful_firewall_rules`,
`test_property_21_nftables_service_persistence` and
`test_property_9_service_restart_on_configuration_change` assert that the
deployment task notifies, that the handler exists, that it uses a service
module, that it uses `state: reloaded` or `state: restarted`, and that every
notified handler name is defined. Nothing asserts the handler is *not*
notified by a run that changed nothing, and nothing exercises a reload on a
live host.

### FW-20 — Drop-in directory created

THE Bootstrap SHALL create `/etc/nftables.d`, owned by root, group root,
mode `0755`, before deploying the ruleset that includes it.

**Why:** this is the half of the extension contract that belongs to the
bootstrap: a purpose repository drops a rule file in and does not edit any
bootstrap-owned file, so the two repositories never contend for
`/etc/nftables.conf` and a bootstrap re-run cannot delete a purpose repo's
rules. Root ownership matters more here than for most directories — a file
placed in it is loaded into the firewall with no review, so write access to
this directory is write access to the host's inbound policy.
**Verified:** nothing. No unit test, property test, verification play or
integration test references `/etc/nftables.d` in any form. The directory's
creation, its ownership and its mode are asserted nowhere, and deleting the
task would leave every test in the project green.

### FW-21 — Drop-in files included at the end of the ruleset

THE Bootstrap SHALL include `/etc/nftables.d/*.nft` at the end of the
deployed ruleset.

**Why:** the include is what makes `FW-20`'s directory an extension point
rather than a folder. Placing it last means a purpose repo's `add rule`
appends after everything this spec defines, and no rule *this* spec renders
is terminal, so an appended accept is reached — only the `FW-3` policy comes
after it. The one exception is not this spec's: on a knock-gated host
`KNOCK-8` renders a terminal `drop` of the three knock ports, so an appended
rule accepting one of those ports is never reached. The glob is deliberate: an `include` of a named file that does not
exist is a parse error that would fail the whole ruleset, whereas a wildcard
matching nothing is not, so a host with an empty or absent drop-in directory
loads exactly the ruleset written here. A hole a drop-in opens has no row
in this project's exposure registers: the purpose repository that opens it
documents it in registers of its own (`PRJ-28`).
**Verified:** nothing in the test suite. The behaviour was measured instead:
the rendered ruleset loads unchanged with the drop-in directory absent and
with it present but empty; a drop-in containing
`add rule inet filter input tcp dport { 80, 443 } accept` appears as the
last rule of the input chain, after the SSH rule and before the policy; and
replacing the glob with a named file that does not exist fails the load.
