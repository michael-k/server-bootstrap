# Port knocking — Design

## Approach

This spec adds no role, no service, no daemon and no file of its own. It is
two conditional blocks inside the firewall's template — the sets at table
level and the rules inside the input chain — one assertion task in front of
them, four variables, and one play at the top of the playbook. Every
line it contributes reaches the kernel through `FW`'s machinery — rendered
into `/etc/nftables.conf` by `FW-16`, loaded whole by `FW-15`'s transaction,
reloaded by `FW-19` when it changes — and this spec adds nothing to that
path.

That was the first decision and it shaped the rest: port knocking is a
firewall concern, not a subsystem. The conventional alternative is `knockd`,
a userspace daemon that watches for a sequence and runs a firewall command
when it recognises one. It was not chosen. A daemon is a second thing that
can be stopped, crash or fail to start at boot, and the rules it adds are
kernel state written imperatively — so the host's actual posture could not
be read off `/etc/nftables.conf` any more, and the rules would be exposed to
`FW-15`'s flush, which `specs/firewall/design.md` records as measured to
remove every table in the kernel and not merely the one it defines. Doing
the same work with nftables sets keeps the whole mechanism inside the one
file `FW` already treats as the complete statement of the host's firewall,
with the same atomic-load and converge-on-every-run properties that file
has.

The mechanism itself is a state machine held in timeout-flagged sets.
Nothing tracks connections, and nothing correlates packets; there are only
sets of source addresses and rules that add to one set on the condition of
membership in another. A source with no entries can only match the first
rule. A source in stage 1 can match the second. A source in stage 2 can
match the third, which puts it in the passed set, which is the only set
`KNOCK-9` reads. Progress is never deleted — only expired — so the machine
is monotone within a window and empty outside one, which is the whole of its
complexity.

Everything is written twice, once per address family, because a set holds
one address type and a set lookup cannot span both. `FW-2`'s single `inet`
table is what makes the duplication local: six sets and six staged rules
instead of three of each, plus a second SSH accept, rather than two whole
tables to keep in agreement. The one rule that is *not* doubled is
`KNOCK-8`'s drop, which matches on destination port alone and so covers both
families at once.

## Implementation map

| Path | Realises |
|---|---|
| `roles/firewall/defaults/main.yml` | KNOCK-1, KNOCK-2, KNOCK-7, KNOCK-10 |
| `roles/firewall/tasks/main.yml` | KNOCK-1, KNOCK-2 |
| `roles/firewall/templates/nftables.conf.j2` | KNOCK-1, KNOCK-3, KNOCK-4, KNOCK-5, KNOCK-6, KNOCK-7, KNOCK-8, KNOCK-9 |
| `site.yml` | KNOCK-1, KNOCK-7, KNOCK-10, KNOCK-11 |
| `tests/property/test_firewall_properties.py` | KNOCK-1, KNOCK-3, KNOCK-4, KNOCK-5, KNOCK-6, KNOCK-7, KNOCK-8, KNOCK-9, KNOCK-10, KNOCK-11 |
| `incus/src/incus/vm.py` | KNOCK-5, KNOCK-6, KNOCK-7, KNOCK-10 |
| `docs/port-knocking.md` | KNOCK-1, KNOCK-2, KNOCK-7, KNOCK-9, KNOCK-10, KNOCK-11 |

All eleven requirements appear above, and every row was built by extracting
the IDs actually written into the file rather than by reading intent. Two
rows need reading carefully. `incus/src/incus/vm.py` does not *implement*
anything here — it is the integration suite's VM helper, and it appears
because it is a **consumer**: its re-knock threshold is chosen against
`KNOCK-7`'s pass window, its knock loop depends on `KNOCK-5` and `KNOCK-6`
ordering, and its fallback sequence is a copy of `KNOCK-10`'s default, so a
change to any of those has to be made there too. `docs/port-knocking.md` is
user-facing how-to material that `specs/README.md` places outside this tree;
it carries IDs so a change to a requirement can be traced to the sentences
that describe it to operators, not because the document is part of the
implementation.

`KNOCK-2` is the one requirement no test touches. It is cited on the
assertion task, in the defaults beside the variable it constrains and in the
operator documentation, but no unit test, property test, verification play
or integration test exercises it or renders the template with a sequence of
another length — deleting the task would leave every test in the project
green. `KNOCK-11` is the converse case: three property tests read the play
out of `site.yml`, and none of them runs it.

