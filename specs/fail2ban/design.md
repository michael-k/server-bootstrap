# Fail2ban — Design

## Approach

The role is five tasks and a handler. It installs the distribution's
package, makes sure the configuration directory is there, renders one file
into it, enables the unit and starts it; the handler restarts the unit when
that one file changes. Nothing here writes a rule, parses a log, or talks to
the kernel. Everything this spec is *about* happens afterwards, inside a
daemon this project only configures.

That division is the whole of the design, and it is why the interesting
parts of this document are not about the role's Ansible. The file the role
renders is `/etc/fail2ban/jail.local`, which is one of several files
fail2ban merges into a single set of configuration sections — the packaged
`jail.conf` first, then `jail.d/*.conf`, then this file, then
`jail.d/*.local`. Within that merge a setting in a jail's own section beats
the same setting in `[DEFAULT]`, whichever file each came from. Two of this
spec's requirements exist because of that rule and would look redundant
without it: `F2B-12`, which restates three counters at jail level so a later
`[DEFAULT]` cannot move them, and `F2B-6`, which is separated from `F2B-7`
because the distribution's own drop-in states `backend` at jail level and
this file states it only in `[DEFAULT]`.

That drop-in is `jail.d/defaults-debian.conf`, it is short enough to quote,
and more of this document turns on it than on anything this project writes:

```
[DEFAULT]
banaction = nftables
banaction_allports = nftables[type=allports]

[sshd]
backend = systemd
journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd
enabled = true
```

It decides `F2B-6`, it is what `F2B-11` overrides rather than corrects, and
it is what `F2B-4`'s false branch has to beat. A reader who does not know it
exists will misdiagnose every one of them.

The second thing worth stating up front is where the enforcement lives.
fail2ban's nftables action builds a table of its own — `inet f2b-table`,
input chain at priority `-1`, one address set per jail and family — and adds
the banned address as a set element. `FW` deploys a different table,
`inet filter`, at priority `0`. The two never edit each other and the
priority puts fail2ban's decision first, so a ban holds even on a path
`FW-10` or `KNOCK-9` has opened. What they do share is the kernel, and
`FW-15`'s `flush ruleset` empties all of it. Most of `## Failure modes` is
downstream of that single fact.

Everything in this document that is stated as measured was measured in this
repository's environment, and the instrument matters enough to name. Jail
behaviour comes from running the packaged `fail2ban-client -d` over a
rendered `jail.local` placed in a copy of the package's **whole**
configuration tree — `jail.d/defaults-debian.conf` included, without which
three of this document's findings invert. Kernel behaviour comes from
building both tables in a user network namespace and reloading a ruleset
that begins with `flush ruleset`. Ansible behaviour comes from running a
play with the same shape as `site.yml`.

`-d` is not the same instrument as a real start, and one finding here turns
on the difference: it passes `allow_no_files=True` to the configuration
reader, so it cannot see a jail whose start would abort for want of a log
file. Claims about that path were taken by calling the same reader with
`allow_no_files=False`, which is what the server uses. Where a claim comes
from reading the packaged server's source rather than from running
anything, it says so.

## Implementation map

| Path | Realises |
|---|---|
| `roles/fail2ban/tasks/main.yml` | F2B-1, F2B-2, F2B-3, F2B-13, F2B-14, F2B-15 |
| `roles/fail2ban/defaults/main.yml` | F2B-4, F2B-7, F2B-9, F2B-10, F2B-11 |
| `roles/fail2ban/templates/jail.local.j2` | F2B-4, F2B-5, F2B-6, F2B-7, F2B-8, F2B-9, F2B-10, F2B-11, F2B-12 |
| `roles/fail2ban/handlers/main.yml` | F2B-15 |

`F2B-6` appears against the template because the template is where the SSH
jail is defined, not because any line in it sets that jail's backend — the
value comes from `jail.d/defaults-debian.conf`, which is not this project's
file at all. It is in the map so that a change to the template's `[sshd]`
section is understood to be a change to this requirement; see
`## Failure modes`.

`F2B-5` has no row in `defaults/main.yml` because the port is not this
role's variable. It comes from `ssh_port`, which `SSH-13` owns, through a
`| default(22)` in the template.

## Key decisions

