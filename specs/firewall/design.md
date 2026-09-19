# Firewall — Design

## Approach

The role is six tasks and one template, and the first task — the knock
sequence length assertion — belongs to the port-knocking spec rather than
this one. The other five install `nftables`, create the drop-in directory,
render one file over `/etc/nftables.conf`, enable the service and start it;
a handler reloads the service when the file changed. Everything this spec
requires about *packets* is a line in that one template, and everything it
requires about *persistence* is one of the deployment and service tasks.
There is no second place a rule could come from and no partially applied
state: the template renders whole or not at all, and the ruleset loads whole
or not at all.

That last point is the structural decision the rest of the design rests on.
`nft -f` applies a file as a single kernel transaction. `FW-15`'s
`flush ruleset` sits inside that transaction, so the deployed file is the
complete statement of the host's firewall — what a reviewer reads is what
the kernel enforces, with no accumulated residue from earlier revisions —
and yet a file that fails to parse applies nothing and leaves the running
rules exactly as they were. Both halves were measured: reloading the
rendered ruleset with a syntactically invalid drop-in present left the
previously loaded chains untouched, and reloading it after another tool had
created a table of its own removed that table.

That construction is also how this spec upholds `INV-9`. `FW-16`'s
declarative deploy converges the file and `FW-15`'s flush converges the
kernel to it, so a re-run cannot leave a rule an earlier revision created
sitting behind the current ruleset, and cannot half-apply the new one. The
two are load-bearing only together: a declarative deploy without the flush
would accumulate, and a flush without a converging deploy would have nothing
dependable to flush to.

The ruleset itself is one `inet` table with three base chains. Input and
forward default to drop, output to accept. The input chain is four
unconditional accepts — stateful, loopback, ICMPv4, ICMPv6 — followed by
exactly one of three mutually exclusive SSH branches chosen by two flags,
followed by nothing. The chain has no terminal rule, which is what makes
`FW-21`'s drop-in include work: an appended `add rule` is still reached, and
only the `FW-3` policy comes after it.

Two of this role's variables are not its own. `firewall_ssh_port` derives
from `SSH-13`'s `ssh_port` and `firewall_tailscale_interface` from `TS-14`'s
`tailscale_interface`, so the rules and the things they are about cannot
name different values. The third indirection, `firewall_tailscale_ipv4`, is
dead — no rule reads it; see `## Failure modes`.

## Implementation map

| Path | Realises |
|---|---|
| `roles/firewall/defaults/main.yml` | FW-10, FW-11, FW-12, FW-13, FW-14 |
| `roles/firewall/tasks/main.yml` | FW-1, FW-16, FW-17, FW-18, FW-19, FW-20 |
| `roles/firewall/templates/nftables.conf.j2` | FW-2, FW-3, FW-4, FW-5, FW-6, FW-7, FW-8, FW-9, FW-10, FW-11, FW-12, FW-13, FW-14, FW-15, FW-21 |
| `roles/firewall/handlers/main.yml` | FW-19 |
| `tests/unit/test_firewall.py` | FW-2, FW-3, FW-4, FW-5, FW-6, FW-7, FW-8, FW-9, FW-10, FW-11, FW-12, FW-13, FW-14, FW-15 |
| `tests/property/test_firewall_properties.py` | FW-1, FW-2, FW-3, FW-4, FW-5, FW-6, FW-7, FW-8, FW-9, FW-10, FW-11, FW-12, FW-13, FW-14, FW-16, FW-17, FW-18, FW-19 |
| `tests/property/test_playbook_behavior_properties.py` | FW-19 |

Every one of the twenty-one requirements appears above, and every row was
built by extracting the IDs actually present in the file rather than by
reading intent. Two requirements are cited in exactly one place each, and
both are the extension contract: `FW-20` only on the task that creates
`/etc/nftables.d`, and `FW-21` only on the `include` line in the template.
Neither has a test of any kind anywhere in the project — no unit test,
property test, verification play or integration test mentions
`/etc/nftables.d` at all — so the single citation is the whole of their
traceability. `FW-15` is cited in the template and the unit suite but not
the property suite, because the property suite's only assertion touching it
is `"flush ruleset" in template_content or "table inet filter" in template_content`,
which the second alternative always satisfies.

