# Port knocking — Requirements

**Prefix:** `KNOCK`

## Purpose

This spec is the middle of the firewall's three SSH branches: the one a host
takes when it has no tailnet but should not simply publish its SSH port.
The port stays closed to every source until that source has sent packets to
three other ports in order; only then, and only for half a minute, does the
input chain accept SSH from it.

What that buys is narrow and worth stating plainly: it removes the host from
untargeted scanning. A scanner that sweeps the internet for open SSH ports
finds nothing here, so the host never enters the lists that feed
credential-stuffing and CVE-chasing traffic, and the sshd log stops filling
with attempts that were never going to succeed. What it does not buy is
authentication. The sequence is a fixed, unauthenticated triple of port
numbers carried in cleartext TCP headers; anyone who can watch the path can
replay it, anyone who can guess it can use it, and nothing about completing
it says who the source is. The controls that decide whether a connection
gets a shell are `SSH`'s — public keys only, no root, no passwords — and
`F2B`'s bans on the attempts that get through. This spec makes those
controls see less traffic. It does not replace any of them.

Without this spec a host with no tailnet would take `FW-13`'s branch and
publish SSH to the internet, which is a supported configuration and the one
an operator gets by setting `port_knocking_enabled: false`. The difference
this spec makes is that the default is not that.

## Scope

### In scope

- The condition under which knocking is active at all, and the guarantee
  that nothing of it is rendered otherwise.
- The assertion that the sequence is exactly three ports, and that it runs
  before the ruleset is rendered.
- The six named sets that hold knock progress — three stages for each
  address family — their element types and their timeouts.
- The three staged rules per address family that move a source from nothing
  to stage 1 to stage 2 to passed.
- The explicit drop of the knock ports, and its position relative to
  everything that could otherwise act on those packets.
- The SSH accept rules that require membership in the passed set of the
  packet's own address family.
- The four `firewall_port_knocking_*` variables, their defaults, and the
  top-level inventory variables they derive from.
- The controller-side knock that lets the playbook reach a host it has
  already put behind a knock sequence.

### Out of scope

- The input chain these rules are inserted into, its `drop` policy, and the
  two unconditional accepts that precede everything this spec renders —
  `FW-3`, `FW-6` and `FW-7`. This spec relies on all three rather than
  restating them, and `FW-7` in particular limits what `KNOCK-8` can claim:
  loopback traffic is accepted before the knock rules are reached at all.
- Choosing the SSH port. `SSH-13` owns it and `FW-14` carries it into every
  SSH rule, this spec's set-membership rules included.
- The open branch `FW-13` renders and the tailnet branch `FW-10` renders.
  This spec owns only the third branch and the flag that selects it; that
  the three are mutually exclusive is a property of the template `FW`
  builds.
- Deploying the file, loading it, reloading it when it changes and flushing
  what was loaded before — `FW-15` through `FW-19`. This spec's rules reach
  the kernel by that machinery and add none of their own.
- What happens to an SSH connection once it has been accepted. Whether it
  can authenticate is `SSH`'s, whether it is banned after failing to is
  `F2B`'s.
- Whether a host has a tailnet at all, which is `TS`'s, and which this spec
  only reads as a flag.
- Teaching an operator how to knock. `docs/port-knocking.md` is user-facing
  how-to material, which `specs/README.md` places outside this tree
  deliberately.

## Security invariants

**Upholds:** INV-1, INV-10
**Relies on:** INV-2, INV-3, INV-4, INV-6
**Allowances claimed:** ALW-3

This branch keeps less off the public internet than the tailnet branch
does, and the difference should be understood rather than glossed. `FW-10` makes SSH
unreachable from the public internet outright: a packet that did not arrive
on the tailnet interface cannot be made to match. This spec makes SSH
unreachable from a source that has not sent three packets first — which any
source can do, if it knows or learns which three. So what is kept off the
public internet is the *port*, not the *service*. `INV-1` is satisfied
because that exposure is registered: `KNOCK-9` opens the SSH port to a
passed source and claims `ALW-3` for it, whose compensating controls are
the knock sequence itself and, behind it, `INV-2` and `INV-3`. The knock
ports need no row of their own: a packet a remote source sends to one of
them is recorded by the progress rules and then dropped by `KNOCK-8`, not
accepted.