**The systemd journal rather than a log file — a decision this project
did not make.** This has to be the first sentence of the entry, because the
honest account is that `jail.d/defaults-debian.conf` sets
`[sshd] backend = systemd` and nothing in this repository can reach that
setting from where it puts its own (`F2B-7`). What follows is therefore why
the inherited choice is the right one to hold this project to, not why this
project chose it.

fail2ban's upstream default backend polls or tails a file, and for the SSH
jail that file would be `/var/log/auth.log`. Nothing in this project
produces one: sshd is configured with neither `LogLevel` nor
`SyslogFacility`, so it keeps OpenSSH's defaults and writes to the AUTH
facility at `INFO`, and on a host with journald and no syslog daemon
forwarding to disk those records exist only in the journal. The tempting
argument from there is that a file-tailing jail would fail *silently* —
start normally, watch a path that never appears, ban nobody. That is wrong,
and it is wrong in the direction that matters. Measured, through the same
configuration reader a real start uses: with a non-`systemd` backend and no
`auth.log`, `JailsReader.convert(allow_no_files=False)` raises
`ValueError: Have not found any log file for sshd jail`. The server does not
come up, so `F2B-14`'s task fails and the bootstrap run fails with it. The
measurement is worth keeping for a second reason: `fail2ban-client -d`
passes `allow_no_files=True`, so a `-d`-only investigation structurally
cannot see this, and an earlier revision of this document asserted the
opposite on exactly that evidence.

So the argument for the journal is not silence, it is availability plus
durability — it is where the records are, and `LOG-1` makes it persistent,
so the evidence survives a reboot rather than being whatever has
accumulated since. What the journal backend does *not* buy is scoping: the
`journalmatch` the drop-in supplies,
`_SYSTEMD_UNIT=ssh.service + _COMM=sshd`, is a **disjunction**, not a
conjunction. The `+` starts a new match group and fail2ban joins the groups
with `add_disjunction()`, so the jail reads any record from `ssh.service`
*or* from any process whose `_COMM` is `sshd`. That is looser than the unit
name suggests, and an earlier revision of this document claimed the
opposite.

**Pinning the ban action, not choosing nftables over iptables.** Upstream
fail2ban defaults to `iptables-multiport`, and the obvious story about this
decision is that naming an nftables action rescues the host from a shim's
table. On Debian that story is false. The drop-in quoted in `## Approach`
sets `[DEFAULT] banaction = nftables`, and `action.d/nftables.conf`'s own
`type` already defaults to `multiport`. Measured: with this project's
`banaction` line removed, the jail is created with `nftables`, and the
resulting action's every command, tag and initialisation value is
byte-identical to what `nftables-multiport` produces — only the action's
name differs.

What `F2B-11` actually buys, then, is that the mechanism is stated in a
variable a reader of the role can see and a deployment can change, rather
than being a property of a package file that could change under the host.
That is worth having and it is a smaller claim than "we chose nftables".
The cost is a wart: `action.d/nftables-multiport.conf`'s own header reads
`Obsolete: superseded by nftables[type=multiport]`, so this project pins a
deprecated spelling of the action it would otherwise have inherited.
Changing the default to `nftables` would be a strict improvement and it is
a spec change, so it is recorded rather than made.

`multiport` rather than `allports` is the narrower of the two shapes and the
right one here, because this jail watches exactly one port: an all-ports ban
would take a source that failed to authenticate to SSH and cut it off from
every service the host might later run, a larger consequence than the
evidence supports. But `F2B-11` applies that same narrow action to
`banaction_allports`, and there it is an override rather than a
reinforcement — the package sets `banaction_allports = nftables[type=allports]`,
and this project replaces it with a multiport action. Measured against a
probe jail using `%(banaction_allports)s`: the package's value renders a
rule with no `dport`, this project's renders the jail's own port. Nothing
uses the setting today, so no host is wrong; a jail added later that asks
for the all-ports shape would silently get a port-scoped ban. That is a
defect of this project's making, and it is listed in `## Failure modes`.

Two properties of the action are worth recording because nothing else in
this spec tree would tell a reader about them. Its chain sits at priority
`-1`, ahead of `FW-3`'s chain at `0` — measured in the dumped action — which
is what makes a ban effective against traffic the firewall would have
accepted. And its `blocktype` is `reject`, not `drop`: a banned source is
told it is being refused, where `FW-3`'s policy would have said nothing at
all. That is the packaged default and this project does not change it. It is
a deliberate asymmetry in the host's behaviour — the firewall is silent to
strangers, the ban is loud to offenders — and it is defensible (a rejected
scanner moves on sooner, which is the point) but it is a real difference and
nobody reading `FW`'s spec would predict it.