Files that exercise this spec's output on a live host carry no `KNOCK-N`
citations, and they divide by what they are evidence *for*.
`tests/verify_bootstrap.yml` belongs to `VRFY` and reads a live ruleset for
the *configuration* — that four of the six sets are present and that the
three sequence ports appear — which is a statement about the file the kernel
loaded. Those checks only run at all if the playbook reaches the host, which
on a knock-gated host it cannot do unaided; see `## Failure modes`. The
integration suite, `tests/integration/test_bootstrap_integration.py`
and `tests/integration/test_tailscale_integration.py`, belongs to the
testing spec and is the only place a packet is ever sent at a knock-gated
host: SSH unreachable without a knock, reachable after one, only SSH
reachable after one, and a knock failing to open SSH on a Tailscale host.
Neither spec has been migrated; when they are, those are the sites the
citations belong on, and the division rather than the tally is what decides
which requirement a given test is evidence for.

## Key decisions

**Three stages, fixed, rather than a configurable number.** The sequence
length is a constant of the rules, not a parameter of them: each stage is
written out by hand with its own set and its own membership test, so a
four-port sequence would need a fourth set per family and a fourth rule per
family, and the template has no loop that would produce them. `KNOCK-2`
exists because of this decision and not the other way round — it converts
what would be a rendering failure or a silently truncated sequence into one
assertion with a legible message, at the cost of refusing a configuration
nobody has asked for. Three is where the returns flatten: against an
untargeted scanner one port is already enough, since the scanner is not
trying to knock at all, and against an adversary who is watching the wire
no number of ports helps, because the sequence is in cleartext either way.
What the extra two ports buy is resistance to accidental completion, and
against the default sequence they buy less of that than they look like they
do: `[7000, 8500, 9100]` is ascending, so a scanner sweeping ports upward
hits the three in the order the rules require. That was measured rather than
reasoned about — a non-blocking sweep of ports 6000 to 9200 in ascending
order took 0.02 seconds against the loaded ruleset and left the source in
all three sets, the passed set included. The same sweep in *descending*
order left the source in the stage-1 set only, with stage 2 and the passed
set empty: it reaches 7000 last, so it starts a sequence it has already
walked past instead of finishing one. So three stages buy resistance to a
*narrow* scan and none at all to an upward one, and against an upward one
only `SSH`'s controls stand. A descending or interleaved sequence would not
have that property; the default was not chosen with it in mind.

**Five seconds per stage and thirty seconds for the pass.** Both are the
timeouts on the sets, so nftables enforces them with no rule and no cleanup.
The stage window is short on purpose: it bounds how long a *partial*
sequence is worth anything, and a partial sequence is exactly what a scanner
leaves behind when it touches the first port and moves on. Five seconds is
comfortable for a client sending three packets in a row and useless for
anything slower. The pass window is longer because its job is different —
it has to cover the time between the last knock and the TCP handshake on the
SSH port, over whatever link the operator has. Thirty seconds is generous
for that and short enough that a completed knock is not a standing invitation
if the operator walks away. Neither window is extensible by re-knocking:
`add` on an element that already exists leaves its expiry alone, which was
measured, so a client that wants more time must let the entry lapse and
start the sequence again.

**The explicit drop of the knock ports, which is not redundant with the
policy.** `FW-3` would drop these packets anyway, so the rule looks like
belt and braces until `FW-21` is taken into account. The drop-in include
appends a purpose repository's rules to the end of the same input chain, and
the contract for those rules is `add rule`, which lands them after
everything this spec renders — except for this drop, which precedes them.
Without it, a purpose repo that opened one of the knock ports for a service
of its own would make that port answer a SYN, which is precisely the signal
the whole scheme withholds, and would do so without anyone connecting the
two files. It was measured rather than assumed: with the rendered branch
loaded and a listener bound to the first knock port, appending
`add rule inet filter input tcp dport 7000 accept` left connections to that
port dropped. The same rule is what keeps a future logging rule from
recording every knock.

What the drop does **not** govern is the two unconditional accepts above it,
and `KNOCK-8` is worded around that: `FW-6` and `FW-7` are evaluated before
anything this spec renders, so a loopback connection to a knock port is
accepted by `FW-7` and never reaches the progress rules or the drop.
Measured on the full rendered ruleset: such a connection succeeded and left
every knock set empty, and the same connection against a copy with `FW-7`'s
rule removed was dropped and populated the stage-1 set. A local process is
not the adversary this spec is about, so that is the right outcome — but it
is the reason this design does not say the knock ports are silent on every
path, only on every path that reaches these rules.