Three files exercise this role's output on a live host and carry no `FW-N`
citations: `tests/verify_bootstrap.yml`, which belongs to `VRFY`, and
`tests/integration/test_bootstrap_integration.py` and
`tests/integration/test_tailscale_integration.py`, which belong to the
testing spec. None has been migrated yet; when they are, these are the sites
the citations belong on. `verify_bootstrap.yml` asserts against a live
`nft list ruleset` for `FW-3`, `FW-4`, `FW-6` and `FW-7`, checks the unit
state for `FW-17` and `FW-18`, and searches for the SSH port for `FW-14`.
The integration suite is the only place in the project where this ruleset is
exercised behaviourally at all. Several of its tests require a connection to
fail, and `FW-3`'s policy is what drops the packet in all of them, but they
divide by what they were written to show. Two are aimed at the policy
itself: `test_non_ssh_port_blocked_despite_listening_service` starts a
listener on port 8080 inside a bootstrapped VM and requires the connection
to fail, and `test_only_ssh_reachable_after_knock` requires ten common ports
to be unreachable. The others — `test_ssh_blocked_without_knock`,
`test_port_knocking_does_not_bypass_tailscale` and `test_ssh_closed_from_host`
among them — are written as evidence that a branch's access control refuses
what it should, and a reader diagnosing one of their failures would look at
that branch rather than at the policy. The division is what matters here,
not the tally: a test added to either side does not change which requirement
it is evidence for.
Nothing live covers `FW-1`, `FW-2`, `FW-5`, `FW-8`, `FW-9`, `FW-11`,
`FW-12`, `FW-13`, `FW-15`, `FW-16`, `FW-19`, `FW-20` or `FW-21`, and
`FW-10`'s live coverage does not isolate it from `SSH-18`.

`docs/multi-repo-strategy.md` describes the same drop-in contract for
purpose repositories, including the `add rule` requirement and a worked
example. It carries no requirement IDs; it is user-facing how-to material,
which `specs/README.md` places outside this tree deliberately.

## Key decisions

**One `inet` table, not an `ip` table and an `ip6` table.** nftables offers
both, and the two-table form is what an iptables-shaped mental model
reaches for. It was not chosen. `INV-4` requires the drop policy to hold
identically for IPv4 and IPv6, and the surest way to guarantee identical is
to have only one thing. In the `inet` family a base chain sees both
families, so `FW-3`'s `policy drop` is written once and governs both; a rule
is family-specific only where it says so, and among the rules this spec owns
exactly two do — `FW-8`'s `ip protocol icmp` and `FW-9`'s
`ip6 nexthdr icmpv6`, which are family specific because the protocols are.
The port-knocking branch adds its own family-specific matches, which is why
it renders a pair of sets and a pair of rule groups where this spec renders
one of each. With two tables every other rule would exist twice, and the
failure mode of that duplication is not a broken host
but a quietly asymmetric one: an IPv6 table missing a rule its IPv4 twin has
is invisible to an operator who tests over IPv4, which is most operators,
most of the time. The cost is that the table cannot hold an IPv4-only match
in a chain the kernel evaluates for IPv6 without the family qualifier being
explicit — a cost this spec's own rules pay twice and nowhere else.

**Restricting SSH by interface, not by address.** `FW-10` matches
`iifname "tailscale0"`. The alternative available — matching the tailnet
address the `TS` role publishes, which this role already inherits as
`firewall_tailscale_ipv4` — was not chosen, and the variable's presence is
the fossil of that decision rather than evidence for it. Matching a
destination address would restate what `SSH-18` already does, since sshd is
bound to that address and packets for any other never reach it; matching a
*source* address would be worse than useless, because a source address is
the one field an attacker controls completely, and a rule admitting packets
that merely claim a `100.64.0.0/10` source would open SSH to the internet
while reading as a restriction. The interface a packet arrived on is not
forgeable from outside the host: a packet that entered on the public
interface did not enter on `tailscale0`, whatever it claims. The cost is a
dependency on a name — `FW-11` takes `firewall_tailscale_interface` on
trust, and nothing here checks that an interface by that name exists or
carries the tailnet. That is the whole of the reliance on `INV-8`.