`INV-10` is upheld because nothing of this spec reaches a tailnet peer:
`KNOCK-1` renders the branch only where `firewall_tailscale_enabled` is
false, which is a host with no tailnet as long as that flag tracks
enrollment, as the tailnet exposure register's preamble assumes.

**Why this is worth doing anyway, and what it is not.** The realistic threat
against a fresh VPS is not a targeted attacker; it is the continuous
background sweep that finds every open port on every routable address within
hours. Against that, a closed port is the whole defence: the host is never
catalogued, never queued for a credential list, never retried. Against an
attacker who has already chosen this host, the sequence is three integers in
plaintext TCP headers — observable by anyone on the path, replayable
forever, and carrying no identity of any kind. With the default sequence it
is weaker still: the three ports are in ascending order, so a scanner
sweeping ports upward completes the knock as a side effect of sweeping, as
`design.md` records having measured. It is obscurity, and obscurity that
sits *in front of* the real controls rather than in place of them, so a
weakness in it costs a layer and not the host: `INV-2` and `INV-3` are
still what stop a source that completed the sequence, and `F2B` is still
what stops it from trying repeatedly. Those two invariants are listed as
reliances for exactly that reason — if either were weakened, this spec would
be the only thing between the internet and a password prompt, and it is not
strong enough to be that.

`INV-4` is the reliance that makes knocking work at all. The SSH port is
silent rather than refused because `FW-3`'s policy drops what no rule
accepted, and the knock ports because `KNOCK-8` drops them explicitly with
that policy behind it; and the whole scheme applies to IPv6 exactly as it
does to IPv4 because `FW-2`'s single `inet` table leaves no second place for
one family to behave differently. This spec renders a pair of nearly
everything for that reason: six sets rather than three, two staged rule
groups rather than one, two SSH accepts rather than one. `KNOCK-8`'s drop is
the one rule not doubled, because it matches on destination port alone and
so covers both families at once.

**`INV-8` is not upheld on this branch, and this spec does not claim it is.**
The invariant reads "SHALL NOT narrow access before verifying the
replacement path works". On a knock-gated host the narrowing is `KNOCK-9`
and the replacement path is the knock itself, and nothing verifies that path
before it becomes the only one. The three candidate verifications all fail
to be one:

- `KNOCK-11`'s controller-side knock **checks nothing**. It sends three TCP
  connection attempts, suppresses every `OSError` they can raise, inspects
  no result, and is marked `changed_when: false`, so it reports success
  whether the packets reached anything or not — a knock draws no reply, so
  there is nothing it could check. On a first run it also executes *before*
  the ruleset exists, against a host whose knock ports are simply closed.
- **The narrowing run cannot notice its own mistake.** The connection
  Ansible is using was established before the firewall reload and is kept
  alive afterwards by `FW-6`, so a ruleset that would refuse every future
  connection does not disturb the run that deployed it. That continuity is
  what makes the branch usable at all; it is also what removes the one
  signal a run could have given.
- **A later run only looks like proof.** A second run does knock and then
  connect, so a run that succeeds normally did complete a knock — but that
  is after the narrowing, not before it, and `ansible.cfg` weakens even
  that: `ControlPersist=60s` over a control path that is stable across runs
  (`/tmp/ansible-ssh-%h-%p-%r`) means a re-run started inside a minute
  reuses the existing multiplexed connection, so it can succeed on a host
  whose knock path is broken.

`VRFY` cannot close the gap either: its playbook has no knock play of its
own, so it cannot reach a knock-gated host unaided at all — see
`design.md`'s `## Failure modes`.

What `KNOCK-2` does is narrower than the invariant and should not be mistaken
for it: it catches a sequence of the wrong *length* before the template
renders. A sequence of three ports the operator cannot reproduce, or that an
intermediate network drops, renders and loads cleanly.

