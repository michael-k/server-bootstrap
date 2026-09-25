# Emergency Access — Requirements

**Prefix:** `EMRG`

## Purpose

This spec covers the break-glass tool: a shell script left on every host
this bootstrap has narrowed to a tailnet, which an operator with a root
console session can run to put SSH back on the public interface, and run
again with `--restore` to take it away. It exists because the narrowing two
other specs perform is not self-healing. `SSH` removes sshd from every
publicly reachable address and `FW` stops the packets at the interface, and
both of them do that on the strength of a tailnet that was working at the
moment the playbook ran. A tailnet that breaks the week after leaves a host
with no route in at all — the daemon is absent from the public address, the
firewall drops the port, and the operator's only remaining door is the
provider's console.

That door is enough, because everything the narrowing consists of is a plain
text file a root shell can edit. The script is not what makes recovery
*possible*; it is what makes recovery a single command instead of an
operator reconstructing two files from memory, at a console, under pressure,
with no editor they like and no way to test the result. It also
deliberately makes a host *less* safe, which is why it claims an allowance
(`ALW-1`) rather than quietly doing it.

## Scope

### In scope

- Deploying the script, its path, its ownership and its mode, and the fact
  that deployment happens only on a host that enrolled in a tailnet.
- The `emergency_access_enabled` flag and its derivation from
  `tailscale_enabled`.
- The two directions the script runs in: reopening SSH on every interface
  when invoked with no arguments, and restoring the tailnet-only
  restriction when invoked with `--restore`.
- What a round trip leaves behind, and in what sense it is the state the
  host started in.
- Restarting sshd and reloading nftables after each change, and what the
  script does when either fails.
- Idempotency in both directions, and the backups taken before any change.
- The preconditions the script enforces before it acts: root, and both
  configuration files present.
- Argument handling, including rejection of anything that is neither an
  empty argument list nor exactly `--restore`.
- The values the script is rendered with, and the fact that they are the
  same values the sshd configuration and the firewall ruleset are rendered
  from.
- The dependence of the script's firewall edits on the *rendered text* of
  the ruleset's SSH accept rule.
- The fact that a bootstrap run deploys the script and never executes it.

### Out of scope

- The narrowing itself. Binding sshd to the tailnet addresses is `SSH`'s,
  the interface-qualified firewall rule is `FW`'s, and the addresses both
  of them narrow to are `TS`'s. This spec edits what those three deploy; it
  does not decide what they deploy.
- **Surviving a later bootstrap run.** The script's repair is an edit to
  two files the playbook re-renders from templates, so the next run puts
  the narrowing back — both halves, in the same play. That is `INV-9`
  working as designed and this spec does not try to defeat it, but it means
  the script is a recovery tool and not a configuration change. Neither
  role warns about it; see `design.md`'s `## Failure modes`.
- Any recovery path for a host narrowed by port knocking rather than by a
  tailnet. The script is deployed only where Tailscale is enabled, which is
  exactly where the knock branch is not rendered, and its firewall edit
  targets a rule a knock-gated host does not have. `KNOCK`'s own spec says
  the same; the recovery there is editing `/etc/nftables.conf` by hand.
- Getting the operator to the console. That is the hosting provider's
  facility and nothing in this repository touches it.
- Notifying anyone that the break-glass path was used. The script writes to
  its own standard output and takes backups; it sends no mail, writes no
  syslog record of its own and raises no alert. A record does exist — sshd
  logs the addresses it binds after `EMRG-6`'s restart — but nobody is told
  about it, and closing that gap belongs to whatever spec owns alerting.

## Security invariants

**Upholds:** INV-1, INV-6, INV-10
**Relies on:** INV-2, INV-3, INV-9
**Allowances claimed:** ALW-1

This spec is the mechanism `INV-6` names. The invariant requires every
access-narrowing mechanism to be recoverable using console access alone,
and this bootstrap's narrowing mechanisms include sshd's binding to the
tailnet addresses (`SSH-18`), the firewall's tailnet-interface qualifier on the SSH
accept rule (`FW-10`), and knock gating (`KNOCK-1`). `EMRG-3` is the
recovery for the first two, which are the pair a Tailscale-enabled host
carries. `EMRG-12` is the clause that makes it count for `INV-6` rather
than merely being convenient: the repair is local file edits and local
service control, so it completes from a console session with no network of
any kind. Note what this spec does *not* claim. `INV-6` holds for knock
gating as well, and it holds there because `/etc/nftables.conf` is a plain
editable file, not because this tool exists — the tool is never even
deployed on a knock-gated host. So this spec covers two of the three
narrowing mechanisms, and it is not the reason the invariant is true of the
third.