**Mutual exclusivity with Tailscale, not composition.** A host could in
principle have both, and the template does not allow it: the set block and
the rule branch are both conditioned on Tailscale being off. The reason is
that the two do not compose in the direction an operator would expect.
`FW-10` narrows SSH by *interface*, and a knock cannot widen an interface
match, so knock rules on a tailnet host would open three ports to the
internet and grant nothing — the passed set would fill and no SSH rule would
read it. Worse, it would read as a second way in, so an operator locked out
of the tailnet might spend the outage knocking. The integration suite has a
test for exactly that expectation,
`test_port_knocking_does_not_bypass_tailscale`, which knocks a
Tailscale-enabled host and requires SSH to stay closed. The cost of the
decision is that there is no configuration in which a host is behind both,
which nobody has needed, and that the three branches must stay genuinely
exclusive — a template change that decoupled the knock branch's condition
from the Tailscale flag would put both branches on one host, with three
knock ports open on a tailnet-only machine.

**A separate local play rather than a task in the bootstrap play.** The
knock has to happen before Ansible opens its SSH connection, and a task
inside the bootstrap play is already too late — the connection is
established when the play's first task runs. A play with `connection: local`
and `gather_facts: false` runs entirely on the controller and touches the
target only with the three knock packets. The knock itself is an inline
Python snippet rather than a shell loop or a dependency on the `knock`
client, because the controller is guaranteed to have Python — Ansible needs
it — and is not guaranteed to have `knockd` installed. It reports
`changed_when: false` because knocking alters nothing.

## Failure modes

- **A sequence the operator cannot reproduce locks them out of the host, and
  the break-glass script does not cover this branch.** `KNOCK-2` catches a
  sequence of the wrong length and nothing else: a sequence of three ports
  an intermediate firewall blocks, or three ports the operator has recorded
  wrongly, renders and loads cleanly and leaves a host whose SSH port
  answers nobody. The run that does it will not notice, because Ansible's
  own connection was established before the reload and survives it under
  `FW-6`. `INV-6` is what makes this recoverable rather than terminal, and
  it applies in its plainest form: the sequence is written into
  `/etc/nftables.conf` in the clear, so an operator at the provider's
  console can read the three ports back out of the file, or delete the knock
  branch and reload, with no network of any kind. What does **not** help is
  the emergency-access script. It is deployed only when Tailscale is
  enabled, which is exactly when this spec is inactive, and its edits target
  `FW-10`'s `iifname`-qualified rule, which a knock-gated host does not
  have. So `INV-6` holds here by the file being editable, not by there being
  a tool — and an operator who expects the script on a knocking host will
  not find one.
- **Nothing verifies that a knock works before the host starts requiring
  one, so `INV-8` is not upheld on this branch.** `requirements.md`'s
  `## Security invariants` states the case in full; the mechanics are these.
  `KNOCK-11`'s play looks like the verification and is not: its inline
  snippet suppresses every `OSError`, inspects no result and is
  `changed_when: false`, so it reports success whether or not the packets
  reached anything — a knock draws no reply, so there is nothing it could
  inspect — and on a first run it executes before the ruleset exists at all.
  The run that applies the narrowing cannot notice either, because its own
  connection predates the reload and is carried through it by `FW-6`. A
  later run does knock and then connect, so a normal success does
  demonstrate the path works, but after the fact rather than before, and
  `ansible.cfg`'s `ControlPersist=60s` over a control path stable across
  runs means a quick re-run can succeed on the previous run's multiplexed
  connection without the knock mattering. The first unambiguous test of a
  host's knock configuration is a fresh connection more than a minute after
  the run that closed it. Resolving this means either adding a real
  post-narrowing check that fails the run, or claiming an allowance against
  `INV-8`; neither is done here, and no allowance is claimed.
- **A ruleset reload empties every knock set**, which is the one thing that
  removes an entry without `KNOCK-7`'s timers, and which that requirement's
  SHALL scopes around by name — "among the rules it renders … the destruction
  of the sets themselves by `FW-15`'s flush excepted". Measured: with the rendered
  branch loaded and a source in the passed set, re-running `nft -f` on the
  same file left the passed set empty. `FW-15`'s `flush ruleset` destroys
  the sets and the file recreates them empty, so every partial and completed
  knock on the host is discarded by `FW-19`'s handler at the end of any run
  that changed the ruleset, by a manual reload, and by a reboot. Established
  SSH connections are unaffected — `FW-6` accepts them on connection state —
  but a source that knocked and had not yet connected must knock again, with
  no signal that anything happened. No requirement in either spec states it;
  `docs/port-knocking.md` warns operators about it under troubleshooting,
  which is the only place it is written down for the people it affects.
