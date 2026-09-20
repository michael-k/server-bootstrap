# Emergency Access — Design

## Approach

The role does one thing: it renders a shell script from a template and
writes it to `/root` with mode `0700`. There is no service, no unit, no
timer and no handler. Everything this spec is about happens later, on a
host nobody can reach, when a person types the script's path at a
provider's console.

The script itself is a single bash file with two directions and a shared
preamble. The preamble checks it is running as root (`EMRG-11`) and that
both files it is about to edit exist (`EMRG-13`), then dispatches on the
argument list: nothing at all means reopen SSH, exactly `--restore` means
close it again, anything else is a usage error (`EMRG-14`). Each direction
begins with a compound `grep` over both files that returns early if the
host is already in the state the direction would produce (`EMRG-9`), then
copies both files to timestamped backups (`EMRG-10`), then makes its edits,
then restarts sshd (`EMRG-6`) and reloads nftables (`EMRG-7`), treating a
failure of either as fatal (`EMRG-8`).

The edits are `sed` against two files this spec does not own. On
`/etc/ssh/sshd_config` it deletes every `ListenAddress` line and inserts
the pair it wants after the `Port` line. On `/etc/nftables.conf` it
substitutes one form of the SSH accept rule for the other. Both are keyed
to literal text — the port, the interface name and the two tailnet
addresses are baked into the script at render time from the same variables
the other two templates read (`EMRG-15`), and the firewall rule's exact
rendered wording is a dependency in its own right (`EMRG-16`).

Two things follow from this shape and are worth stating up front, because
most of `## Failure modes` is downstream of them. The script has no parser
for either file, so every one of its edits fails silently when the file it
is editing does not look the way it expected. And the script is not part of
the bootstrap's declarative state: it changes files the playbook renders
from templates, so a later run undoes everything it did.

## Implementation map

| Path | Realises |
|---|---|
| `roles/emergency_access/tasks/main.yml` | EMRG-1, EMRG-2, EMRG-17 |
| `roles/emergency_access/defaults/main.yml` | EMRG-1, EMRG-2, EMRG-15 |
| `roles/emergency_access/handlers/main.yml` | EMRG-17 |
| `roles/emergency_access/templates/emergency-ssh-access.sh.j2` | EMRG-3, EMRG-4, EMRG-5, EMRG-6, EMRG-7, EMRG-8, EMRG-9, EMRG-10, EMRG-11, EMRG-13, EMRG-14, EMRG-15, EMRG-16 |

`EMRG-12` appears nowhere in that table and carries `**Traceability:**
exempt` for the reason it gives: it is a requirement about what the script
does not do, and there is no line that realises an absence.

`roles/emergency_access/handlers/main.yml` defines no handlers. It is in
the map because its emptiness is the evidence for `EMRG-17` — a handler
here would be the obvious way to make the bootstrap invoke the script, and
the file says in a comment that there is deliberately none.

## Key decisions

**Rewriting the configuration files rather than toggling a service.** The
obvious alternative was a second, permanently installed path in: a
recovery sshd on another port, a systemd unit an operator starts, or a
drop-in under `/etc/nftables.d` that is present but inert until something
enables it. Every one of those is a standing object that exists on the host
whether or not anyone ever needs it, and that is exactly what `INV-1`
exists to prevent — a socket that is usually not listening is still a
socket someone can arrange to have listening, and a drop-in that is usually
not loaded is one flag away from being loaded. This design has no standing
object at all. Between bootstrap and break-glass there is a file with no
execute path of its own, and the host's exposure is identical to a host
where this spec did not exist. The cost is that the repair is textual
surgery on two files the tool does not own, and most of this document's
`## Failure modes` is the bill for that choice. It is still the right one:
a recovery tool whose mere presence widens the attack surface is a tool
that has to justify itself on every host, every day, against a failure that
may never happen.