**`ALW-1` is claimed by `EMRG-3`, and only by `EMRG-3`.** That requirement
puts sshd back on `0.0.0.0` and `::` and strips the interface qualifier off
the firewall's SSH rule, which is exposure on a publicly reachable address
— exactly what `INV-1` forbids without an allowance. `ALW-1` is that
allowance's row in the public exposure register, and claiming it is how
this spec upholds `INV-1`. `EMRG-1`, which
deploys the script, does not weaken anything on its own, and the register
row names the requirement that performs the weakening rather than the one
that makes the tool available.

`INV-10` is upheld because `EMRG-3` gives a tailnet peer nothing it did not
already have. The unqualified rule it writes admits SSH on the tailnet
interface as well, but `FW-10`'s rule already admitted SSH there, under
`ALW-6`, so on the tailnet side the edit widens nothing and claims no
tailnet row.

What makes that exposure defensible is the set of compensating controls
the register row names, and every one of them is a requirement here rather
than a hope. `EMRG-11` requires root, so an attacker who could run it
already has everything it could give them. `EMRG-17` requires the bootstrap
never to run it, so the weakening is always a human decision and never
something a playbook run does. `EMRG-12` keeps the script from adding any
network-reachable interface of its own, so there is no path by which the
weakening could be triggered remotely. `EMRG-4` is the way back, and
`EMRG-5` states that the way back arrives where it started.
`EMRG-10` leaves a timestamped copy of both files as they were. That is
not the only record: `EMRG-6`'s restart makes sshd log the addresses it
bound at default `LogLevel INFO` to the AUTH facility — measured, the line
is `Server listening on <address> port <port>.` — so the journal carries a
timestamped statement of *which direction was taken and when*. What neither
record gives is *who* ran the script: the script writes nothing to syslog
itself, and the lines sshd logs name addresses and a port, never a user or
a session. So the break-glass path is attributable in outcome and in time
but not in actor, and this spec does not pretend to more.

`INV-2` and `INV-3` are what this spec relies on for the exposure to be
survivable rather than merely reversible. The host the script reopens is
running an sshd that accepts no password, offers no keyboard-interactive
path and refuses root outright, so what `EMRG-3` exposes on the public
interface is a daemon that will complete an authentication only against a
key it already holds — not a password prompt, and not a root login by any
method. Without those two, `EMRG-3` would be opening a door rather than
moving one.

`INV-9` is the reliance that is easiest to mistake for a defect. The
script's repair does not survive the next bootstrap run — the playbook
re-renders both files from their templates and puts the narrowing back. As
a property of a configuration tool that would be a bug; as a compensating
control for this one it is the right behaviour, because it means a
forgotten break-glass session does not leave a host permanently public. It
also means an operator who reopens SSH and then re-runs the playbook for an
unrelated reason locks themselves out again. That is a real hazard and it
is recorded in `design.md`'s `## Failure modes` rather than smoothed over
here.

## Requirements

### EMRG-1 — Break-glass script deployed to a root-only path

THE Bootstrap SHALL deploy the break-glass script to the path named by
`emergency_access_script_path` (default `/root/emergency-ssh-access.sh`),
owned by root, group root, mode `0700`.

**Why:** the script rewrites the two files that decide who can reach this
host, so the ability to run it is the ability to expose the host. Mode
`0700` under `/root` means the only accounts that can read it, let alone
execute it, are ones that could make the same edits with an editor —
`EMRG-11`'s root check is then a guard against mistake rather than the only
thing standing between an unprivileged account and a public SSH port.
Naming the path in a variable rather than writing it into the task is what
lets `docs/` and the playbook's closing message state one path that cannot
drift from the one actually used.
**Verified:** the role's single task deploys
`emergency-ssh-access.sh.j2` to `emergency_access_script_path` with
`owner: root`, `group: root` and `mode: "0700"`, and the defaults file sets
that variable to `/root/emergency-ssh-access.sh`.
`test_property_22_emergency_script_deployment` asserts the template module,
the `src:`, a `dest:` that is either the literal path or the variable
reference, one of three spellings of mode `0700`, `owner: root` and
`group: root` — all as substrings of the tasks file, so they are asserted
to be present somewhere in it rather than to sit on the same task. Since
the file contains exactly one task that is not a coincidence today, but
nothing enforces it. The verification play's
`Verify EMRG-1: emergency script exists`, which runs only on a
Tailscale-enabled host, `stat`s the deployed path and asserts it exists and
is executable — the only check anywhere of real system state on
the positive side, and it confirms neither the mode nor the owner this
requirement names. Nothing reads the file's actual `0700` or its
`root:root` ownership from any host.

### EMRG-2 — Deployed only on a host that enrolled in a tailnet