**Two independent controls on the SSH path, not one.** On a Tailscale
enabled host, `SSH-18` binds sshd to the tailnet addresses and `FW-10`
admits SSH only on the tailnet interface. Either alone would keep a public
client out. They are kept as two because they fail differently and
independently: an sshd bound to a stale address fails closed but leaves the
firewall's rule correct, while a firewall rule naming a renamed interface
fails closed but leaves sshd's binding correct, and a mistake in one is not
a mistake in the other. `specs/ssh-hardening/design.md` records the same
decision from the other side and makes the stronger point that the binding
is the control that makes the service *absent* rather than merely filtered.
This design agrees with that ordering and does not claim `FW-10` is
redundant with it, or it with `FW-10`. The integration suite tests exactly
one direction of the independence: `test_ssh_closed_without_firewall` stops
nftables and flushes the ruleset, then requires SSH from outside the tailnet
to still fail. Nothing does the converse.

**The drop-in directory as the extension point, and the glob that makes it
safe.** A purpose repository layered on this bootstrap needs to open ports
this spec has never heard of. The alternatives were a variable holding a
list of extra rules, which puts purpose-specific data in bootstrap-owned
inventory and re-renders the whole ruleset for every change, or letting
purpose repos edit `/etc/nftables.conf`, which loses the file to the next
bootstrap run. `FW-20` and `FW-21` instead give the purpose repo a
directory of its own that no bootstrap task writes to, and put the `include`
last so an appended `add rule` is reached by packets the base rules did not
already decide. Three properties of the mechanism were measured rather than
assumed: a wildcard include matching nothing is not an error, so a host with
an empty or absent drop-in directory loads the base ruleset unchanged (an
`include` of a *named* missing file is an error, which is why the glob is
not a convenience); a drop-in's `add rule` lands as the last rule of the
input chain, after the SSH rule and before the policy takes effect; and a
drop-in that fails to parse fails the whole load atomically, changing
nothing. The contract's one hard constraint follows from `FW-15`: a drop-in
must use `add rule` and must not re-declare the table or flush, because it
is included *inside* the same transaction as the flush, not after it.

**A reload handler rather than a restart, and rather than an inline
service call.** `state: reloaded` runs the unit's reload command. The
packaged unit's `ExecStart` and `ExecReload` are the same command —
`/usr/sbin/nft -f /etc/nftables.conf` — so nothing is saved and restored,
and a reload and a boot load the identical ruleset by the identical path.
The unit is `Type=oneshot` with `RemainAfterExit=yes`, so its `active` state
records that the last load succeeded rather than that anything is running;
this matters to `VRFY`, below. Using a handler means a converged host is not
disturbed by a run that changed nothing — with an unconditional restart,
every `make bootstrap` would briefly flush the firewall of a host whose
configuration was already correct. The cost is Ansible's deferral: the
handler fires at the end of the *play*, not of this role, so on a run that
changes the ruleset the host enforces the old rules through every role that
follows.

**Enable and start as two tasks, not one.** `systemd` would accept
`enabled: true` and `state: started` in a single task. They are separate
because they answer separate requirements with separate consequences —
`FW-17` is about the next boot and `FW-18` about this minute — and because
the property suite's task walk reads them independently, though only by a
one-line margin; see `## Failure modes`. Nothing depends on the ordering
between them.

## Failure modes