**Aggressive filter mode.** Discussed in `F2B-8`'s `**Why:**`, and the short
form is that on a key-only daemon the default mode can barely see the
traffic that costs the most. What belongs here is the shape of the trade,
because it is not the usual false-positive argument. The `extra` patterns
that `aggressive` adds match
`Unable to negotiate with <HOST>: no matching … found`, and this project
*causes* that message: `SSH-5`, `SSH-6` and `SSH-7` restrict the algorithm
lists to a modern subset, so any client outside it is refused at
negotiation. A scanner using an old library produces that line. So does an
operator on an old client. The jail cannot tell them apart, because at that
point in the protocol there is nothing to tell apart — neither has offered a
credential. `F2B-10`'s ten-minute ban is the mitigation, and it is a
mitigation by duration rather than by discrimination.

**One file, no `jail.d` drop-in of this project's own.** The alternative
shape would have been to write `jail.d/sshd.local` and leave `jail.local`
alone, which is what a package integrating with fail2ban would do. This
project is not integrating with a third party's configuration — though it is
emphatically not the only thing configuring fail2ban here: the
distribution's own `jail.d/defaults-debian.conf` sets three things this
document spends its words on, and this project's relationship to each
differs — it *decides* `F2B-6`'s backend, it is what `F2B-11` *overrides*
rather than corrects, and its `enabled = true` is what `F2B-4`'s false
branch has to *beat*. And `jail.local` is the
file the package's own instructions point an administrator at. Using it
means one file of this project's to read, and it is read after every
`jail.d/*.conf`, which is what lets `F2B-4`'s false branch override the
drop-in's `enabled = true`.
What it costs is stated in `F2B-12`: `jail.d/*.local` is read *after*
`jail.local`, so a drop-in someone adds later outranks this project's
`[DEFAULT]`, and the jail-level restatement is what keeps the three counters
out of its reach.

**No `ignoreip`.** The deployed file sets no allow-list, so the only
addresses exempt from a ban are the host's own, which fail2ban exempts by
its own `ignoreself` default. A tempting alternative would have been to
exempt the tailnet range, or the controller's address, so that an operator
can never lock themselves out. It is not done, and the reason is that an
allow-list is a standing exemption that survives the compromise of whatever
is on it — a tailnet-wide exemption would mean any device on the tailnet can
brute-force this host unmetered. The recovery path for a self-inflicted ban
is `F2B-10`'s ten minutes, and beyond that `EMRG` for the case where the
narrowing and the ban compound.

## Failure modes

- **`fail2ban_ssh_backend` does not reach the SSH jail.** The template sets
  `backend` in `[DEFAULT]`. The distribution's `jail.d/defaults-debian.conf`
  sets `backend` inside `[sshd]`, and a jail-level setting beats a
  `[DEFAULT]` one no matter which file each came from. Measured: rendering
  the template with `fail2ban_ssh_backend` set to `polling` and dumping the
  result with the packaged `fail2ban-client -d` still produces
  `['add', 'sshd', 'systemd']`. The variable is therefore inert for the one
  jail this project defines.

  **Which file decides is worth getting right, because getting it wrong
  sends a diagnosis into a dead end.** It is not `jail.conf`, whose `[sshd]`
  section sets `backend = %(sshd_backend)s`, and it is not
  `paths-debian.conf`, which defines that interpolation. Measured: changing
  `paths-debian.conf`'s `sshd_backend` to `polling` leaves the jail at
  `systemd`; changing `jail.d/defaults-debian.conf`'s `[sshd] backend` to
  `polling` moves it. `jail.d/*.conf` is read after `jail.conf`, so the
  drop-in's literal `systemd` is the value in force and the interpolation
  never reaches the jail. An earlier revision of this document named
  `paths-debian.conf`, which would have sent an operator to a file where an
  override does nothing.

  Two things follow. The outcome is right — `F2B-6` holds — so this is a
  documentation-shaped defect rather than a broken host. But an operator who
  sets the variable expecting to change the jail's backend gets no error, no
  warning and no change, and the tests would not notice either: `test_backend_is_systemd` and
  `test_fail2ban_journald_backend_configuration` assert on the rendered
  text, which does change. The fix would be to set `backend` in the
  template's `[sshd]` section as well, exactly as `F2B-12` does for the
  three counters; that is a behaviour change and therefore a spec change,
  and it is recorded here rather than made.