THE Bootstrap SHALL deploy the break-glass script only where
`emergency_access_enabled` is true, and `emergency_access_enabled` SHALL
default to `tailscale_enabled`, which is itself false by default.

**Why:** the script's whole purpose is to undo a narrowing, and on a host
that never narrowed there is nothing to undo — what it would leave behind
instead is a root-owned script rendered with two empty addresses, whose
`--restore` direction writes `ListenAddress` lines with no argument — a
configuration sshd refuses to parse at all, measured — and whose firewall
edit matches nothing. That is worse than useless: it is a recovery tool
that breaks the host it is run on. Deriving the flag from
`tailscale_enabled` rather than restating the condition means the script
exists exactly on the hosts whose access `TS` and its two consumers
narrowed, with no third place for the two conditions to disagree.
**Verified:** the defaults file defines
`emergency_access_enabled: "{{ tailscale_enabled | default(false) }}"`, the
deployment task carries `when: emergency_access_enabled | bool`, and
`site.yml` additionally gates the whole role on
`tailscale_enabled | default(false) | bool`, so the condition is enforced
twice by two different expressions. `test_property_22_emergency_script_deployment`
and `test_property_11_tailscale_conditional_execution` both assert the
`when:` string in the tasks file and both assert that the defaults file
contains `emergency_access_enabled:` and mentions `tailscale_enabled` —
the second assertion is satisfied by the variable's own definition line, so
it cannot distinguish a derivation from a coincidence of naming. Both sides
of the condition are checked on a live host, and only under Incus:
`test_emergency_script_not_deployed_when_tailscale_disabled` asserts
`/root/emergency-ssh-access.sh` is absent from a host bootstrapped with the
flag off, and the tailnet integration fixture — the only place in this
project a run is made with the flag on — goes on to execute the script at
that path on its target, which would fail if it were not there.

### EMRG-3 — SSH reopened on every interface when the script is invoked with no arguments

THE Bootstrap SHALL, when the break-glass script is invoked with no
arguments, make SSH reachable on every interface of the host, by binding
sshd to `0.0.0.0` and `::` and by removing the tailnet-interface qualifier
from the SSH accept rule in the deployed nftables ruleset.

**Why:** this is the requirement the spec exists for, and it is the one
that opens a public exposure, which `ALW-1` covers. Undoing only one of the two narrowings would leave a
host that is still unreachable and an operator who cannot tell which half
failed, so the requirement names both: sshd has to be listening on the
public address *and* the packets have to arrive. Doing it with no arguments
rather than behind a flag is deliberate — the state an operator is in when
they need this is "locked out, at a provider's web console, typing a path
they read off a wiki," and the default action of the script is the action
they need.
**Verified:** `unrestrict_ssh` deletes every `ListenAddress` line from
`/etc/ssh/sshd_config` and inserts `ListenAddress 0.0.0.0` and
`ListenAddress ::` after the `Port` line, then rewrites
`/etc/nftables.conf` with a `sed` substitution that replaces the
interface-qualified SSH accept rule with the unqualified one; `main`
dispatches to it when `$#` is zero.
`test_property_23_emergency_script_unrestrict_operation` asserts the
function exists, that both address literals appear in the template, that
`sed -i` and `tcp dport` appear, and that the no-argument branch exists —
all as substrings of the whole template rather than of the function.
`test_unrestrict_replaces_tailscale_ip_with_all_interfaces`,
`test_unrestrict_removes_interface_restriction_from_nftables` and
`test_unrestrict_function_defined` assert the same construction against a
rendered script.
`test_emergency_script_edge_cases.py` renders the template, points it at
two fixture files and runs it, then asserts both open addresses are in the
sshd file and that the interface-qualified rule is gone from the ruleset —
but those fixtures are hand-written miniatures, not the files `SSH` and
`FW` deploy. The one test that establishes this requirement as stated is
the tailnet integration suite's `test_emergency_script_unrestricts_ssh`:
it runs the deployed script on a bootstrapped, narrowed host and then
opens an SSH connection to that host's *public* address, asserting it
succeeds where the preceding test asserted it failed — and asserting that
tailnet access over both families survives. That is the only evidence
anywhere that the pair of edits produces a reachable host rather than two
plausible-looking files, and it runs only under Incus. This spec's
`design.md` records a separate measurement against the real rendered
templates.

### EMRG-4 — Tailnet-only restriction restored by `--restore`

THE Bootstrap SHALL, when the break-glass script is invoked with the single
argument `--restore`, bind sshd to the tailnet addresses the script was
rendered with and to no other address, and restore the tailnet-interface
qualifier on the SSH accept rule in the deployed nftables ruleset.