The second-order consequence is the one worth naming. Because the script
edits rendered files rather than setting a variable the playbook would
honour, its repair is not durable — see `## Failure modes`. A design that
wrote, say, `emergency_unrestricted: true` into a host var and re-ran the
playbook would produce a durable change, but it would need the playbook,
which needs a controller, which needs a network: precisely the thing that
is missing when this script is needed. Local, textual and temporary is the
combination that survives the failure this exists for.

**Anchoring the sshd edit to `Port` rather than restoring a saved copy.**
The script could have restored `/etc/ssh/sshd_config` from the backup it
takes, which would make `EMRG-5` a byte-for-byte guarantee. It does not,
and the reason is that a backup is only as good as the state it captured:
an operator who ran unrestrict twice a month apart, or who edited the file
by hand in between, would have the script restore something other than what
the playbook deployed. Deleting all `ListenAddress` lines and inserting the
pair the script was rendered with makes the result a function of the script
and the current file, not of history. The price is that the directives come
back in a different position than they started in, which is why `EMRG-5`
is worded the way it is.

**The script exists only where Tailscale is enabled.** `emergency_access_enabled`
derives from `tailscale_enabled` and the role is gated a second time in
`site.yml` on the same flag. The narrow reason is that the script is
rendered with two tailnet addresses and one interface name: on a host that
never enrolled, those render empty, and `--restore` would write
`ListenAddress` with no argument after it. Measured on OpenSSH 10.4, sshd
refuses that outright — `no argument after keyword "ListenAddress"`, one
bad configuration option, exit 255 — so the restart in `EMRG-6` would fail
and `EMRG-8` would stop the script, leaving the host with a broken
configuration and no running sshd. The broader reason is that the script
would be a recovery tool for a narrowing that did not happen. A host with
no tailnet is reachable either openly (`FW-13`) or through a knock
sequence, and in
neither case does removing an `iifname` qualifier from a rule that does not
exist help anybody. Deploying it anyway would be worse than not deploying
it, because an operator who finds a break-glass script on a host reasonably
concludes it is the break-glass path for that host.

That decision is why `KNOCK` has no recovery tool and says so. It is a real
asymmetry rather than an oversight, and it is recorded in both specs so
that neither can quietly acquire the assumption that the other covers it.

**No `sshd -t` before the restart.** `SSH-19` requires the bootstrap to
parse a candidate sshd configuration before installing it, precisely so a
rendering mistake becomes a task failure rather than a daemon that does not
come back. This script does the same kind of edit and does not do the same
check: it writes, restarts, and finds out. That is a real gap and it is
listed in `## Failure modes` rather than defended here — the honest account
is that the script predates that requirement and nothing has reconciled
them.

## Failure modes

- **`FW-10`'s rendered rule text is a published interface, and breaking it
  is silent.** The script's firewall edit is a `sed` substitution against
  the literal string `iifname "<interface>" tcp dport <port> accept`, with
  that word order and that spacing. `sed` exits 0 when it matches nothing
  — measured — and the script does not check what it changed. So rewording
  that rule, or changing its spacing, or splitting it in two, turns the
  break-glass path into this: the script takes its backups, edits
  `sshd_config` successfully, changes nothing in `/etc/nftables.conf`,
  restarts sshd, reloads an unchanged ruleset, prints
  `SUCCESS: SSH access unrestricted`, and leaves a host that still drops
  every SSH packet on the public interface. The operator reads the success
  line, closes the console, and discovers the truth when the connection
  times out. `EMRG-16` exists to make that dependency a stated requirement
  rather than a coincidence, and `specs/firewall/design.md` records the
  same coupling from the other side. `specs/ssh-hardening/design.md`
  records the equivalent hazard for the `sshd_config` half, where the
  anchors are `^Port <port>` and the two `ListenAddress` literals.