This spec therefore records an unresolved gap rather than papering over it.
Two resolutions exist and both are decisions above this spec: add a
verification that actually exercises the knock path after the ruleset is
loaded and fails the run if it cannot connect, which would make `INV-8`
upheld in the same shape `TS-15`, `TS-16`, `TS-21` and `TS-22` uphold it for
the tailnet branch; or claim a numbered allowance against `INV-8` with
`INV-6`'s console recovery named as the compensating control. **No allowance
is claimed here**, because claiming one is a change to the allowance
registers in `specs/project/security-invariants.md` and not this spec's to
make unilaterally. Until it is resolved, the
honest statement is the one in this paragraph: the knock branch narrows
access without verifying the replacement path.

`INV-6` is the last resort behind that gap, and this spec earns it the same
way `FW` does: the knock rules live in `/etc/nftables.conf`, a plain
root-owned file, so an operator at a provider console can delete the branch
or read the sequence back out of it without a network. It is worth being
explicit that the break-glass *script* does not help here — it is deployed
only on Tailscale-enabled hosts, which are exactly the hosts where this spec
is inactive, and it edits `FW-10`'s rule, which a knock-gated host does not
have. Console recovery from a knock lockout is manual editing, not a tool.

## Requirements

### KNOCK-1 — Port knocking is active only when Tailscale is disabled and knocking is enabled

THE Bootstrap SHALL render the knock sets and rules when, and only when,
`firewall_tailscale_enabled` is false and `firewall_port_knocking_enabled`
is true, and SHALL render none of them otherwise.

**Why:** knocking and the tailnet solve the same problem, so a host that has
one does not need the other and should not carry both. On a tailnet-enrolled
host SSH is already unreachable from the public internet by `FW-10`, and
adding knock rules there would open three ports on every interface to buy
nothing — worse, it would suggest a second route in that does not exist,
since `FW-10` narrows by interface and a knock cannot widen it. Making the
condition exclusive rather than additive also keeps the template's three SSH
branches genuinely three: exactly one of `FW-10`, this spec's rules, and
`FW-13` is rendered for any pair of flag values, so no combination of flags
produces two SSH branches, and none produces a host with no SSH rule at all.
**Verified:** `test_knock_rules_conditional_on_tailscale_and_knocking`
generates both flags and branches on them, but every assertion in all three
branches is a substring check against the raw template text, so it confirms
the conditional's *spelling* — that the Tailscale test comes first and the
knock test is an `elif` — rather than what any flag combination renders. The
four combinations were rendered and inspected directly instead: with
Tailscale enabled the output contains no set, no staged rule and no
`@knock`-qualified accept whether knocking is on or off; with Tailscale
disabled and knocking on it contains six sets, six staged rules and two
set-membership accepts; with both off it contains `FW-13`'s unqualified
accept and nothing of this spec.

### KNOCK-2 — The knock sequence is exactly three ports

THE Bootstrap SHALL fail the run, before the ruleset is rendered, if
`firewall_port_knocking_sequence` does not contain exactly three ports,
and SHALL make that check only when `KNOCK-1`'s condition holds.

**Why:** the rules are written out one stage at a time and index the
sequence by position, so a shorter list fails the template task with
Ansible's message for an out-of-range index — measured:
`object of type 'list' has no attribute 2` — and a longer one is a sequence
whose extra ports are silently ignored, so an operator who configured five
ports and knocks all five would find the host admitting them after three,
with no indication that two of their ports mean nothing. Failing the run
before the ruleset is rendered turns both into one legible message before
the firewall writes anything. The gating matters as much as the check: a
host that has Tailscale, or has turned knocking off, never renders these
rules, and failing its run over the shape of a list nothing reads would be a
check with no subject.
**Verified:** nothing. No unit test, property test, verification play or
integration test exercises this assertion, references its task, or renders
the template with a sequence of any other length. Deleting the task would
leave every test in the project green — the short-sequence behaviour quoted
above was measured against Ansible's templating directly, not against this
role.

### KNOCK-3 — Six named sets hold knock progress, three per address family

THE Bootstrap SHALL define, at table level, a stage-1, a stage-2 and a
passed set for IPv4 and the same three for IPv6, each holding addresses of
its own family.