**Why:** an allowance that cannot be given back is not an allowance, it is
a permanent change with an apology attached. `ALW-1`'s compensating control
is this requirement, and the "and to no other address" clause is the part
that carries it: a restore that added the tailnet addresses without
removing `0.0.0.0` would report success on a host that is still publicly
reachable, and the operator would have no reason to look again.
**Verified:** `restore_ssh` deletes every `ListenAddress` line and inserts
`ListenAddress ${TAILSCALE_IPV4}` and `ListenAddress ${TAILSCALE_IPV6}`
after the `Port` line — so the removal of the open addresses is a
consequence of the same deletion that clears the way for the tailnet ones,
not a separate step that could be forgotten — and substitutes the
interface qualifier back onto the ruleset's unqualified SSH accept rule.
`test_property_24_emergency_script_restore_operation` asserts the function,
the `--restore` literal, the `ListenAddress ${TAILSCALE_IPV4}` form, the
`/^ListenAddress /d` deletion and the presence of `iifname`; several of its
assertions are `A or B` disjunctions whose second alternative is a much
weaker substring, so they cannot distinguish the construction from any
other use of the same words. `test_restore_removes_all_listen_address_lines`,
`test_restore_adds_tailscale_listen_address` and
`test_restore_adds_interface_restriction_to_nftables` assert the same
strings against a rendered script. `test_restore_idempotency` in the
edge-case suite runs the restore against fixture files and asserts both
that the tailnet address is present and that `0.0.0.0` is absent; its
fixture supplies no IPv6 address, so every unit-level execution of the
script renders it with `emergency_access_tailscale_ipv6` undefined — which
also makes the restore guard's IPv6 clause degenerate into a match on any
`ListenAddress` line at all, so those runs do not exercise the guard as
written either. `design.md`'s `## Failure modes` records the degeneracy.
The tailnet integration suite's
`test_emergency_script_restore` is what covers this requirement in
substance: it runs `--restore` on a host the previous test had reopened,
asserts an SSH connection to the public address now fails, and asserts
tailnet access over both IPv4 and IPv6 still works. It runs only under
Incus, and it depends on the session-scoped fixture and on definition
order — it is not independently runnable.

### EMRG-5 — A round trip returns the host to the configuration it started with

THE Bootstrap SHALL, after an invocation with no arguments followed by an
invocation with `--restore`, leave the deployed nftables ruleset
byte-identical to its content before the pair and leave sshd resolving to
the same configuration it resolved to before the pair, though not
necessarily leaving `/etc/ssh/sshd_config` byte-identical.

**Why:** the operator's decision to break glass has to be cheap to reverse,
and "cheap" means they do not afterwards have to audit two files against a
template to find out what the tool changed. The exception in the last
clause is not a caveat the implementation earned by being sloppy — it is
the honest statement of what the mechanism can promise. The script edits by
deleting and re-inserting lines at an anchor, not by restoring a saved
copy, so the directives come back with the right values in the right order
but not necessarily in their original position in the file. A requirement
written as "byte-identical" would be false, and a requirement written as
"equivalent" would be too vague to check. This one names the two artefacts
separately because they behave differently, and a future change that made
the sshd half byte-identical would satisfy it too.
**Verified:** measured, not tested. Rendering `sshd_config.j2` and
`nftables.conf.j2` for a Tailscale-enabled host, running the rendered
script with no arguments and then with `--restore`, leaves
`/etc/nftables.conf` byte-identical and leaves `sshd -T` producing output
identical to the original's — but leaves the two `ListenAddress` lines
above `AddressFamily any` instead of below it, with the comment that
introduced them orphaned. `design.md` records the measurement and the diff.
`test_property_25_emergency_script_round_trip_restoration` asserts only
that both functions exist, that both name the same two configuration files,
and that each contains the transformation the other reverses; it never runs
anything. `test_alternating_modes_idempotency` runs both directions
repeatedly against fixture files and asserts the final state is
unrestricted — it checks that the alternation does not diverge, not that a
round trip returns to the start. The tailnet integration suite performs a
real round trip across `test_emergency_script_unrestricts_ssh` and
`test_emergency_script_restore`, and what it asserts at the end is
behavioural: the public address refuses again and the tailnet still works.
It never compares either file against its prior content, so nothing in
this project tests the clause about what the round trip leaves on disk.

### EMRG-6 — sshd restarted after each configuration change

THE Bootstrap SHALL have the break-glass script restart sshd after each
change it makes to sshd's configuration.