- **The deployed ruleset is not validated before it is installed, so a
  template that renders to something `nft` cannot parse is written to disk
  anyway, and on two of the three paths that follow it leaves the host
  unfiltered.** `FW-16`'s deployment task has no `validate:` hook, unlike
  the sshd_config task that `SSH-19` covers. `nft -c -f <file>` is exactly
  the check that would fit — it parses and commits nothing — and it is not
  used. The three cases differ sharply. On a **re-run against a host whose
  ruleset is already loaded**, the damage is contained: the reload handler
  fails, the run fails with it, and because the load is atomic the
  previously loaded rules stay in force, so the host is still filtered and
  still reachable. On a **first run**, where the service has never started,
  there is nothing loaded to fall back to, and the failure arrives before
  the handler rather than at it: `FW-18`'s start task is itself an `nft -f`
  of the bad file, so the unit fails, the task fails, and the play aborts
  for that host — leaving it unfiltered, as it was before the run began, and
  now also half-configured, with the roles after this one never executed.
  The run does fail loudly, which is the one mercy here. On the **next
  boot** of a host in either state, the same load fails the same way with no
  signal: `nftables.service` fails, the kernel holds no base chains at all,
  and a host with no base chains filters nothing — every socket any package
  has open is reachable from the internet, and the only trace is a failed
  unit nobody is watching at boot time. This is the inverse of the usual
  firewall failure: it fails open, not closed, and in the boot case it fails
  at the moment least likely to be observed. The same applies to a
  drop-in file that was valid when written and is not valid for the
  installed `nft` version. Adding `validate: /usr/sbin/nft -c -f %s` would
  close the template half of this; note that the check needs `CAP_NET_ADMIN`
  even though it commits nothing — run unprivileged it fails at
  `flush ruleset` with `Operation not permitted` — so it must run under the
  task's existing `become: true`.
- **Stopping the nftables service removes the firewall entirely rather than
  reverting it.** The packaged unit's `ExecStop` is `nft flush ruleset`, so
  a stopped service is a host with no base chains and therefore no
  filtering at all — the same open state a failed boot load produces, and
  the reason `systemctl stop nftables` is not a way to "disable the
  firewall temporarily" on a reachable host. The unit also carries
  `ConditionFileNotEmpty=/etc/nftables.conf`: if that file were ever
  rendered empty the unit would be skipped rather than failed, which
  systemd reports as a *successful* condition check and which leaves the
  host equally unfiltered. Nothing in this role guards against either. The
  first behaviour is used deliberately by the tailscale integration suite's
  `test_ssh_closed_without_firewall`, which stops the service to prove that
  `SSH-18` holds without the firewall.
- **`test_critical_configs_use_validation` exists to catch exactly the
  preceding gap and asserts nothing.** The test maps `nftables.conf` to this
  role, reads the tasks file, computes `has_validate = "validate:" in
  tasks_content`, and then branches into two bodies that both consist of a
  comment and `pass`. It cannot fail, for this role or for the two others it
  parametrises over. A reader scanning test names would reasonably conclude
  validation is covered.
- **`FW-15`'s flush removes every table in the kernel, not only the one this
  file defines.** Measured: with the rendered ruleset loaded, a second table
  created alongside it was gone after reloading `/etc/nftables.conf`, and
  nothing recreated it. So whatever rules another tool maintains in its own
  table do not survive a reload of this file, a re-run of this role that
  changes the ruleset, or a reboot, unless that tool notices and rebuilds
  them. The case that matters here is fail2ban, which `F2B` configures to
  use the `nftables-multiport` ban action: on a reboot fail2ban restarts too
  and rebuilds its jail, so the window is short and self-healing, but on a
  reload the firewall is reloaded by a handler at the end of a play and
  nothing restarts fail2ban after it, so a host can run with its active bans
  silently discarded until something else does. Nothing in either role
  notices, and no test covers it. The narrower `flush table inet filter`
  would avoid it, at the cost of leaving behind tables an earlier revision of
  this file created.
- **The break-glass script's firewall edit is reverted by the next bootstrap
  run.** The emergency-access script restores public SSH by rewriting
  `FW-10`'s rule inside `/etc/nftables.conf`. That is the very file `FW-16`
  re-renders from this role's template on every run, so the next
  `make bootstrap` against that host puts the `iifname` qualifier back —
  silently, as one `changed` result among many, with `FW-19`'s handler
  reloading the narrowed ruleset at the end of the play. An operator who
  used the break-glass path, fixed the tailnet and then re-ran the playbook
  gets the right outcome; one who used it and re-ran the playbook for an
  unrelated reason while the tailnet was still broken is locked out again by
  their own run. Nothing in either role warns about this. It is the exact
  counterpart of the hazard `specs/ssh-hardening/design.md` records for the
  script's `sshd_config` edits, and it bites at the same moment, because
  both files are re-rendered in the same play.