- **The repair is undone by the next bootstrap run — both halves, in the
  same play.** `/etc/nftables.conf` is deployed by an unconditional
  `template` task (`FW-16`) that notifies the reload handler (`FW-19`), and
  `/etc/ssh/sshd_config` is deployed the same way by the SSH role. Neither
  task is conditional on anything the script changes, so a bootstrap run
  against a host in the unrestricted state re-renders both files from their
  templates, puts the tailnet-only narrowing back, restarts sshd and
  reloads nftables — as two ordinary `changed` results among fifty. An
  operator who broke glass to recover a host, then re-ran the playbook for
  an unrelated reason while the tailnet was still broken, is locked out
  again by their own run, and nothing in either role warns them. No test
  covers it: no suite runs the script and then bootstraps the same host.
  The sshd half of this is recorded in `specs/ssh-hardening/design.md`; the
  nftables half is recorded here. It is also, viewed from the other
  direction, `INV-9` working correctly — which is why `requirements.md`
  lists `INV-9` under **Relies on** rather than treating this purely as a
  defect.

- **The unrestrict guard can be satisfied by a comment when the SSH port is
  443.** The third clause of `unrestrict_ssh`'s idempotency check is
  `grep -q "tcp dport ${SSH_PORT} accept" /etc/nftables.conf`. The
  firewall's drop-in documentation block near the end of that file contains
  the line `#   add rule inet filter input tcp dport 443 accept` as an
  example, and that comment satisfies the grep when `ssh_port` is 443 —
  measured. Today the guard as a whole cannot be fooled by it, because the
  fourth clause requires the interface-qualified rule to be *absent*, and
  on a narrowed host it is present. So the quirk is unreachable, not
  harmless: it becomes live the moment anyone relaxes or reorders that last
  clause, and the symptom would be the script reporting
  `SSH is already unrestricted` on a host whose firewall still narrows SSH.
  The general shape of the problem is that the guard greps a configuration
  file for rule fragments without regard to whether the line it found is a
  rule or a comment; only the `--restore` substitution, which anchors at
  `^\s*`, is immune.

- **The script restarts sshd without validating what it wrote.** Every
  path through `unrestrict_ssh` and `restore_ssh` edits `sshd_config` and
  then runs `systemctl restart sshd`. If the edit produced a configuration
  sshd will not accept, the restart fails, `EMRG-8` makes the script exit 1
  — and the host is left with a broken `sshd_config`, a daemon that is not
  running, and the firewall half of the change not yet applied. Recovery is
  then the backup the script took, by hand, at the console. `SSH-19` avoids
  exactly this for the bootstrap by parsing the candidate first; nothing
  here does.

  **The likeliest route to it is running `--restore` before the tailnet is
  back.** That is not an exotic misconfiguration — it is following this
  spec's own documented sequence slightly early. The tailnet addresses
  belong to an interface the client creates — which is why `TS-15` waits
  for `/sys/class/net/<interface>` to appear before anything trusts it — so
  while `tailscaled` is down there is nothing for the two `ListenAddress`
  lines `EMRG-4` writes to bind to. Measured: sshd given two unbindable
  addresses reports
  `Bind to port <port> on <address> failed: Cannot assign requested
  address.` for each, then `Cannot bind any address.`, and exits 255;
  given one bindable and one not, it starts and serves the one, as
  `specs/ssh-hardening/design.md` records. This pair is gone together, so
  it is the fatal case: the restart fails and `EMRG-8` exits 1. The host is
  then left with both file edits already applied — `sshd_config` no longer
  naming the public addresses — an sshd that is not running, and an
  nftables reload that never ran, so the kernel still holds the
  unrestricted rules. That is the worst outcome this spec can produce, and
  it is reached by an operator doing the right thing in the wrong order.
  The one mercy is that the firewall is still open, so repairing
  `sshd_config` by hand at the console and restarting is enough to get back
  in. The next bullet is a second, rarer route to the same place.

- **The tailnet addresses are frozen at bootstrap time, so `--restore` can
  write addresses the host no longer has.** `TS-17` and `TS-18` publish the
  addresses as facts during the run, and this role bakes their values into
  the script as shell literals. A host that is later re-registered with the
  control server, or moved to a different tailnet, gets new addresses; the
  script on disk still holds the old ones. Running `--restore` then writes
  two `ListenAddress` lines for addresses the host does not have. As
  `specs/ssh-hardening/design.md` records, sshd treats a bind failure as
  fatal only when *every* configured address fails — so with both of the
  pair stale the outcome is a restart failure, the previous bullet's
  half-applied state, and an operator at a console with no SSH at all. The
  same freezing applies to the interface name and the port. Nothing detects
  staleness, and a bootstrap re-run is what fixes it, which the operator
  may not be able to do.