**Why:** sshd reads its configuration at startup and never again, so a
rewritten `ListenAddress` is a promise about the next restart and nothing
else. This is the same reasoning `SSH-17` applies during a bootstrap run,
except that here there is no Ansible and no handler to defer to: the script
is the only thing that will ever act on the file it just wrote, and an
operator staring at a console has no way to tell an edited file from an
applied one.
**Verified:** both `unrestrict_ssh` and `restore_ssh` call
`systemctl restart sshd` after their edits and before returning.
`test_sshd_restart_command_present` asserts the command appears in the
rendered script and `test_both_services_restarted_in_unrestrict` asserts it
appears at least twice, which is what makes it cover both directions rather
than one.
`test_property_23_emergency_script_unrestrict_operation` asserts the same
string file-wide;
`test_property_24_emergency_script_restore_operation` is the only assertion
scoped to a function, and it scopes by taking a fixed 3000-character slice
from the start of `restore_ssh`. No test asserts the restart happens
*after* the edits. That the restart takes effect at all is established only
by the tailnet integration suite, where an SSH connection to the public
address succeeds as soon as the script returns — which the daemon that had
been running could not have answered. Note what this requirement does
*not* include: nothing validates the configuration the script just wrote
before restarting, as `SSH-19` requires of the bootstrap's own deployment,
so a bad edit becomes a daemon that does not come back rather than a
refused change. `design.md`'s `## Failure modes` records the gap and how
it is reached.

### EMRG-7 — nftables ruleset reloaded after each change

THE Bootstrap SHALL have the break-glass script reload the nftables service
after each change it makes to the deployed ruleset.

**Why:** the kernel holds the rules the last load installed, not the
contents of `/etc/nftables.conf`, so the file this script edits has no
effect until something re-reads it. `FW-19` makes the same point for a
bootstrap run. The failure this prevents is the most misleading one
available: every file-reading check passes, the script prints success, and
the host goes on dropping the SSH packets it was dropping before. The
reload has a side effect worth stating here rather than discovering later:
`FW-15` makes the deployed ruleset begin with a flush of everything the
kernel holds, so each direction of this script also discards whatever bans
fail2ban had installed — in the unrestrict direction, at the moment the
SSH port becomes publicly reachable.
**Verified:** both functions call `systemctl reload nftables` after their
edits. `test_nftables_reload_command_present` asserts the command is in the
rendered script and `test_both_services_restarted_in_unrestrict` asserts it
appears at least twice.
`test_property_23_emergency_script_unrestrict_operation` and
`test_property_25_emergency_script_round_trip_restoration` assert the same
string file-wide, the latter with a `>= 2` count.
`test_nftables_reload_failure_unrestrict` is the only unit-level test that
causes the command to be run, and it does so against a mock `systemctl`
that fails for anything other than sshd. The reload is exercised for real
in the tailnet integration suite, where a packet reaching the target's
public SSH port after the script returns is only possible if the edited
ruleset was loaded into the kernel — `FW-3`'s policy would otherwise have
dropped it.

### EMRG-8 — A failed restart or reload stops the script with a non-zero status

THE Bootstrap SHALL have the break-glass script report the failure and exit
non-zero, making no further change, if either the sshd restart or the
nftables reload does not succeed.

**Why:** the script's two halves are a matched pair, and the state between
them is a host that is half repaired. Continuing past a failed restart
would mean opening the firewall for a daemon that is not listening, or
announcing success on a host whose sshd did not come back — and the
operator would read the last line rather than scroll up. Exiting non-zero
makes the console session's own exit status the signal, which is the only
signal available at a provider's web console. What this requirement does
not do is undo the half that already succeeded: the restart runs first, so
a failed reload leaves sshd bound to the new addresses and the kernel
still enforcing the old rules. In the `--restore` direction that is the
dangerous combination — sshd back on the tailnet while the firewall still
admits SSH from everywhere — and `design.md`'s `## Failure modes` sets it
out.
**Verified:** each `systemctl` invocation is the condition of an `if`, and
each `else` branch logs an error and calls `exit 1`; `set -euo pipefail` at
the top of the script additionally aborts on an unhandled failure such as a
`cp` that cannot write.
`test_sshd_restart_failure_handled` and `test_nftables_reload_failure_handled`
assert the two error strings appear in the rendered script.
`test_sshd_restart_failure_unrestrict` and
`test_nftables_reload_failure_unrestrict` actually run the script against
mock `systemctl` binaries that fail, and assert both the non-zero status
and the error message. Those two are among the few assertions in this spec
that observe behaviour rather than text. Nothing asserts the "makes no
further change" clause: no test inspects the configuration files after a
failed restart to confirm the reload did not also run.

### EMRG-9 — Both directions are idempotent

THE Bootstrap SHALL have the break-glass script, in either direction,
detect that the host is already in the state that direction would produce,
make no change to either configuration file, take no backup, restart and
reload nothing, and exit zero with a message saying so.