- **The stage-1 set is fillable by anyone, and its only bound is a default
  this file does not state.** `KNOCK-4` admits any source that sends one
  packet to one port, with no rate limit and no authentication, so the set
  grows with the rate of incoming traffic to that port. What bounds it is
  `KNOCK-7`'s five-second expiry and `nft`'s own default set size, which a
  live listing shows as `size 65535` with `flags dynamic,timeout` — neither
  of which is written in the template. What happens at that limit was **not**
  measured; the expectation is that further `add`s fail, which would fail
  *closed* for a legitimate knocker rather than open anything, making the
  consequence a denial of the knock path rather than of SSH, and only for as
  long as the flood lasts. Nobody has tested it.
- **The default sequence is completed by an ordinary ascending port scan.**
  Measured: against the loaded ruleset, a non-blocking sweep of ports 6000
  to 9200 in ascending order completed in 0.02 seconds and left the source
  in all three sets, the passed set included. The same sweep descending left
  the source in the stage-1 set only — it hits 7000 last, so it starts a
  sequence rather than completing one — with stage 2 and the passed set
  empty. A scanner that walks ports upward therefore passes the knock as a
  side effect of scanning and finds the SSH port open, which returns the host to
  the posture `FW-13` would have given it against that one adversary. This
  is the sharpest illustration of the `## Security invariants` claim that
  knocking is not authentication: it defeats the scan that does not bother,
  not the scan that is thorough. Choosing a non-monotonic sequence in
  inventory removes the property; the default does not have it removed.
- **Turning `port_knocking_enabled` off on a re-run silently publishes the
  SSH port.** The flag selects between this spec's branch and `FW-13`'s, so
  a re-run with the flag flipped renders the unqualified accept, and
  `FW-19`'s handler loads it at the logging role's handler flush. Nothing
  warns, and the
  run reports one changed template among many. `INV-9` is not violated —
  the operator asked for it — but the gap between the size of the inventory
  edit and the size of the change to the host's exposure is worth naming.
- **The role-level variables can be overridden directly, and then the
  controller-side play knocks the wrong ports.** `KNOCK-10`'s derivation is
  what keeps the ruleset and `KNOCK-11`'s play in agreement: both read
  `port_knocking_sequence`, so an inventory that sets that one variable
  moves both. An inventory that instead sets `firewall_port_knocking_sequence`
  — the role-level name, which is equally settable — moves the ruleset and
  not the play, and the next run's knock goes to the old ports. The same
  applies to `firewall_port_knocking_enabled` against the play's
  `port_knocking_enabled`. Nothing asserts the two agree.
- **Every property test of this mechanism reads the template as text, and
  several generate values no assertion uses.** `test_knock_sequence_ports_in_template`
  draws a three-port sequence it never reads;
  `test_timeout_variables_used`, `test_no_unconditional_ssh_accept_with_knocking`
  and `test_defaults_define_knock_variables` each draw an address family
  they never read. Those four run the same fixed substring check 100 times
  and would pass unchanged with their decorators deleted. More consequential
  than the wasted examples is what none of them do: no test in the default
  suite renders the knock branch at all. The unit suite's `base_vars` sets
  `firewall_port_knocking_enabled: False`, so `tests/unit/test_firewall.py`
  renders the open branch and the tailnet branch and never this one, even
  though the same fixture carries a knock sequence and both timeouts, which
  makes them look load-bearing to a reader. Every claim this spec makes
  about *rendered* output rests on the integration suite, on
  `verify_bootstrap.yml`, or on the measurements recorded in this document.
- **Two assertions about rule ordering are guarded so that they skip rather
  than fail.** `test_sets_at_table_level` and
  `test_explicit_drop_for_knock_ports` both locate two line numbers by
  substring and only compare them `if` both were found. Renaming a set or
  rewording the drop rule makes the search find nothing, which makes the
  comparison disappear, which is a pass. They can catch a reordering; they
  cannot catch a deletion.