- **A firewall reload silently unenforces every active ban, and the run that
  does it is the ordinary one.** This is the most consequential thing in
  this spec and it is worth setting out step by step, because each step was
  measured separately.

  `FW-15` makes the deployed ruleset begin with `flush ruleset`, which
  removes every table in the kernel and not only the one the file defines.
  Measured, in a user network namespace with nftables 1.1.6: with both
  `inet filter` and `inet f2b-table` present and a banned address in
  `addr-set-sshd`, loading a file that begins `flush ruleset` and defines
  only `inet filter` leaves `nft list tables` reporting `inet filter`
  alone. The ban element is gone with the table.

  `FW-19` performs that reload from a handler. Absent an explicit flush —
  and this play has one, which the paragraph after next is about — Ansible
  flushes handlers at the end of the play's task section, not at the end of
  the role that notified them, and handlers run in the order they were
  *defined*, which for roles is the order `site.yml` lists them. Measured, with
  ansible-core 2.20.3, using a two-role play of the same shape: a handler
  notified inside the first role runs after the second role's tasks have
  completed and after the `tasks:` section, and before `post_tasks`; and
  with both roles notifying, the first role's handler runs first.

  The end of the play is not in fact where the flush happens, and the
  difference does not change the conclusion but does change the evidence. An
  earlier revision of this document said `site.yml` "contains no
  `meta: flush_handlers` anywhere," which is true of that file and false of
  the play: `roles/logging/tasks/main.yml` flushes handlers unconditionally,
  and `LOG-4`'s own design entry says why. `site.yml` runs `logging` after
  `fail2ban`, so the nftables reload actually fires *mid-play, inside the
  logging role* — still after every task in this role, and still ahead of
  this role's own handler, because handlers run in role-definition order and
  `firewall` is listed first. (`roles/filesystem_hardening/tasks/main.yml`
  flushes too, but it runs before `firewall`, so nothing of this spec's is
  pending there.) So on any run where the ruleset changes, the reload
  happens after fail2ban has been installed, configured, enabled and
  started — by way of the logging role rather than the end of the play.

  One case escapes all of this and is worth naming so the split below is
  not read as exhaustive. Measured, same play shape: when a handler at a
  flush point fails, the host is marked failed and none of the remaining
  handlers runs — `force_handlers` is set nowhere in this project. `SSH-17`'s
  restart is defined before `FW-19`'s reload and fails on a host whose new
  sshd configuration cannot bind, which `specs/ssh-hardening/design.md`
  records as a real lockout path. On such a run the reload never happens,
  so this spec's table survives intact — the one way a ruleset change
  leaves the bans alone, and not a reassuring one, since the run has failed
  and the daemon is down.

  Otherwise, what the reload produces depends on whether `jail.local` also
  changed:

  - **Both changed** (a first run, or a run that alters a fail2ban
    variable): the firewall's reload handler runs, flushing fail2ban's
    table, and then fail2ban's own restart handler runs. A jail start
    restores every currently-banned source from
    `/var/lib/fail2ban/fail2ban.sqlite3` with its remaining ban time — read
    from the packaged server's `Jail.start`, not observed at a restart — so
    the table is rebuilt and the bans come back. The run heals itself.
  - **Only the ruleset changed** — which is every subsequent run that
    touches the firewall and nothing here, the common case — nothing
    restarts fail2ban. The table stays gone, fail2ban holds the tickets —
    read from the packaged server's ban manager, not observed — and the
    kernel enforces nothing.

  Recovery from the second case is partial and asymmetric, and the route
  differs depending on who shows up. A banned source that stops connecting
  is simply unbanned, silently, for the remainder of its ban time.

  A source fail2ban has *not* yet banned takes the ordinary path. Two links
  of it were measured against the kernel and the rest was read, and the two
  halves are marked here rather than run together. **Measured:** after the
  flush, `nft add element inet f2b-table …` exits 1 with
  `Error: No such file or directory`, and so does
  `nft list chain inet f2b-table f2b-chain` — so both the ban command and
  the action's own `actioncheck` fail. **Read, in `action.py`'s
  `_processCmd`:** a failed command sets the retry counter, the next pass
  through the loop runs the invariant check, that check's failure logs
  `Invariant check failed. Trying to restore a sane environment` and stops
  and restarts the action, and the command is then retried. Nothing in this
  sequence was observed running; what was observed is that its two
  preconditions hold.

  A source fail2ban already considers banned never reaches a ban command at
  all; it hits the "already banned" branch, and the repair is triggered
  there by a periodic `consistencyCheck()` on that branch rather than by any
  failure. What puts the ticket back is `invalidateBanEpoch()`, called by
  the repair: the jail's epoch advances past the ticket's, and the very next
  test in that branch re-bans every action whose epoch has moved. The
  packaged source is worth reading carefully rather than quoting loosely —
  its comment on the stop/start path says the opposite, warning that the
  tickets stay in the ban manager and so "will not be banned, because
  'already banned' will happen". That comment describes the behaviour the
  epoch bump exists to prevent, and an earlier revision of this document
  cited it as agreeing. Net effect either way: the jail self-heals for
  whoever knocks next and for nobody else.

  Nothing detects the condition and no test covers it. The same flush is
  recorded from the firewall's side in `specs/firewall/design.md` and from
  the break-glass script's side in `specs/emergency-access/design.md`; what
  is added here is which run triggers it, which does not, and what the
  partial recovery actually is.