**Why:** the operator running this has already lost their normal way in and
may not remember whether they ran it. A second run that re-applied the
edits would restart sshd underneath the session they just recovered, and a
second run that failed would look like the first one had not worked. Making
the no-op case explicit — rather than relying on the edits happening to be
idempotent — is also what keeps the backup directory from filling with
identical copies, which is `EMRG-10`'s evidence value protected from
`EMRG-9`'s convenience.
**Verified:** each function opens with a compound `grep` guard over both
files and returns zero with a `[WARN]` message before reaching
`backup_configs` if every clause holds.
`test_unrestrict_idempotency`, `test_restore_idempotency` and
`test_alternating_modes_idempotency` run the script repeatedly against
fixture files and assert the second run in each direction exits zero and
prints its "already …" message; `test_no_backup_on_idempotent_run` counts
backup files before and after a no-op run and asserts the count is
unchanged, which is the only assertion covering the "take no backup"
clause. `test_property_26_emergency_script_idempotency` asserts, within a
fixed-size slice of each function, that a `grep -q` appears, that there are
at least two of them, that a `return 0` appears and that the word "already"
appears. No test asserts that nothing is restarted on a no-op run, and no
test exercises a guard that is partly satisfied — see `design.md`'s
`## Failure modes` for a case where one clause is satisfied by a comment.

### EMRG-10 — Both files backed up before any change

THE Bootstrap SHALL have the break-glass script copy `/etc/ssh/sshd_config`
and `/etc/nftables.conf` to timestamped copies beside them before it
modifies either.

**Why:** the script's edits are line deletions and pattern substitutions
against files it did not write, and the failure mode of a pattern that
matches more than it should is silent. A copy taken first is what lets an
operator put the host back by hand from the console they are already
sitting at. It is the *recovery* control, not the audit one: the record
that the path was taken, and in which direction, comes from sshd's own
startup log after `EMRG-6`'s restart. These copies are what that log cannot
give — the exact prior contents of both files.
**Verified:** `backup_configs` copies both files with a
`.backup.%Y%m%d_%H%M%S` suffix and is called by both functions after the
idempotency guard and before the first edit.
`test_backup_function_present` asserts the function name is in the rendered
script; `test_backup_created_on_unrestrict` runs the script and asserts at
least two `*.backup.*` files appear.
`test_property_23_emergency_script_unrestrict_operation` and
`test_property_25_emergency_script_round_trip_restoration` assert only that
the word "backup" and the string `cp ` occur somewhere in the template. No
test asserts the backup's *content* matches the file as it was, and the
suffix is second-resolution, so two runs within the same second overwrite
each other's copies — see `design.md`'s `## Failure modes`.

### EMRG-11 — Root required

THE Bootstrap SHALL have the break-glass script refuse to do anything and
exit non-zero when its effective user is not root.

**Why:** this is one of `ALW-1`'s compensating controls, and it is worth
being precise about what it buys. Mode `0700` under `/root` already means
no unprivileged account can execute the file, so the check is not the
barrier — it is what turns a confusing partial failure into one clear line.
A non-root run without it would get as far as the first `cp`, fail on a
permission error under `set -e`, and leave an operator who had forgotten
`sudo` staring at a message about a file they can read.
**Verified:** `check_root` compares `$EUID` against zero and exits 1 with
an error, and `main` calls it before anything else — before `validate_files`
and before either direction runs.
`test_root_check_present` asserts the strings `check_root` and `EUID`
appear in the rendered script. Nothing runs the script as a non-root user:
every execution test in the edge-case suite replaces `check_root` with a
function that returns zero, precisely so the tests can run unprivileged. So
the check's presence is asserted and its behaviour is not.

### EMRG-12 — The repair needs no network of any kind

THE Bootstrap SHALL confine the break-glass script's repair to edits of
local files and control of local services, so that it runs to completion
from a console session on a host with no working network, and so that it
adds no network-reachable interface of its own.

**Traceability:** exempt — this is a property of what the script does not
contain. There is no line to cite, and no test could observe it by
rendering or running the script; it is stated as a requirement so that
adding a network call is a spec change rather than a patch.

**Why:** this clause is the whole of what makes this spec count towards
`INV-6`. A recovery tool that needed to reach a package mirror, a control
server or an API would be useless in exactly the situation it exists for —
the host cannot be reached, and quite possibly cannot reach anything
either. The second half matters for `INV-1`: a daemon, a listening socket
or a callback that could trigger the weakening remotely would turn a
break-glass tool into a remote unlock, and the allowance's argument that
the change requires an existing root session would stop being true.
**Verified:** by inspection only. The script's whole vocabulary is `grep`,
`sed`, `cp`, `date`, `echo` and `systemctl`, all operating on two local
paths and two local units; it opens no socket, fetches nothing and starts
no service of its own. The tailnet integration suite runs it through
`incus exec` rather than over SSH, which is the closest anything comes to
demonstrating the property, but the target has working networking
throughout so it demonstrates nothing about a host that does not.