- **`firewall_tailscale_ipv4` is dead configuration.** The variable is
  defined in this role's defaults, indirects through the `TS` role's
  published fact, and is read by no task, no template and no rule. It is
  also set in two test fixtures — `tests/unit/conftest.py` and
  `tests/unit/test_firewall.py`'s `tailscale_vars` — which makes it look
  load-bearing to a reader of the tests. `specs/tailscale/design.md` names
  it as something the firewall consumes, which was true of the intent and
  has never been true of the code. No requirement covers it, because there
  is nothing to require; it is recorded here so the next reader does not
  reconstruct a rule from its presence. Deleting it would change no rendered
  output.
- **Three of the property suite's defaults-file assertions cannot fail.**
  Each is written as a specific check `or` a weaker one that the specific
  check's own subject satisfies:
  `"{{ ssh_port" in defaults_content or "ssh_port" in defaults_content` is
  satisfied by the string `firewall_ssh_port:`;
  `"{{ tailscale_interface" ... or "tailscale_interface" ...` by
  `firewall_tailscale_interface:`; and
  `"firewall_wireguard_port: 41641" ... or "firewall_wireguard_port:" ...`
  by the key alone, whatever value follows it. The same pattern appears for
  `tailscale_enabled`. So the defaults could be changed to hard-coded
  literals, or the WireGuard port to any number at all, and
  `test_property_19_nftables_ssh_access_control` would stay green — which
  matters because those assertions are the only place in the default suite
  that reads `defaults/main.yml` for these values at all. The unit suite's
  `base_vars` is a hand-written copy of the same defaults, so its
  "renders the configured value" assertions confirm the fixture, not the
  role. This is the same inert-verification pattern recorded against the
  tailscale, ssh-hardening, user-accounts and swap specs; no test was
  changed.
- **The four `test_property_*` tests in the firewall property suite generate
  values no assertion reads.** `valid_ssh_port`, `valid_interface_name` and
  `valid_wireguard_port` feed parameters that those four test bodies never
  use: every assertion is a substring check against a file on disk, so each
  test runs the same fixed check 50 or 100 times and would pass unchanged
  with the decorators deleted. What those four verify is a text corpus, not
  a property over an input space. Identical to the finding recorded for
  `TS`. The knock tests in the same file are not all like this —
  `test_knock_rules_conditional_on_tailscale_and_knocking` does branch on
  its two generated flags — so the criticism is of the four named tests, not
  of the suite as a whole.
- **`FW-17`'s and `FW-18`'s task walk separates the two tasks by one line,
  and separated them by none before this spec was written.**
  `test_property_21_nftables_service_persistence` looks for a systemd task
  naming `nftables` by taking a fixed ten-line window from each
  `ansible.builtin.systemd:` line and asking whether `enabled: true` and
  `state: started` appear in it. Whether that reads one task or two is a
  function of how many comment lines sit between them, which nothing
  guarantees. Measured on this role's task file: before this spec's
  citations were added, the enable task's window ran to line 51 and
  `state: started` sat on line 50, so `found_start_task` was already
  satisfied from the *enable* task's window and that half of the assertion
  was inert — deleting the start task entirely would not have failed it.
  The citation comments added here pushed the two apart, so each key is now
  found only in its own task's window, but the margin is exactly one line:
  removing a single comment line restores the old, inert behaviour with no
  test failure to announce it. The fix is to slice to the next line
  beginning a task rather than to a fixed offset. No test was changed here,
  per this plan's rules; this bullet is the record.