- **A reboot is safe, and for a reason that is not this project's doing.**
  The packaged `nftables.service` is `WantedBy=sysinit.target` with
  `DefaultDependencies=no`, and the packaged `fail2ban.service` declares
  `After=… nftables.service`. So at boot the ruleset is loaded first and
  fail2ban starts afterwards, builds its table and restores its bans from
  the database. Read out of both unit files; not observed at a boot. Neither
  ordering is asserted by anything in this repository, and a change to
  either package's unit would move this into the previous bullet's
  territory without any test noticing.

- **The aggressive filter bans clients this project's own hardening
  refuses.** `SSH-5`, `SSH-6` and `SSH-7` restrict key exchange, ciphers and
  MACs; a client outside those lists gets
  `Unable to negotiate with <HOST>: no matching … found`, which is one of
  the patterns `mode=aggressive` adds. Five such attempts in ten minutes is
  a ban. The same is true of `SSH-15`'s login grace timeout
  (`Timeout before authentication for <HOST>`) and of `SSH-14`'s three-try
  limit (`Disconnecting: Too many authentication failures`), which an
  operator reaches by having four or more keys in their agent and
  reconnecting twice. None of these involves a wrong credential; all of them
  count. The exposure is bounded by `F2B-10`'s ten minutes, and it compounds
  badly with `SSH-18` and `FW-10`: on a tailnet-narrowed host the banned
  address is the operator's own tailnet address, and the remaining way in is
  the provider's console and `EMRG`. Nothing warns about this and no
  `ignoreip` softens it.

- **`fail2ban_max_retry` counts events, not authentication attempts, and the
  two differ by a lot on this host.** A single connection from a scanner can
  produce more than one matched line — an `invalid user` and a
  `Connection closed … [preauth]`, say — while a legitimate operator's
  successful login produces none that count, because the filter marks a
  valid user's failed public-key offer as a non-failure. So "5 failures"
  is not "5 connections" and the ratio depends on what the client does.
  Nothing in this project measures the ratio, and no test produces a real
  authentication failure against a real host: every assertion about
  `maxretry` in either suite is about the rendered text. The only live
  check anywhere is `VRFY`'s, which confirms the jail exists.

- **`banaction_allports` is overridden with an action that is not
  all-ports.** The package sets it to `nftables[type=allports]`; `F2B-11`
  sets it to `fail2ban_banaction`, which is a multiport action. Measured
  against a probe jail configured with `%(banaction_allports)s`: the
  package's value renders an `actionstart` with no `dport` at all, this
  project's renders one scoped to the jail's port. No jail in this project
  uses the setting, so nothing on a host today is wrong; the defect is
  latent, and it is the kind that surfaces as "the recidive jail is not
  blocking what it said it would" long after anyone remembers this line.
  The fix is to stop setting it, or to set it to the all-ports spelling; it
  is a behaviour change and therefore a spec change. Note that the
  assertion covering it in the property suite carries the failure message
  "for all-port blocking", so the test text asserts the opposite of what the
  value does — left as found, since the wording is inside the assertion.