### EMRG-13 — Refuses to act on a host missing either configuration file

THE Bootstrap SHALL have the break-glass script exit non-zero, changing
nothing, if `/etc/ssh/sshd_config` or `/etc/nftables.conf` is absent.

**Why:** this guard is not what prevents a false success, and saying so is
the only way to see what it is for. Measured: with `validate_files` removed
and `/etc/nftables.conf` absent, `set -euo pipefail` aborts the run at
`backup_configs`'s second `cp` — rc 1, no `sed` executed, `sshd_config`
untouched, no success message. The dangerous outcome is already
unreachable. What the guard adds is three things the abort does not. It
names the missing file in the script's own vocabulary instead of leaving an
operator at a console to interpret `cp: cannot stat …`. It fails before any
backup is written: without it, that same run leaves behind a stray
`sshd_config.backup.<timestamp>` for a repair that never happened —
observed in the measurement above — which is exactly the artefact `EMRG-10`
teaches an operator to trust. And it runs in `main`, before either
direction is chosen, so it holds for `--restore` identically rather than
depending on which `grep` in which guard happens to short-circuit first.
**Verified:** `validate_files` tests both paths with `[[ ! -f ]]`, logs
which one is missing and exits 1; `main` calls it after `check_root` and
before dispatching.
`test_file_validation_present` asserts the function name appears in the
rendered script. `test_missing_sshd_config`, `test_missing_nftables_config`
and `test_missing_both_configs` delete one or both fixture files, run the
script and assert the exit status is 1 and the right message appears.
`test_missing_both_configs` asserts only the sshd message, which is the
first check, so it confirms the order rather than both messages. Nothing
asserts the "changing nothing" clause directly; it follows from the check
preceding both directions.

### EMRG-14 — Any other argument list refused

THE Bootstrap SHALL have the break-glass script reject any invocation that
is neither an empty argument list nor exactly the single argument
`--restore`, printing its usage and exiting non-zero.

**Why:** the two directions differ by one word and have opposite effects,
and the operator is typing at a console with no shell history. A
mistyped `--restor` that fell through to the default action would reopen
SSH on a host the operator was trying to close, and — because the script is
idempotent and the host was already closed — would do it silently and
report success. Rejecting everything unrecognised, rather than treating an
unknown argument as "no arguments", is what stops a typo from choosing the
dangerous direction.
**Verified:** `main` dispatches on `$# -eq 0` and on `$# -eq 1` with
`$1 == "--restore"`, and its `else` branch logs "Invalid arguments", prints
a two-line usage block and exits 1.
`test_usage_comment_present` asserts `--restore` and `Usage:` appear in the
rendered script. `test_invalid_argument` runs the script with `--invalid`
and `test_multiple_arguments` runs it with `--restore --extra`; both assert
exit status 1 and the "Invalid arguments" message, so both the unknown-word
and the too-many-arguments cases are covered by an execution test.

### EMRG-15 — Port, interface and tailnet addresses inherited rather than restated

THE Bootstrap SHALL render the break-glass script's SSH port, tailnet
interface name and tailnet addresses from `ssh_port`,
`tailscale_interface`, `tailscale_ipv4` and `tailscale_ipv6` — the same
values the deployed sshd configuration and the deployed firewall ruleset
are rendered from.