- **A failed nftables reload leaves the two halves disagreeing.** Both
  directions restart sshd first and reload nftables second. If the restart
  succeeds and the reload fails, `EMRG-8` stops the script, and the host is
  left with sshd bound to the new addresses and the kernel still enforcing
  the old rules. In the unrestrict direction that is merely a failed
  recovery — sshd is public, the firewall still drops. In the `--restore`
  direction it is worse: sshd is back on the tailnet addresses only, the
  firewall still admits SSH from everywhere, and the operator's session may
  have been on the public address. Nothing re-orders these or rolls back,
  and no test inspects the state after a partial failure.

- **The reload discards fail2ban's table.** `/etc/nftables.conf` begins
  with `flush ruleset` (`FW-15`), which removes every table in the kernel
  and not just the one the file defines. So each direction of this script
  drops whatever bans fail2ban had installed, at the exact moment the
  unrestrict direction makes the SSH port publicly reachable. The bans come
  back as fail2ban re-detects the offenders, not immediately. This is a
  property of the firewall's own reload and is recorded in
  `specs/firewall/design.md`; it is repeated here because this script is
  the one thing that triggers a reload at a moment when the bans matter
  most.

- **Backups taken within the same second overwrite each other.**
  `backup_configs` names its copies with a `%Y%m%d_%H%M%S` suffix, so two
  changing runs inside one second produce one pair of backups rather than
  two — observed while measuring the round trip, where an unrestrict and a
  `--restore` run back to back left a single timestamp. A human at a
  console will not hit this; a script driving the tool, as the integration
  suite does, can. What is lost is the older copy: an unrestrict followed
  within the second by a `--restore` leaves one backup, and it holds the
  *unrestricted* state rather than the state the host was in before the
  break-glass path was used. The journal still says the path was taken and
  in which direction, so what the collision destroys is not the evidence
  but the *recovery material*: the only copy of the host's pre-break-glass
  configuration, which is precisely what `EMRG-10` exists to preserve.

- **The round trip does not restore `sshd_config` byte for byte.**
  Measured: rendering `sshd_config.j2` for a Tailscale-enabled host,
  running the script with no arguments and then with `--restore`, leaves
  `sshd -T` producing output identical to the original's, and leaves
  `/etc/nftables.conf` byte-identical — but the two `ListenAddress`
  directives end up immediately after `Port`, above `AddressFamily any`,
  rather than below it where the template puts them, and the two-line
  comment that introduced them is left behind with nothing following it.
  The effective configuration is unaffected: `AddressFamily any` is the
  default, and `sshd -T` was measured to produce identical output with the
  directives in either order. What is affected is the next reader of that
  file, who finds a comment saying "bound to the Tailscale interface
  addresses only" immediately above a blank space. `EMRG-5` states this
  outcome rather than promising the stronger one.

- **The break-glass path records the change but not the actor.** The
  script itself writes only to its own standard output: no `logger` call,
  no journal entry of its own, no mail, no alert. The record that exists
  comes from the daemon it restarts.
  `roles/ssh_hardening/templates/sshd_config.j2` sets neither `LogLevel`
  nor `SyslogFacility`, so sshd keeps OpenSSH's defaults for both — `INFO`
  on the AUTH facility. Measured: at startup it emits one
  `Server listening on <address> port <port>.` line per bound address, and
  the two directions are distinguishable in it — `0.0.0.0` and `::` after
  an unrestrict, the two tailnet addresses after a `--restore`. On a
  systemd host those lines land in the unit's journal (`ssh.service`, of
  which `sshd.service` is an alias — checked). After `EMRG-6`'s restart the
  journal therefore carries a timestamped, direction-distinguishing record,
  and an auditor reading this spec should be sent there first.

  What is genuinely missing is attribution. Those lines name addresses and
  a port; they name no user, no session, and not the script. So the journal
  answers "which direction, and when" and cannot answer "by whom". Nothing
  here closes that. A `logger` call naming the invoking user would, and
  this spec deliberately does not require one — that is a gap recorded, not
  a gap argued away. `ALW-1`'s compensating-control column claims only the
  backups, because those are the artefact *this* spec produces: the journal
  line comes from `SSH`'s configuration, so a register row leaning on it
  would be leaning on another spec's defaults without saying so.