- **Two of `VRFY`'s three checks pass on a host with no jail.** `F2B-4`'s
  off position does not produce a dormant jail; measured, it produces a
  fail2ban server with no jail at all, which is still `enabled` and still
  `active`. So the checks for `UnitFileState` and `ActiveState` are
  satisfied by a host on which nothing is being watched, and only the third
  — `fail2ban-client status` naming the `sshd` jail — can tell the two
  apart. That is the right split and it is worth knowing which of the three
  is carrying it, because a future verification play that kept the two
  service checks and dropped the status check would still report success on
  a host where `fail2ban_ssh_enabled` had been turned off by accident.

- **The whole spec is verified by reading text.** Of the assertions the
  `**Verified:**` lines cite, all but the `VRFY` checks operate on the
  tasks file, the defaults file or the rendered template. None of them
  starts fail2ban, and none of them produces a failed authentication. The
  consequence is specific rather than general: a change that leaves the
  rendered text intact but breaks the jail — the backend shadowing above is
  exactly such a change — passes everything. The measurements in this
  document were made with the packaged `fail2ban-client` and with `nft`,
  by hand, and are not wired into any suite, so they do not defend against
  regression.

- **The mode and ownership this spec states for two paths are asserted
  nowhere.** `F2B-2`'s `0755` root-owned directory and `F2B-3`'s `0644`
  root-owned file are both real parameters on real tasks, and no test in
  either suite reads either of them — the property test asserts that the
  path `/etc/fail2ban` and the string `ansible.builtin.file:` occur
  somewhere in the tasks file, which two unrelated tasks would also satisfy,
  and asserts nothing at all about the template task's mode. Nothing reads
  them from a host either. These are the weakest-covered requirements here.

- **The template's comments described the opposite of what the file does,
  and the test that looks at them cannot tell.** The `[sshd]` section's
  three restated counters carried comments reading
  `Inherits from DEFAULT if not specified` immediately above lines that
  specify them — a true general statement about fail2ban placed exactly
  where it is misleading, since those lines are what makes the jail *not*
  inherit. The comments now say what `F2B-12` says. What did not change is
  `test_fail2ban_configuration_consistency`'s assertion that the template
  contains the substring `inherit`, which was satisfied by the misleading
  text and is satisfied by the corrected text; it is a check that the topic
  is mentioned, not that it is described correctly, and it is not evidence
  for `F2B-12`. The measurement with a `jail.d/*.local` override is.

## Interactions

**What this spec assumes of others:**

- `SSH-13` — the port `ssh_port` names is the port sshd listens on, and
  `F2B-5` renders that same variable into the jail. The coupling is
  one-directional and silent if it breaks: the jail's port is what a ban
  blocks, not what it reads, so a mismatch produces bans that are installed,
  reported as active, and ineffective. Both sides carry their own
  `| default(22)`, so the default is agreed by coincidence of value rather
  than by a shared definition.
- `SSH-12` — `AllowGroups` is what turns a connection by a user outside the
  SSH access group into a logged refusal, which is one of the events
  `F2B-9` counts. This spec assumes nothing about *which* group; it assumes
  only that a refusal is logged.
- `SSH-14` — the three-attempt cap inside one connection is what forces a
  brute-force attempt to open new connections, which is the only reason a
  source-address counter can see it at all. `specs/ssh-hardening/design.md`
  states the same from the other side. It also produces
  `Disconnecting: Too many authentication failures`, which `F2B-8`'s filter
  counts, so the two mechanisms compound: `SSH-14` ends the connection and
  `F2B-9` counts the ending.
- `SSH-15` — the login grace timeout produces
  `Timeout before authentication for <HOST>`, which is one of the patterns
  `mode=aggressive` adds. A longer grace time means fewer such lines and a
  slower count.
- `SSH-5`, `SSH-6`, `SSH-7` — the restricted algorithm lists produce
  `Unable to negotiate … no matching … found` for clients outside them,
  which `F2B-8`'s filter counts as a failure. This is the one place where
  another spec's hardening directly feeds this spec's counter with events
  that are not authentication attempts; see `## Failure modes`.
- `SSH-18` — the daemon may be bound to the tailnet addresses only, in which
  case every address this spec can ever ban is a tailnet address, including
  the operator's own.