**Why:** the whole mechanism is "remember which sources have got how far",
and a timeout-flagged set is the only place in nftables where a rule can
record that from the packet path. They are at table level because the syntax
requires it — a set declared inside a chain is a parse error, and a parse
error in this file means `FW-15`'s transaction applies nothing, which on a
first boot is a host with no firewall at all. Three sets per family rather
than one set with a stage counter is the shape nftables makes cheap: set
membership is a match, so each stage's rule is one line with one lookup,
and a source's progress is readable with `nft list set`. The families are
separate because the element type is: an `ipv4_addr` set cannot hold an
IPv6 address, so parity across families here means duplication, which is
the cost `FW-2`'s single table accepts in exchange for one policy governing
both.
**Verified:** `test_dual_stack_knock_sets` samples `ipv4_addr` and
`ipv6_addr` and asserts each appears somewhere in the template;
`test_sets_at_table_level` finds the line declaring `knock4_stage1` or
`knock6_stage1` and asserts it precedes `chain input`, though the assertion
sits inside an `if both line numbers were found` guard and would be skipped
rather than fail if the set were renamed. Both read the raw template.
`verify_bootstrap.yml` asserts that a live `nft list ruleset` contains
`knock4_stage1`, `knock6_stage1`, `knock4_passed` and `knock6_passed` — the
stage-2 sets are not among them — and the integration suite's
`test_port_knocking_rules_in_nftables` asserts `knock4_stage1` and
`knock4_passed` appear in a real bootstrapped VM's ruleset. The rendered
knock branch was also loaded into a live kernel in a network namespace,
where the six sets appeared as declared; `nft` supplies `flags dynamic` and
`size 65535` itself, so each set is capped at 65535 elements by a default
this file does not state.

### KNOCK-4 — The first sequence port admits any source to stage 1

THE Bootstrap SHALL add the source address of any TCP packet sent to the
first port of the sequence to that family's stage-1 set.

**Why:** the sequence has to start somewhere, and the first knock is the one
step that cannot require prior progress. The consequence is that this rule
matches every source that sends one packet to one port, including a scanner
that touches it by accident, so the stage-1 set is the one an adversary can
fill at will — bounded only by `nft`'s default set size and by `KNOCK-7`'s
five-second expiry, since nothing here rate-limits and nothing distinguishes
a deliberate knock from a stray SYN. That is tolerable precisely because
stage-1 membership grants nothing: it is a precondition for `KNOCK-5`, not
an accept.
**Verified:** `test_knock_sequence_ports_in_template` asserts the template
references `firewall_port_knocking_sequence[0]`; it also generates a
three-port sequence it never reads, so the same fixed assertion runs 100
times. The behaviour was measured instead: with the rendered branch loaded
in a network namespace, a single TCP connection attempt to the first port
put the source into `knock4_stage1` with a five-second expiry, from a source
that was in no set beforehand.

### KNOCK-5 — The second sequence port advances a stage-1 source to stage 2

THE Bootstrap SHALL add the source address of a TCP packet sent to the
second port of the sequence to that family's stage-2 set, and SHALL do so
only if that source is already in the stage-1 set.

**Why:** this is where the sequence becomes a sequence. The membership test
is the entire mechanism — without it the three rules would be three
independent ports any one of which admitted progress, and order would not
matter. Because the rule only ever adds, a source that reaches stage 2
remains in stage 1 until its own timer runs out; that was measured, and it
means "stage 2" is a source's furthest progress rather than its current
position. Nothing depends on the earlier entry being gone, and removing it
would cost a second set operation per packet to buy nothing.
**Verified:** `test_knock_sequence_ports_in_template` asserts the template
references `firewall_port_knocking_sequence[1]`. Nothing asserts the
membership qualifier is present, in the template or anywhere else. Measured
in a network namespace: a source in stage 1 that hit the second port
appeared in stage 2 and remained in stage 1; a source that hit the second
port with no stage-1 entry — including a source whose stage-1 entry had
expired — did not appear in stage 2 at all. Knocking the three ports in
reverse order left the source in the stage-1 set **only**, with stage 2 and
the passed set empty, and that stage-1 entry is `KNOCK-4` doing its
unconditional job on the final packet: 9100 and 8500 find no membership to
build on, and 7000 arrives last and starts a sequence rather than finishing
one. The entry expired on its own five seconds later, leaving all three sets
empty.