- **The restore guard's IPv6 clause degenerates when the address is
  empty.** `restore_ssh` checks
  `grep -q "^ListenAddress ${TAILSCALE_IPV6}"`, which with an empty
  `TAILSCALE_IPV6` becomes `grep -q "^ListenAddress "` and matches any
  `ListenAddress` line at all. Every unit-level test of the script renders
  it without `emergency_access_tailscale_ipv6`, so this is the path they
  all take — which is why the IPv6 half of `EMRG-4` is not really covered
  by them. On a real deployment the variable is non-empty, because `TS-20`
  fails the run otherwise; the degeneracy is reachable only on a host where
  the fact was somehow empty at render time, and there the guard is the
  least of the problems — the insertion that follows writes a bare
  `ListenAddress`, which sshd refuses to parse at all.

## Interactions

**What this spec assumes of others:**

- `SSH-13` — the deployed `sshd_config` contains a line beginning `Port `
  followed by the same port this script was rendered with. Both of the
  script's insertions use that line as their `sed` anchor, so a
  configuration without it, or with a different port, leaves the script
  deleting the `ListenAddress` lines and inserting nothing. sshd with no
  `ListenAddress` at all listens on every address, so the asymmetry is
  worth naming: an anchor failure makes the unrestrict direction reach its
  goal by accident, and makes the restore direction fail *open* — the
  script reports that SSH is restricted to the tailnet again on a host that
  is now bound to every address it has. Both directions would then be
  saying "success" and one of them would be wrong in the dangerous
  direction.
- `SSH-18` — the deployed `sshd_config` contains exactly two
  `ListenAddress` lines and no other. The unrestrict direction deletes all
  of them and writes `0.0.0.0` and `::`, which are `SSH-18`'s own
  else-branch values, so the host it produces is bound the way a
  Tailscale-disabled host would have been. The restore direction writes the
  tailnet pair, which is `SSH-18`'s enabled-branch result. This spec
  therefore assumes `SSH-18`'s two branches are the only two states sshd's
  binding is ever in, and it assumes nothing about `ssh_listen_address_ipv4`
  and `ssh_listen_address_ipv6`: it hardcodes `0.0.0.0` and `::` rather
  than reading them, so a deployment that changed those defaults would find
  the script's idempotency guard permanently unsatisfied.
- `SSH-17` and `SSH-19` — this spec deliberately does neither's job through
  Ansible. `EMRG-6` restarts sshd itself because there is no controller
  present to flush a handler, and it does *not* do `SSH-19`'s validation
  first; see `## Failure modes`.
- `FW-10` — the deployed ruleset contains the SSH accept rule in its
  interface-qualified form, and that form's literal text is what the
  unrestrict direction matches. This is the tightest coupling in the spec
  tree and `EMRG-16` states it as a requirement. `specs/firewall/design.md`
  states the same thing from the firewall's side and names `FW-10`,
  `FW-16` and `FW-19` as the IDs this spec should cite; it does.
- `FW-13` — this spec assumes nothing of it, and the distinction matters.
  The unrestrict direction produces the same rule text `FW-13` would have
  rendered, but `FW-13`'s stated condition is that
  `firewall_tailscale_enabled` and `firewall_port_knocking_enabled` are
  both false, and this script only ever runs on a host where the first of
  those is true. The rule is there because a `sed` put it there, not
  because `FW-13`'s branch was taken, and a bootstrap re-run will not agree
  that it belongs.
- `FW-16` — `/etc/nftables.conf` is a plain, root-owned, root-editable file
  at that exact path, which is what makes the firewall half of the repair
  possible from a console at all.