- **`test_property_19`'s "Tailscale block" is not the Tailscale block.** The
  test extracts the conditional branch by scanning from
  `{% if firewall_tailscale_enabled | bool %}` until a line containing
  `{% else %}` or `{% endif %}`. The template's next conditional line is
  `{% elif firewall_port_knocking_enabled | bool %}`, which contains
  neither, so the extracted "block" runs on through the entire
  port-knocking branch and stops only at the final `{% else %}`. Its
  assertions happen to hold because the real Tailscale branch is inside the
  over-wide region, but `assert "accept" in tailscale_block` and
  `assert "tcp dport {{ firewall_ssh_port }}" in tailscale_block` would also
  hold if the Tailscale branch were emptied entirely, since the knock branch
  supplies both strings. The `{% else %}` extraction immediately below it is
  correctly scoped.
- **Nothing in the default suite checks that the three SSH branches are
  mutually exclusive, and nothing exercises two of them on a live host.**
  The unit suite renders the Tailscale branch and the open branch, never the
  knock branch; `test_knock_rules_conditional_on_tailscale_and_knocking`
  generates both flags but asserts against the raw template text rather than
  rendered output, so it never observes which branch a flag combination
  actually produces. The integration suite bootstraps with the default
  configuration — Tailscale disabled, knocking enabled — so `FW-13`'s open
  branch is never exercised live, and `FW-10`'s branch is exercised only in
  the tailscale integration environment, where `SSH-18` is narrowing the
  same path at the same time.
- **The handler is deferred to the end of the play, so the ruleset the host
  enforces during a run is the previous one.** Ansible flushes handlers at
  the end of the play, not of this role. On a run that changes the ruleset,
  every role after this one — emergency-access, fail2ban, logging, swap —
  executes against the old firewall. That is normally harmless and is
  occasionally the only reason the run survives: the connection Ansible is
  using was admitted under the old rules and, being established, continues
  to be admitted under the new ones by `FW-6` regardless of what changed.
  The corollary is that a change which would refuse *new* SSH connections —
  a wrong interface name, a port the `SSH` spec no longer uses — does not
  announce itself on the connection that made it. It shows on the next one.
- **A host reached through the knock branch has no `FW-6`-independent
  guarantee that a long-running Ansible run stays connected**, because the
  knock-passed set entry expires on a timer while the run is in progress.
  That belongs to the port-knocking spec; it is named here only because the
  rule that saves it — the established-connection accept — is `FW-6`, and a
  future change to `FW-6`'s position in the chain would break port knocking
  in a way that looks unrelated to it.
- **Nothing verifies that the deployed file is the ruleset the kernel is
  enforcing.** `verify_bootstrap.yml` reads a live `nft list ruleset` for
  four of the rules, which is real evidence, but the checks are `search()`
  matches for individual lines rather than a comparison against the deployed
  file, and no check is made that the two correspond. A host whose service
  is running an older ruleset — loaded before a deployment whose handler
  never ran — passes every one of them.
- **Neither ICMP rule has live coverage of any kind**, and `FW-9` has a
  spelling trap for whoever adds it: `nft` normalises
  `ip6 nexthdr icmpv6` to `ip6 nexthdr ipv6-icmp` when listing a loaded
  ruleset, so a verification check written against the template's spelling
  would fail on a correctly configured host.
- **The knock branch's `Requirement 8.x` citations do not exist, so there
  was nothing to leave for the port-knocking spec.** Every superseded
  citation in this role sat on a rule or a task this spec now covers; the
  knock sets, the staged accepts, the knock-port drop and the four knock
  defaults carried none. The port-knocking spec added its citations from
  scratch rather than rewriting existing ones, and those lines now carry
  `KNOCK-N` comments where this spec had left placeholder prose.

## Interactions

**What this spec assumes of others:**

- `SSH-13` — `ssh_port` is the port sshd actually listens on. `FW-14`
  derives `firewall_ssh_port` from it, so the rule and the daemon agree by
  construction; if that derivation were broken the firewall would open a
  port nothing serves and refuse the one that does.
- `SSH-18` — on a Tailscale-enabled host sshd is bound to the tailnet
  addresses. `FW-10` does not depend on this for its own correctness, and
  deliberately so: the two are independent controls on the same path, and
  this spec's rule is complete without the binding. What this spec assumes
  is only that the binding does not *contradict* the rule — that sshd is
  listening on an address reachable over the tailnet interface, so that the
  packets `FW-10` admits find a socket.