### KNOCK-6 — The third sequence port admits a stage-2 source to the passed set

THE Bootstrap SHALL add the source address of a TCP packet sent to the third
port of the sequence to that family's passed set, and SHALL do so only if
that source is already in the stage-2 set.

**Why:** the passed set is the one that means something — `KNOCK-9` reads it
and nothing else does — so this is the rule that decides who gets to reach
sshd. It is the same construction as `KNOCK-5` for the same reason, and the
only difference is the timeout the entry gets, which is the pass window
rather than a stage window.
**Verified:** `test_knock_sequence_ports_in_template` asserts the template
references `firewall_port_knocking_sequence[2]`. The end-to-end behaviour is
the best-covered part of this spec: the integration suite's
`test_ssh_blocked_without_knock` requires the SSH port to be unreachable on
a bootstrapped VM, `test_ssh_accessible_after_knock` requires it to be
reachable after a knock, and the rest of that suite knocks before using SSH
at all rather than testing the knock itself. Measured directly as well: in a
network namespace a connection to the SSH port failed before the knock and
succeeded after it, and the source appeared in `knock4_passed` with a
thirty-second expiry.

### KNOCK-7 — Progress is held only by set timeouts, and expiry is the only reset

THE Bootstrap SHALL bound stage-1 and stage-2 entries by
`firewall_port_knocking_stage_timeout` and passed entries by
`firewall_port_knocking_timeout`, and SHALL provide, among the rules it
renders, no other means of removing an entry, the destruction of the sets
themselves by `FW-15`'s flush excepted.

**Why:** something has to forget, or the first knock anyone ever sent would
stand forever and the sequence would degrade into "these three ports have
been touched at some point". A timeout does that without a rule, without
state to clean up and without a packet having to arrive to trigger it. Two
different windows because the two jobs differ: five seconds is a bound on
how long a *partial* sequence stays interesting, which should be about as
long as it takes to send three packets and no longer, and thirty seconds is
a bound on how long a completed knock stays useful, which has to be long
enough to start an SSH connection on a slow link.

Three consequences of "only expiry" are worth stating, because they are what
a reader would otherwise assume backwards. **An out-of-sequence or unrelated
packet does not reset anything** — there is no rule that deletes, so a
source that knocks the first port, then touches an unrelated port, then
knocks the second and third, still passes. What a wrong port costs is time,
not progress. **Re-knocking does not extend a window**: `add` on an element
that is already present leaves its original expiry in place, so a source
cannot hold itself in stage 1 by knocking the first port repeatedly, and the
five seconds run from the packet that created the entry. **An SSH connection
that is already established outlives its passed entry**, because `FW-6`
accepts it on connection state and never consults these sets again — which
is why a knock-gated host can be administered at all, and why a long Ansible
run does not have to re-knock partway through.

The exception the SHALL names is worth spelling out, because it is the one
way a knock disappears that no timer explains. `FW-15`'s flush destroys the
sets and the file recreates them empty, so `FW-19`'s handler, a manual reload
and a reboot each discard every partial and completed knock on the host. That
was measured. It is excepted rather than forbidden because it is not a
removal mechanism this spec provides — it is this spec's state not surviving
an event that belongs to `FW` — and what it costs an operator is recorded as
a failure mode in `design.md`.
**Verified:** `test_timeout_variables_used` asserts that the strings
`firewall_port_knocking_stage_timeout` and `firewall_port_knocking_timeout`
appear in the template; it does not check which set carries which, and it
generates an address family it never reads. No test anywhere waits for an
expiry. All three consequences were measured in a network namespace against
the rendered branch: a source that knocked the first port, then a port
outside the sequence, then the second and third, reached the passed set; a
source that re-knocked the first port after three seconds kept its original
expiry and was gone at six, after which the second port did nothing; and
with the pass window shortened to two seconds, an established connection
still carried traffic four seconds later while a new connection from the
same source was refused.