- `SSH` generally — sshd's records reach the journal under the `ssh.service`
  unit at OpenSSH's default `INFO` level, because the deployed
  configuration sets neither `LogLevel` nor `SyslogFacility`. What the jail
  matches on is looser than the unit name suggests:
  `_SYSTEMD_UNIT=ssh.service + _COMM=sshd` is a disjunction, so renaming the
  unit would *not* empty the stream as long as the process is still called
  `sshd` — and, read the other way, a record from any process named `sshd`
  in some other unit is offered to the filter too. Lowering the log level is
  the change that would really blind the jail, and it would do so with no
  error anywhere.
- `FW-1` — nftables is the host's packet filter, which is what makes
  `F2B-11`'s choice of ban action the matching one rather than an
  alternative.
- `FW-15` — the deployed ruleset begins with a flush of **every** table in
  the kernel. This spec may assume `FW` leaves `inet f2b-table` alone while
  the firewall is not being reloaded; it may **not** assume the table
  survives a reload, a re-run that changes the ruleset, or a reboot.
  `specs/firewall/design.md` states that from the firewall's side and asks
  that the flush be the interaction recorded against an ID here: it is
  recorded against `F2B-11`, whose ban action is what builds the table the
  flush removes, and `F2B-15`, whose restart is the only thing in a
  bootstrap run that starts the jail again — and a jail start is the only
  thing that puts back a ban for a source that does not offend again.
  fail2ban itself rebuilds the table, and re-bans whoever triggered the
  rebuild, but never an address that has gone quiet; a reboot starts the
  jail too, which is why that case is self-healing. `## Failure modes` sets out which runs
  trigger it.
- `FW-19` — the reload runs from a handler, and the handler runs after
  every task in this role. Where it runs is *not* the end of the play: the
  logging role's own `meta: flush_handlers` is the next flush point after
  this role, so the reload fires mid-play, inside `logging`. See
  `## Failure modes`, where the flush *semantics* and the handler order are
  measured and the flush *location in this play* is read off `site.yml` and
  that role's task file. That ordering, and not the flush
  alone, is what makes the hazard above reachable on an ordinary run.
- `FW-3` — the input chain's policy is drop, which handles every source this
  spec's jails never see. A ban is therefore always an addition to a
  default-deny posture, never the thing standing between a stranger and the
  host. `F2B-11`'s action inserts its chain at priority `-1`, ahead of
  `FW-3`'s, so a ban also overrides an accept `FW-10`, `FW-13` or `KNOCK-9`
  had granted.
- `FW-10` and `FW-13` — whichever SSH accept rule is rendered, it is what
  lets a source reach sshd in the first place; this spec only ever sees
  sources that rule admitted. It assumes nothing about which of them is in
  force.
- `LOG-1` — the journal is persistent, so the evidence `F2B-6`'s jail reads
  survives a reboot.
- `LOG-2` and `LOG-3` — the journal is capped at 500M and one month,
  whichever binds first, and records are evicted oldest-first. That cap is
  what makes this spec's claim on `INV-7` a real one: unmetered
  authentication noise buys the eviction of `INV-7`'s escalation records.
  This spec assumes only that the cap exists and is finite, not its value.
- `UPD` — kernel updates are what make a reboot a routine event, which is
  why `F2B-13`'s enablement matters and why the boot-time ordering in
  `## Failure modes` is worth having checked.
- `PRJ-12` — `site.yml` applies roles in one fixed order and this role is
  placed after `firewall`. This spec does not require that order for its own
  correctness — nothing here needs the firewall to exist first — but the
  order is what makes the reload-after-start hazard the shape it is, so a
  reordering would change this spec's failure modes without changing any of
  its requirements.

**What others may assume of this spec:**