**Why:** every edit the script makes is keyed to one of these four values
as a literal, and there is no mechanism available to detect a mismatch at
runtime: the anchors are text, the files are text, and `sed` that matches
nothing exits zero. What a mismatch produces is not uniform, which is why
it has to be prevented rather than handled. In the firewall half, a wrong
port or interface means the substitution finds nothing and the script
reports success on an unchanged ruleset. In the sshd half it is worse: the
deletion of every `ListenAddress` line happens first and unconditionally,
so a wrong port means the insertion's `^Port <port>` anchor matches
nothing and the file is left with no `ListenAddress` at all — which sshd
reads as "listen on every address". The unrestrict direction would then
reach its goal by accident and the `--restore` direction would fail
*open*, reporting that SSH is restricted to the tailnet on a host bound to
everything. Agreement therefore has to be established at render time, by
all three templates reading the same variables, and the role's defaults
exist to do that indirection in one place rather than in each `{{ }}`.
**Verified:** the defaults file derives `emergency_access_ssh_port` from
`ssh_port | default(22)`, `emergency_access_tailscale_interface` from
`tailscale_interface | default('tailscale0')`, and
`emergency_access_tailscale_ipv4` and `emergency_access_tailscale_ipv6`
from the two facts `TS` publishes, each with an empty-string fallback; the
template assigns all four to shell variables at the top and uses nothing
else. `test_ssh_port_embedded`, `test_tailscale_interface_embedded`,
`test_tailscale_ipv4_embedded`, `test_custom_port_rendered`,
`test_custom_interface_rendered` and `test_custom_tailscale_ip_rendered`
render the template with chosen values and assert each lands in its shell
assignment, `test_custom_port_rendered` also asserting the default is gone.
`test_property_22_emergency_script_deployment` asserts the three `{{ }}`
expressions appear in the template and that three of the four variables are
defined in the defaults file. Nothing checks the `ipv6` variable in either
suite, and nothing compares any of the four against the value the `ssh` or
`firewall` role was rendered with — the agreement is by construction and is
asserted nowhere. Note also that the four values are frozen into the script
at render time: a host later re-registered on a different tailnet keeps a
script holding the old addresses, and `--restore` would then write
`ListenAddress` lines the host cannot bind. `design.md`'s
`## Failure modes` sets out what that does.

### EMRG-16 — Firewall edits keyed to the ruleset's rendered rule text

THE Bootstrap SHALL key the break-glass script's edits to the deployed
nftables ruleset to the literal rendered text of its SSH accept rule: the
interface-qualified form `iifname "<interface>" tcp dport <port> accept`
to reopen SSH, and the unqualified form `tcp dport <port> accept` to close
it again.

**Why:** this requirement exists to make a coupling visible that is
otherwise invisible, and dangerous. The script has no parser for the
ruleset; it does a `sed` substitution against that exact word order and
spacing. `sed` exits zero when it matches nothing — measured — so a
reworded rule does not produce an error, a warning or a non-zero status.
What it produces is the script restarting sshd, reloading an unchanged
ruleset, and printing `SUCCESS` on a host that still refuses SSH, to an
operator who has just been told their last resort worked. Stating the
dependence as a requirement is what makes the rendered form of that rule a
published interface: changing it is a change to this spec, not an
implementation detail of the firewall's template. The `--restore` direction
has the converse dependence on the unqualified form, and inherits the same
silence.
**Verified:** `unrestrict_ssh` substitutes the interface-qualified form
with the unqualified one and `restore_ssh` substitutes back, anchoring the
second at the start of the line so that only a rule, never a comment, is
rewritten. `test_unrestrict_removes_interface_restriction_from_nftables`
and `test_restore_adds_interface_restriction_to_nftables` assert the
qualified form's exact escaped text appears in the rendered script.
Measured: running the rendered script against a genuinely rendered
`nftables.conf` performs both substitutions and returns the file
byte-identical after the pair. The tailnet integration suite is the one
test that would fail if the two forms drifted apart, since it reaches the
target's public SSH port after running the script — but it runs only under
Incus and its failure message would say the script failed, not that a rule
had been reworded. In the default suite nothing compares the script's
pattern against the firewall template's rule, so rewording the rule would
leave every test that runs by default green. See `design.md`'s
`## Failure modes`.

### EMRG-17 — Deployed, never executed

THE Bootstrap SHALL deploy the break-glass script without executing it, so
that no bootstrap run changes this host's reachability by way of this spec.

**Why:** this is what keeps `ALW-1` an allowance for a human action rather
than a hole in the playbook. If any code path could invoke the script — a
handler, a rescue block, a "repair if unreachable" convenience — then a run
that mis-detected a failure could reopen a host to the internet with nobody
watching, and `INV-9` would be violated by the very tool `INV-6` depends on.
Keeping the role to one `template` task means the weakening requires a
person, at a console, typing a path.
**Verified:** the role's `tasks/main.yml` contains exactly one task, a
`template`, and its `handlers/main.yml` defines no handlers at all — the
deployment task notifies nothing, so there is no handler for a later role's
`notify` to reach either. No `command`, `shell`, `script` or `raw` task
anywhere in this repository names `emergency_access_script_path` or the
script's filename; `site.yml` mentions the path only in the closing message
it prints for the operator, and the verification play only `stat`s it. The
one place the script is executed by automation is the tailnet integration
suite, which runs it deliberately against a throwaway VM to test what it
does — that is a test of `EMRG-3` and `EMRG-4`, not a bootstrap run, and it
is why this requirement is about the *Bootstrap* rather than about the
repository. Nothing asserts any of this: no test counts the role's tasks,
and a second task added to the role would fail no check in this project.