### KNOCK-8 — The knock ports are dropped after the progress rules

THE Bootstrap SHALL drop TCP packets addressed to any port of the sequence,
after the rules that record progress and before every rule that follows
them in the input chain, the drop-in rules `FW-21` appends included.

**Why:** this rule is not redundant with `FW-3`'s policy, which would also
drop these packets, and the difference is `FW-21`. The drop-in include
appends a purpose repository's rules to the end of the input chain, and a
purpose repo that opened one of the knock ports for its own service would
otherwise turn that port into a working service *and* a knock — answering
the SYN, which is exactly the signal the scheme exists to withhold. An
explicit drop at this position makes the knock ports silent no matter what
is appended later, and does the same for any future logging rule that would
otherwise record every knock. Placing it after the progress rules rather
than before is what lets the same packet do both jobs: nftables evaluates
rules in order, so the `add` has already happened by the time the drop is
reached.

The requirement is deliberately "every rule that *follows* them" and not
"every rule that could accept them", because two unconditional accepts sit
above everything this spec renders and this drop does not govern them.
`FW-6` accepts a packet belonging to an established or related connection,
and `FW-7` accepts anything arriving on the loopback interface — so a
process on the host connecting to a knock port over `127.0.0.1` is accepted
by `FW-7`, and records no knock progress at all, because it never reaches
these rules. That is the right outcome and not a gap: a local process does
not need a knock and cannot be a remote scanner. It is stated here so that
"unconditionally silent" is not read as a claim about the loopback path.
**Verified:** `test_explicit_drop_for_knock_ports` asserts the template
contains a rule referencing `firewall_port_knocking_sequence | join`, and
that the line number of the drop is less than the line number of the
`@knock…_passed accept` rule, with the comparison guarded by an `if both
were found` check; it generates an address family it never reads. Nothing
tests the interaction with a drop-in. That was measured: with the rendered
branch loaded in a network namespace and a listener bound to the first knock
port, `add rule inet filter input tcp dport 7000 accept` — the exact form
`FW-21`'s contract requires of a drop-in — left connections to that port
still dropped. The loopback precedence was measured too, on the *full*
rendered ruleset with `FW-7`'s rule in place: a loopback connection to the
first knock port succeeded and left every knock set empty, while the same
connection against a copy of the ruleset with `FW-7`'s rule removed was
dropped and populated the stage-1 set.

### KNOCK-9 — SSH is accepted only for a source in its own family's passed set

THE Bootstrap SHALL accept inbound SSH only from a source address present in
the passed set of that packet's address family, and SHALL add no other SSH
accept while `KNOCK-1`'s condition holds.

**Why:** this is the requirement the other eight exist to make possible, and
the one that makes `INV-1` true for a knock-gated host: with `FW-3`'s policy
below it and no unqualified accept beside it, there is no packet a *remote*
source that has not completed the sequence can send to the SSH port that
this chain will accept. The qualifier is load-bearing — `FW-7` accepts
loopback traffic above this rule, so a process on the host reaches sshd over
`127.0.0.1` without knocking, and `FW-6` keeps an already-established
session going; `INV-1` is about reachability from a publicly routable
address, which is closed to a source that has not completed the sequence.
What stays open to a source that has completed it is registered as
`ALW-3`. The rule is written once per
family rather than once, because
the passed sets are per family and a set lookup cannot span both; the
practical consequence for an operator is that a knock sent over IPv4 opens
SSH over IPv4 only, which is a real source of confusion on dual-stack hosts
and is why `docs/port-knocking.md` says so.
**Verified:** `test_ssh_accept_references_knock_passed` samples the address
family and asserts `@knock4_passed accept` or `@knock6_passed accept`
appears in the template;
`test_no_unconditional_ssh_accept_with_knocking` extracts the knock branch
between `elif firewall_port_knocking_enabled` and the next `{% else %}` and
requires every line in it carrying `tcp dport`, `firewall_ssh_port` and
`accept` to also carry `@knock`. That extraction is correctly scoped — the
branch's `{% for %}` and `{% endfor %}` lines contain neither `{% else %}`
nor `{% endif %}`, so the scan stops at the branch's own `{% else %}` —
unlike the Tailscale-branch extraction in the same file that
`specs/firewall/design.md` records as over-wide. Live evidence is the
integration suite's `test_ssh_blocked_without_knock` and
`test_ssh_accessible_after_knock` on a real bootstrapped VM, and
`test_only_ssh_reachable_after_knock`, which requires ten other common ports
to stay unreachable after a knock. `test_port_knocking_does_not_bypass_tailscale`
covers the other side of `KNOCK-1`: a completed knock against a
Tailscale-enabled host does not open SSH, because no rule here was rendered.