- `SSH-1`, `SSH-2`, `SSH-3` — what makes `FW-13` defensible. That branch
  accepts SSH from the whole internet; the connections it admits are then
  refused unless they present a key, are not root, and offer no password.
  `FW-13` without those is an open door.
- `TS-14` — `tailscale_interface` names the interface the client actually
  brings up. `FW-11` inherits it, and a mismatch means `FW-10`'s rule
  matches nothing and the host has no SSH path at all.
- `TS-1` — `tailscale_enabled` defaults to false, so an unconfigured
  deployment reaches the knock branch or `FW-13`'s open branch rather than a
  tailnet rule with no tailnet behind it.
- `TS-15`, `TS-16`, `TS-21`, `TS-22` — the interface exists, the client is
  `Running`, traffic crosses the tailnet, and all of it has been confirmed
  before this role renders its template. This is the whole of the safety
  argument for `FW-10`, and `INV-8` is the invariant it satisfies. Nothing
  in this role can tell a working tailnet from a broken one.
- `PRJ` — `site.yml` orders the `tailscale` role ahead of this one and
  supplies the inventory that sets `ssh_port`, `tailscale_enabled` and the
  knock flags. The role has no `when:` of its own at the role level: it runs
  on every host, and the branching happens inside the template.
- `INV-6` — a tailnet that works during the bootstrap and breaks afterwards
  leaves `FW-10` matching an interface that no longer carries traffic.
  Nothing in this role can detect or repair that. What makes the narrowing
  recoverable rather than terminal is the emergency-access spec's script,
  which edits this spec's own `/etc/nftables.conf` from a root console and
  reloads the service, needing no network of its own; see
  `## Interactions`. This spec's contribution to `INV-6` is that the
  narrowing lives in a plain file rather than in kernel state — there is
  something for that script to edit.

**What others may assume of this spec:**

- `SSH` — that the firewall's posture, not sshd's binding, is what stands
  between a Tailscale-disabled host's sshd and the internet. `FW-3`'s drop
  policy is the default-deny half of that; the other half is whichever SSH
  branch the host's two flags select, and which one that is matters. With
  port knocking at its default of enabled — the configuration such a host
  gets unless knocking is explicitly turned off — the open port is
  knock-gated and `FW-13`'s rule is not rendered at all; `FW-13` is reached
  only when both flags are false. Whichever branch is taken, `FW-14`
  guarantees the port it opens is the port `SSH-13` configured. On a
  Tailscale-enabled host `SSH` may
  further assume `FW-10` admits SSH only on the tailnet interface — as a
  second, independent control alongside its own binding, not as a substitute
  for it.
- The port-knocking spec — this spec owns the input chain the knock rules
  are inserted into, the two flags that select between the three branches,
  and `FW-6`, which is what keeps an SSH session alive after its knock-passed
  set entry has expired. It also owns `FW-3`'s drop policy, which is what
  makes the knock ports silent rather than refused. That spec is now
  written: the knock sets and rules in
  `roles/firewall/templates/nftables.conf.j2` and the four
  `firewall_port_knocking_*` defaults carry its `KNOCK-N` citations, and it
  cites `FW-3`, `FW-6` and `FW-7` in return. `FW-7` belongs in that list —
  the loopback accept is evaluated before the knock rules, so `KNOCK-8`'s
  drop of the knock ports does not apply to loopback traffic, which is why
  that requirement is scoped to the rules that follow it.
- The fail2ban spec — it writes bans into the same kernel ruleset this spec
  flushes, in a table of its own. It may assume this spec leaves its table
  alone while the firewall is not being reloaded; it may **not** assume the
  table survives a reload, a re-run that changes the ruleset, or a reboot,
  because `FW-15`'s flush removes every table in the kernel. It may also
  assume `FW-3`'s drop policy handles everything its jails never see. Not
  yet written; same prose-not-IDs caveat — when it is, the interaction to
  record against an ID is the flush.