- **`make verify` cannot reach a knock-gated host at all.** The verification
  playbook is a single `hosts: all` play with `gather_facts: true` and **no
  knock play of its own**, and `make verify` runs it directly with no extra
  variables. So against a host this spec has closed, the run fails
  UNREACHABLE at fact gathering, before any verification task is evaluated.
  There are exactly two ways it succeeds: an operator knocks by hand
  immediately beforehand, or the run starts inside the window in which a
  previous run's SSH connection is still multiplexed — `ansible.cfg` sets
  `ControlPersist=60s` over a control path that is stable across runs. The
  integration suite demonstrates the first of those: its verification test
  calls the VM's `knock()` before running the playbook, and would not pass
  without it. `KNOCK-11`'s play cannot help, because it lives in `site.yml`
  and the verification playbook is a different file. This belongs to `VRFY`;
  it is recorded here because knocking is what makes it true, and because an
  operator needs to know that `make verify` is not a command they can run
  unaided on a knock-gated host.
- **`verify_bootstrap.yml` also dereferences `port_knocking_sequence` with
  no default.** Its "Verify port knocking sequence ports in NFTables" task is
  gated on `port_knocking_enabled | default(true)`, so it is selected on a
  host that configured nothing, and then evaluates
  `port_knocking_sequence[0]`, which has no `| default(...)` and is defined
  in none of the inventory examples. Ansible fails hard on that — measured:
  `object of type 'list' has no attribute 2` for the analogous out-of-range
  case. This is a second, independent defect, but it is **not** what an
  operator hits first: the bullet above means the task is normally never
  reached. It becomes reachable exactly when the run gets past fact
  gathering — after a manual knock, or on a reused connection. Also `VRFY`'s;
  recorded here because the variable is `KNOCK-10`'s.
- **A knock port that collides with the SSH port would close SSH
  permanently.** `KNOCK-8`'s drop names the sequence ports and precedes
  `KNOCK-9`'s accept, so a sequence containing the SSH port would drop every
  SSH packet before the accept could match — including the packets of a
  source that had completed the knock. `KNOCK-2` checks the length of the
  sequence and nothing about its contents, and no other check compares the
  two. The configuration is absurd and nothing prevents it.

## Interactions

**What this spec assumes of others:**

- `FW-3` — the input chain's policy is `drop`. This is what makes the knock
  ports and the SSH port *silent* rather than refused, and silence is the
  entire product: a port that answers with a reset has told the scanner the
  host exists and is filtering. It is also the backstop behind every rule
  here — a source that never completes the sequence is refused by the policy,
  not by any rule this spec writes.
- `FW-6` — established and related connections are accepted before any
  service rule. `KNOCK-7`'s pass window would otherwise be a session length
  limit: an SSH connection would be cut thirty seconds after the knock that
  admitted it, and a bootstrap run would not survive its own firewall role.
  Measured with the window shortened: a connection established inside it
  still carried traffic after the entry had expired, while a new connection
  from the same source was refused. The position matters as much as the
  rule — `FW-6` sits above everything this spec renders, which
  `specs/firewall/design.md` also records from its side.
- `FW-7` — loopback traffic is accepted, above everything this spec renders.
  This spec assumes it and does not work around it: a local process reaches
  sshd or a knock port over `127.0.0.1` without knocking and without
  recording progress, which is correct, and which is why `KNOCK-8`'s SHALL
  is scoped to the rules that follow it rather than to the whole chain.
- `FW-2` — one `inet` table, so the six sets and both rule groups live in
  the same table as the chain that reads them, and IPv6 is governed by the
  same construction as IPv4 rather than by a parallel one.
- `FW-15`, `FW-16`, `FW-19` — the rendered file is the complete statement of
  the firewall, it is deployed to the path the service reads, and a change
  to it is reloaded. This spec adds nothing to that path and depends on all
  of it. The consequence it must live with is `FW-15`'s flush, which empties
  the knock sets on every reload; see `## Failure modes`.
- `FW-14` — the SSH port named in `KNOCK-9`'s two accept rules is the port
  `SSH-13` configured. Neither rule here reads `ssh_port` directly.
- `FW-13` — the branch that is *not* taken while this spec is active. It is
  worth stating the direction: `FW-13`'s own condition requires both flags
  false, and `firewall_port_knocking_enabled` defaults to true, so a host
  with neither a tailnet nor an explicit `port_knocking_enabled: false`
  reaches this spec's branch and `FW-13`'s rule is never rendered for it.