### KNOCK-10 — Knock behaviour is configured from inventory

THE Bootstrap SHALL take the enable flag, the sequence and the two timeouts
from `firewall_port_knocking_enabled`, `firewall_port_knocking_sequence`,
`firewall_port_knocking_timeout` and `firewall_port_knocking_stage_timeout`,
each defaulting to the identically named variable without the `firewall_`
prefix, and those in turn defaulting to true, `[7000, 8500, 9100]`, 30 and 5.

**Why:** a sequence that is the same on every host running this bootstrap is
a sequence an attacker reads once out of a public repository, so the value
has to be an inventory decision, and the role-level indirection is what lets
an operator express it as one top-level `port_knocking_sequence` rather than
a role-prefixed variable per consumer. The defaults are chosen to make the
unconfigured case work rather than to be secret: three high ports unlikely
to be in use on a freshly provisioned host, and two timeouts a human with a
shell script can meet. "Unlikely" is not "unassigned" — 9100 is Prometheus
node_exporter's default listening port, and `KNOCK-8` drops it, so a purpose
repository that deploys node_exporter on a knock-gated host must move one of
the two. An operator who leaves the sequence alone gets obscurity against
untargeted scanning and nothing against anyone who has read this file, which
is the honest position for a default.
**Verified:** `test_defaults_define_knock_variables` asserts the four keys
appear in the defaults file; it checks no value, and generates an address
family it never reads. No test asserts the default sequence, either timeout
default, or that any of the four derives from the unprefixed variable — so
the defaults could be changed to unrelated literals, or the derivation
removed, with every test still green. This is the same inert-verification
pattern `specs/firewall/design.md` records against its own defaults
assertions.

### KNOCK-11 — The controller knocks before the playbook connects

THE Bootstrap SHALL send the knock sequence from the Ansible controller to
each host, over a local connection that needs no SSH, before the play that
connects over SSH, under the same condition that governs `KNOCK-1`.

**Why:** the first run of the playbook is against an unbootstrapped host
with SSH open, so it needs no knock; every run after it is against a host
this spec has closed, and without this play Ansible's own connection would
be the first thing the new rules refuse. The result would be a bootstrap
that works once and then locks out the tool that produced it. Running it as
a separate play with `connection: local` is what makes it possible at all —
a task inside the bootstrap play would need the SSH connection it exists to
enable. Reporting no change keeps a knock, which alters nothing on the host,
out of the run's changed count.

The requirement is about the bootstrap playbook and nothing else. The
verification playbook is a separate file with no knock play of its own, so
it cannot reach a knock-gated host unaided — that is a gap, it belongs to
`VRFY`, and it is recorded in `design.md`'s `## Failure modes` rather than
fixed by widening this requirement to cover a playbook this spec does not
own.
**Verified:** `test_knock_play_exists_before_bootstrap_play` parses
`site.yml` and asserts the first play is named "Port knock for SSH access",
gathers no facts and uses the local connection;
`test_knock_play_is_conditional` asserts its task's `when` mentions both
`tailscale_enabled` and `port_knocking_enabled`, without checking their
sense; and `test_knock_play_never_reports_changed` asserts `changed_when` is
false. All three read the playbook rather than run it. The play's real
evidence is the integration suite, where every run of the bootstrap
playbook against an already-bootstrapped VM goes through it.