- `PAM` — that the split described in `specs/pam-hardening/design.md` is
  exactly as that spec states it, and the reciprocal side of it is this.
  `PAM-2`, `PAM-3` and `PAM-4` configure a failed-attempt threshold, an
  unlock timeout and a counting window; `PAM-5` applies them to root as
  well; `PAM-6` and `PAM-7` place the two `pam_faillock` profiles around
  `pam_unix` in `common-auth`. Every one of those counts *password*
  failures, per account, at a prompt — the console, `su`, and `sudo`.
  `F2B-9` counts *log lines*, per source address, from a daemon that under
  `INV-2` never presents a password prompt at all. The two mechanisms
  therefore share no counter, no state, no file and no subject: a PAM
  lockout locks an account and a fail2ban ban blocks an address, and neither
  can be reached by the other's events. `PAM`'s spec may assume that
  nothing here consults `common-auth`, that nothing here increments or
  resets `pam_faillock`'s counter (so `PAM-17`'s reset-on-success is
  unaffected by any ban), and that the SSH surface's brute-force resistance
  is `F2B-8` through `F2B-11` rather than `PAM-2` through `PAM-7`. The one
  thing it may *not* assume is that this spec covers the console: a source
  address is meaningless there, so `PAM-2` through `PAM-7` remain the only
  bound on password guessing at a physical or provider console, and
  `PAM-5`'s inclusion of root is the only thing metering attempts against
  the root password. That asymmetry is the reason the two specs exist
  separately rather than one deferring to the other.
- `FW` — that this spec writes only into `inet f2b-table` and never edits
  `inet filter`, never rewrites `/etc/nftables.conf`, and never reloads the
  nftables service. A firewall reload is always `FW`'s own action or
  `EMRG`'s, never this spec's. What `FW` may not assume is that this spec
  notices a flush: it does not, and `## Failure modes` states what that
  costs.
- `EMRG` — that the bans its break-glass script discards, by way of
  `EMRG-7`'s reload of a ruleset that begins with `FW-15`'s flush, come back
  only as described in `## Failure modes`: not at all for a source that goes
  quiet, and on the next offence for a source that does not.
  `specs/emergency-access/design.md` states that the bans "come back as
  fail2ban re-detects the offenders, not immediately," which is the same
  claim at lower resolution — the detection has to be a *new* offence, and
  the first one after the flush also costs a failed ban command and an
  action restart. Neither direction of that script restarts fail2ban, so
  neither triggers the database restore that would have brought the existing
  bans back.
- `KNOCK-9` — that this spec sees fewer authentication failures on a
  knock-gated host and that the ones it does see came from a source that
  passed that requirement's set-membership test, exactly as
  `specs/port-knocking/design.md` states. It may not assume it sees none.
  That spec asks for two things to be recorded against an ID here, and
  `KNOCK-9` is the ID both belong to, though the first half holds for the
  whole knock mechanism. First, nothing in `KNOCK` disturbs this spec's ban
  table: `KNOCK-9`'s accept rule, the sets it reads, and the `KNOCK-4`
  through `KNOCK-6` rules that fill them all live inside `FW`'s
  `inet filter` table, and the only thing that reaches `inet f2b-table` is
  `FW-15`'s flush. Second, `KNOCK-9` is upstream of this
  spec's evidence rather than a substitute for it — it decides whether a
  packet reaches sshd at all, and `F2B-9` counts journal lines sshd writes
  *after* it did. The layering runs one way only: a `KNOCK-9`-passed source
  is banned by `F2B-11`'s rule exactly as any other source would be, because
  that rule's chain is evaluated at priority `-1`, before `inet filter`.
- `SSH` — that nothing here changes sshd's configuration, its port, its
  binding or its restarts. This spec reads what sshd logs and writes
  packet-filter rules; it never touches the daemon.
- `LOG` — that this spec adds no journald configuration and no log
  destination of its own. fail2ban writes its own log to
  `/var/log/fail2ban.log` by the package's default and this project does not
  change that, so the ban record is *not* in the journal `LOG` sizes and
  retains, and an auditor looking for when a ban happened should be sent to
  that file and to `/var/lib/fail2ban/fail2ban.sqlite3` rather than to
  `journalctl`.
- `VRFY` — that on a bootstrapped host the `fail2ban` unit is enabled and
  active and that `fail2ban-client status` names the `sshd` jail, which is
  what its three checks establish. Those cover `F2B-13`, `F2B-14` and the
  enabled half of `F2B-4`. They do not establish that any ban was ever
  installed, that the counters have the configured values, or that the
  file's mode and ownership are what `F2B-2` and `F2B-3` state.
- The testing spec — that every assertion it holds for this spec, apart from
  the three `VRFY` checks, reads a file: the tasks YAML, the defaults YAML,
  or the template rendered with a fixed variable set. No suite starts
  fail2ban, produces an authentication failure, or inspects the kernel. A
  suite that wanted to cover this spec in substance would have to bootstrap
  a host, fail authentication against it from a second host, and read the
  ban out of `nft list table inet f2b-table`.