- `FW-19` — a reload re-reads the whole file as one transaction, so the
  edited file either takes effect completely or not at all, and a reload
  that fails leaves the previously loaded rules in place. `EMRG-7` depends
  on the unit being reloadable at all; `EMRG-8` depends on a failed reload
  being reported as a non-zero exit.
- `FW-15` — a reload flushes every table in the kernel, including
  fail2ban's. See `## Failure modes`.
- `FW-3` — the input chain's policy is drop, which is why removing the
  `iifname` qualifier is sufficient to reopen SSH and why leaving it in
  place is sufficient to keep SSH closed. If the policy were accept, this
  script's firewall half would be pointless in both directions.
- `TS-1` — `tailscale_enabled` defaults to false, which is what makes
  `EMRG-2` deploy nothing on an ordinary host.
- `TS-14` — `tailscale_interface` names the interface the client actually
  brings up, and it is the string the script substitutes into `FW-10`'s
  rule form. A rename that reached the firewall's template but not this
  role's default, or the reverse, would produce a script that matches
  nothing.
- `TS-17` and `TS-18` — the two published facts are baked into the script
  at render time. This spec assumes they are non-empty when the script is
  rendered, which `TS-19` and `TS-20` enforce by failing the run otherwise;
  it does *not* assume they are still correct when the script is run, which
  is the staleness failure mode above.
- `PRJ` — `site.yml` gates this role on `tailscale_enabled` a second time
  and orders it after `tailscale`, `ssh_hardening` and `firewall`, so the
  script is rendered from facts that exist and deployed to a host whose
  narrowing has already happened. `site.yml` also prints the script's path
  and both invocations in its closing message, which is the only place an
  operator is told the tool exists during a run.

**What others may assume of this spec:**

- `SSH` and `FW` — that the narrowing each of them performs is recoverable
  from a console, and specifically that `INV-6` holds for `SSH-18`'s
  tailnet binding and `FW-10`'s interface qualifier because `EMRG-3` exists
  and `EMRG-12` makes it usable without a network. Neither may assume the
  recovery survives its own next run; the reversion is this spec's
  `## Failure modes` entry and `specs/ssh-hardening/design.md`'s.
- `KNOCK` — that this spec provides it **nothing**. The script is deployed
  only where Tailscale is enabled, which is exactly where the knock branch
  is not rendered, and the rule it edits is one a knock-gated host does not
  have. `INV-6` holds for a knock lockout because `/etc/nftables.conf` is
  editable at the console, not because this tool exists, and an operator
  who goes looking for a break-glass script on a knocking host will not
  find one. `specs/port-knocking/design.md` says the same and asks that the
  gap be recorded against an ID here; this bullet is that record.
- `TS` — that the flag it owns is the whole of what decides whether this
  spec's artefact exists, and that this spec reads its two facts and
  changes neither. Nothing here touches the client, the daemon or the
  tailnet; the unrestrict direction is explicitly *additive* to tailnet
  reachability rather than a replacement for it, which the tailnet
  integration suite asserts by checking that peer access over both families
  still works after the script has run.
- `VRFY` — that on a Tailscale-enabled host the script exists at
  `/root/emergency-ssh-access.sh` and is executable, which is what its
  `Verify EMRG-1: emergency script exists` checks. What a completed
  bootstrap establishes is `EMRG-1`,
  `EMRG-2` and `EMRG-17` — a file was rendered, to the right path, with the
  right mode, and nothing ran it. Every other requirement in this spec is a
  claim about what happens when a human runs the script *later*, and no
  bootstrap run establishes any of them.
- The testing spec — that the tailnet integration suite is the only place
  in this project where the script is executed against a real narrowed host
  and the result is measured by opening a connection rather than by reading
  a file. Two of its tests do this, in definition order against a
  session-scoped three-VM fixture, and the second depends on the state the
  first left. They run only under Incus. Everything else that claims to
  test this spec is reading the rendered template for substrings, or
  running it against two hand-written fixture files that resemble the real
  ones.