- `SSH-1`, `SSH-2`, `SSH-3` — public keys only, no root, no passwords. These
  are what make `KNOCK-9` defensible, in the same way they make `FW-13`
  defensible, and for a stronger reason: a source that has completed the
  sequence is in exactly the position a source on an open SSH port is in,
  and the sequence establishes nothing about who it is.
- `TS-1` — `tailscale_enabled` defaults to false, which is why this spec's
  branch is the one an unconfigured host takes.
- `PRJ` — `site.yml` carries `KNOCK-11`'s play as its first play, and the
  inventory is where the four top-level knock variables would be set. None
  of the inventory examples in the repository sets any of them, so the
  values a host actually gets are `KNOCK-10`'s defaults unless a deployment
  adds them; `PRJ` provides the place, not the values.

**What others may assume of this spec:**

- `F2B` — that it will see fewer authentication failures, and that the ones
  it does see came from a source that completed a knock. It may **not**
  assume it will see none, and nothing here changes what it does: the jail
  reads sshd's log, which is written after the firewall has already admitted
  the connection, so the two are independent layers and fail2ban's bans
  apply to knock-passed sources exactly as they would to any other. That
  spec is now written and its `## Interactions` records both halves against
  `KNOCK-9`: that nothing here disturbs its own ban table, since this spec's
  sets and rules all live inside `FW`'s `inet filter` table and only
  `FW-15`'s flush reaches `inet f2b-table`, and that this spec is upstream
  of its evidence rather than a substitute for it.
- `VRFY` — that a completed bootstrap leaves the six sets and the staged
  rules in the deployed file, that the SSH port is open to no source that
  has not knocked, and that the sequence in the file is the one
  `port_knocking_sequence` named. What it may **not** assume is that the
  kernel holds any knock progress: the sets are empty after every reload and
  after every boot, so a check that reads elements out of them is checking
  the last few seconds of traffic, not the configuration. The checks it
  already makes — four of the six sets present in a live ruleset, the three
  ports present in it — are configuration checks and are the right shape for
  that reason. Its undefined-variable bug on `port_knocking_sequence` is
  recorded under `## Failure modes`.
- The testing spec, and `incus` as its helper — that the sequence a
  bootstrapped test VM requires is `KNOCK-10`'s default unless the playbook
  was given another, and that a knock stays good for `KNOCK-7`'s thirty
  seconds. Every knock the integration suite performs is an explicit
  `knock()` call written into the test, and the tests otherwise reach the VM
  through `incus exec`, which is not an SSH path and needs no knock at all.

  The helper also has an **auto-knock** path — `ssh()` and the readiness
  poll re-knock when the last knock was more than twenty seconds ago, twenty
  being chosen to leave margin inside thirty rather than for any reason of
  its own. As this repository is wired, that path never runs: both guards
  require `knock_sequence` to be set, nothing in `tests/integration/`
  constructs a VM with it, and no integration test calls `ssh()`. It is
  exercised only by unit tests against mocks, and it exists for the purpose
  repositories that `docs/multi-repo-strategy.md` tells to set
  `knock_sequence`. For those consumers the coupling is real — shortening
  the pass window below twenty seconds would open a gap in which the helper
  still believes its knock is good and the host has already forgotten it,
  and no test would fail, because no test names either number.

  The helper's fallback sequence is a copy of `KNOCK-10`'s default rather
  than a read of it, because it is not an Ansible consumer and has no
  inventory to read; the integration suite's own variable set carries a
  further copy for the same reason. They agree today and nothing checks that
  they do.
- The emergency-access spec — that it has **no** interaction with this spec
  and should not be understood to provide a recovery path for it. Its script
  is deployed only on Tailscale-enabled hosts, where nothing here is
  rendered, and it edits `FW-10`'s rule, which a knock-gated host does not
  have. Recovery from a knock lockout is console editing of
  `/etc/nftables.conf` by hand. Not yet written; when it is, the thing to
  record against an ID is the gap rather than a dependency.
- Purpose repositories — that the three sequence ports are not available for
  a service of their own. A drop-in rule accepting one of them is appended
  after `KNOCK-8`'s drop and never reached, which was measured, so the
  service would silently fail to be reachable rather than fail to start.
  This is not hypothetical for the default sequence: 9100 is Prometheus
  node_exporter's default listening port, so a purpose repo that deploys
  node_exporter on a knock-gated host must move one of the two, and nothing
  will tell it which problem it has. `FW-21`'s contract otherwise applies
  unchanged.