- The emergency-access spec — its break-glass script repairs **both** halves
  of the narrowing, this spec's included, and may assume it can. It edits
  `/etc/nftables.conf` in place, strips the `iifname` qualifier off
  `FW-10`'s rule — leaving the unqualified accept `FW-13` would have
  rendered, though `FW-13`'s own condition is not what put it there —
  reloads the service, and exits non-zero if that reload fails. So it is
  self-sufficient: a host
  recovered with that script alone is reachable, and no separate firewall
  step is needed. What it may assume of this spec is that
  `/etc/nftables.conf` is a plain root-editable file (`FW-16`), that a
  reload re-reads it whole (`FW-19`), and that neither requires a network —
  together, what makes `INV-6` true for `FW-10`'s narrowing rather than
  merely hoped for.

  The coupling runs the other way too, and it is tighter than it looks. The
  script's edit is a `sed` substitution matching `FW-10`'s rendered rule
  *as literal text* — the `iifname "<interface>" tcp dport <port> accept`
  form, with that word order and that spacing. Any change to how `FW-10`
  renders breaks it silently: `sed` matching nothing is not an error, so the
  script would go on to restart sshd, reload an unchanged ruleset, and print
  its success message on a host still refusing SSH. `FW-10`'s rule text is
  therefore a published interface, not an implementation detail, and this is
  the same hazard `specs/ssh-hardening/design.md` records about the script's
  `ListenAddress` edits. The `--restore` direction has the converse
  dependency, re-adding the qualifier to a line it matches as
  `tcp dport <port> accept`. Not yet written; same prose-not-IDs caveat —
  when it is, `FW-10`, `FW-16` and `FW-19` are the IDs it should cite, and
  `FW-10` is the one whose rule text it must not be allowed to drift from.
- Purpose repositories, and whichever spec eventually owns the extension
  contract — a bootstrapped host has `/etc/nftables.d` (`FW-20`), included
  at the end of the ruleset (`FW-21`). A file placed there is loaded on the
  next reload and on every boot, its rules are appended after everything
  this spec defines, and a bootstrap re-run neither deletes it nor needs to
  know about it. The constraint is `add rule` syntax: the drop-in is
  included inside the same transaction as `FW-15`'s flush and after the
  table exists, so a file that re-declares the table or flushes again breaks
  the whole load. `docs/multi-repo-strategy.md` states the same contract for
  that audience.
- `VRFY` — what a completed bootstrap guarantees is a property of the
  **deployed file** plus one systemd start, and the distinction is what
  `VRFY` exists for. A completed run establishes that the template rendered,
  that it was installed at `/etc/nftables.conf` owned by root with mode
  `0644` (`FW-16`), that the service was enabled (`FW-17`) and started
  (`FW-18`) without systemd reporting failure, and that a reload was
  requested if the file changed (`FW-19`). On that basis every rule the file
  carries says what this spec says it says. What a completed run does *not*
  establish is that the kernel is enforcing that file: the start task
  succeeds on a host whose service was already running an older ruleset, and
  the handler that would have fixed that is deferred to the end of the play.
  The unit's own state does not close that gap either — it is `oneshot` with
  `RemainAfterExit=yes`, so `ActiveState == active` means the last load
  exited zero, not that the rules it loaded are still in the kernel.
  The four live assertions `verify_bootstrap.yml` already makes — `FW-3`,
  `FW-4`, `FW-6`, `FW-7` — are worth more than the rest of the list for
  exactly that reason: they can only answer if a ruleset is loaded. A `VRFY`
  spec that wanted to close the gap would compare the loaded ruleset against
  the deployed file rather than search it for individual lines, and would
  add checks for `FW-8` and `FW-9` — matching `ipv6-icmp`, not `icmpv6`.
- The testing spec — the integration suite is the only place in the project
  where a packet is ever sent at a bootstrapped host's firewall, and so the
  only evidence that `FW-3`'s policy drops rather than merely renders. It
  runs only under Incus. Every other claim in `requirements.md` rests on
  rendered text, a live `nft list ruleset` read by `VRFY`, or the
  measurements recorded in this document.
