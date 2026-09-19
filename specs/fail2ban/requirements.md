# Fail2ban — Requirements

**Prefix:** `F2B`

## Purpose

This spec covers the one component in this bootstrap that reacts to traffic
rather than deciding in advance what to admit. Everything else here is
static: sshd offers one authentication method, the firewall's input chain
drops what no rule names, PAM counts failures at a prompt no network client
ever reaches. fail2ban reads the authentication records sshd writes to the
journal, counts the failures coming from each source address, and when one
crosses a threshold it installs a kernel rule that stops that source's
packets for a while.

What would be worse without it is not "an attacker gets in". `INV-2` means
sshd will not complete an authentication against anything but a key it
already holds, so the brute-force attempt this spec exists to answer cannot
succeed no matter how long it runs. What it can do is run forever, for free,
and write a line to the journal for every attempt. That is the cost fail2ban
removes: the connection handling, the key exchange, and — the part this
project actually feels — the journal volume. `LOG-2` caps the journal at
500M and `LOG-3` at a month, whichever comes first, and a scanner producing
authentication failures faster than the host produces anything else buys
itself the eviction of the oldest records in that window. Those records are
the ones `INV-7` requires. fail2ban is therefore defence in depth against an
attacker and a first-order control over the audit trail.

## Scope

### In scope

- Installing fail2ban from the distribution's package repository.
- The configuration directory and the jail file this spec deploys, their
  paths, ownership and modes.
- The SSH jail: whether it exists, which port it watches, which filter it
  applies, and where it reads its evidence from.
- The counting policy — how many failures, in what window — and how long a
  ban lasts.
- The mechanism a ban is enforced by, and the fact that this project pins
  it explicitly rather than inheriting whatever the package defaults to.
- The fact that the jail's counters are stated at jail level as well as at
  `[DEFAULT]` level, and what that pins.
- Enabling the service at boot and starting it during a run, and restarting
  it when the jail configuration changes.

### Out of scope

- **Which sources are worth banning.** This spec deploys a threshold and a
  window; it does not maintain a reputation list, consult a blocklist
  service, or treat any address as more or less trusted than another. There
  is no allow-list here: the jail configuration this spec deploys sets no
  `ignoreip`, so the only addresses exempt from a ban are the host's own,
  which fail2ban exempts by its own default.
- **Stopping the connection before sshd sees it.** A ban is installed after
  a source has already failed `fail2ban_max_retry` times, which means every
  banned source was admitted, served and logged that many times first.
  Refusing a connection that has not yet misbehaved is `FW`'s job and, where
  it is configured, `KNOCK`'s.
- **Limiting attempts inside one connection.** `SSH-14` does that, and it is
  what forces an attacker to open new connections instead of retrying inside
  one — which is what makes a source-address counter able to see the attempt
  at all.
- **Counting failures at a password prompt.** `PAM-2` through `PAM-7` own
  that, at the console and at `sudo`. The two mechanisms never meet; see
  `## Interactions`.
- **Owning the kernel ruleset.** fail2ban writes into a table of its own
  alongside the one `FW` deploys. This spec does not deploy, order or
  reconcile the two, and `FW-15` is entitled to remove fail2ban's table
  without telling it; `design.md`'s `## Failure modes` records what that
  costs.
- **Jails for anything but SSH.** The deployed file defines exactly one
  jail. Settings it puts in `[DEFAULT]` would apply to another jail if one
  existed, but nothing here creates one.
- **Notifying anyone that a ban happened.** fail2ban writes its own log and
  its own database; no mail is sent, no alert is raised, and no requirement
  here asks for one.
- **Reporting on or reviewing bans.** Nothing in a bootstrap run reads the
  jail's state back. That a jail exists at all after a run is confirmed by
  `VRFY`, which is a different claim from any ban ever having worked.

## Security invariants

**Upholds:** INV-7
**Relies on:** INV-2, INV-3, INV-4
**Allowances claimed:** none

The way this spec upholds `INV-7` is indirect and worth stating precisely,
because the obvious reading — that fail2ban guards the escalation path — is
wrong. `INV-7` has two halves: escalation is restricted to named principals,
and its use leaves an audit trail. Nothing here touches the first half.
`SUDO` and `PAM` own it, and a banned address was never going to reach
`sudo` anyway, because it never authenticated. What this spec defends is the
second half, and it defends it against volume rather than against tampering.

The audit trail `INV-7` requires lives in the journal, and the journal is
finite by requirement: `LOG-2` caps it at 500M of disk and `LOG-3` at a
month, whichever binds first. Records are evicted oldest-first when either
cap is reached, and journald does not distinguish a `sudo` record from an
sshd authentication failure when it decides what to drop. So a source
address that can generate authentication failures without limit can, at no
cost to itself and without ever succeeding at anything, shorten the window
in which `INV-7`'s escalation records survive — and can do so to whatever
length it likes by raising its rate. `F2B-9`'s threshold and `F2B-10`'s ban
duration are what bound that: after `fail2ban_max_retry` failures, a source
stops being able to write to this host's journal for `fail2ban_ban_time`.
That is the whole of this spec's claim on `INV-7`, and it is a claim about
retention, not about access.

`INV-2` and `INV-3` are relied on for the sharper reason that they are what
makes this spec's own limits acceptable. Every requirement here is a delay
and a threshold, never a refusal: a source gets `fail2ban_max_retry`
attempts before anything happens to it, gets them back when
`fail2ban_ban_time` expires, and gets them back immediately if `FW-15`
removes the ban — which `design.md` records that it does. If any of those
attempts could succeed at guessing a credential, that would be an
unacceptable design. They cannot. sshd accepts no password and offers root
no login path at all, so the attempts this spec meters are attempts at
something that has no success case. This is the honest reading of what
fail2ban is doing on this host, and `F2B-9`'s `**Why:**` sets out what is
actually being counted.

`INV-4` is the reliance the brief for this spec names and the one with a
concrete mechanical edge. A ban is a rule in the kernel's packet filter, and
this project owns that packet filter. The two must not fight, and the way
they avoid fighting is that fail2ban builds a table of its own —
`inet f2b-table`, with an input chain at priority `-1`, measured — rather
than editing the `inet filter` table `FW` deploys. Priority `-1` puts
fail2ban's chain ahead of `FW-3`'s, so a ban is decided before any of the
firewall's accept rules are consulted, which is what makes a ban effective
on a path `FW-10` or `KNOCK-9` had already opened. The other half of the
reliance runs the other way and is not symmetric: `FW-15` flushes every
table in the kernel, fail2ban's included, and this spec has no way to notice.
`## Interactions` states what may and may not be assumed about that table,
and `design.md`'s `## Failure modes` states what the flush costs.

This spec claims no allowance. It opens nothing, listens on nothing, and
reaches nothing over the network; every rule it causes to exist refuses
traffic that the firewall would otherwise have admitted.

## Requirements

### F2B-1 — fail2ban installed from the distribution's package repository

THE Bootstrap SHALL install the `fail2ban` package from the distribution's
package repository, refreshing the package cache first.

**Why:** the distribution's package is what makes the rest of this spec
short. Everything this spec configures is an override of a default that
package ships — the jail definitions in `jail.conf`, the sshd filter's
regular expressions, the nftables action's command set, and the systemd unit
that orders fail2ban after `nftables.service`. Building or vendoring any of
those would mean this project owning a set of log-parsing regular
expressions that have to track OpenSSH's message wording, which is a
maintenance commitment nothing here could meet. Refreshing the cache first
is the same reasoning `FW-1` applies to `nftables`: a bootstrap runs against
a host whose package index may be older than its first `apt` invocation.
**Verified:** the role's first task installs `fail2ban` with
`state: present` and `update_cache: true`.
`test_property_27_fail2ban_installation_and_configuration` asserts the `apt`
module, the package name, `state: present` and one of two spellings of
`update_cache`, as substrings of the tasks file.
`test_install_task_exists` parses the tasks file as YAML, finds the task by
name and asserts the module's `name` and `state` parameters, which is the
stronger of the two because it reads the parameters off the task rather than
finding the strings anywhere in the file. Neither confirms the package is
installed on any host; the closest thing to that is `VRFY`'s check that the
service is active, which a missing package would fail.

### F2B-2 — Configuration directory present, root-owned, world-readable

THE Bootstrap SHALL ensure `/etc/fail2ban` exists as a directory owned by
root, group root, mode `0755`.

**Why:** the directory is the package's own and exists before this task
runs, so the task is not there to create it on a normal host — it is there
so that the mode and ownership of the directory holding this host's ban
policy are stated somewhere rather than inherited from whatever the package
happened to ship. `0755` is deliberate and not a weaker choice than `0700`
would have been: fail2ban's own client reads this directory as the invoking
user, and the file inside it that carries anything sensitive is the one
`F2B-3` deploys, whose contents are thresholds rather than secrets. The task
also makes the role work on a host where the directory was removed, which is
the same convergence argument `LOG-5` makes for `/var/log/journal`.
**Verified:** the role's second task uses the `file` module with
`state: directory`, `mode: "0755"`, `owner: root` and `group: root`.
`test_property_27_fail2ban_installation_and_configuration` asserts that the
path `/etc/fail2ban` and the string `ansible.builtin.file:` both appear
somewhere in the tasks file; it does not assert the mode, the owner or the
group, and it cannot tell that the two strings belong to the same task. No
unit test parses this task, and nothing reads the directory's real mode from
a host.

### F2B-3 — Jail configuration deployed as a template to the path fail2ban reads last

THE Bootstrap SHALL render the jail configuration from a template to
`/etc/fail2ban/jail.local`, owned by root, group root, mode `0644`.

**Why:** the path is not an arbitrary choice and the `.local` suffix is the
whole of the mechanism. fail2ban reads `jail.conf`, then `jail.d/*.conf`,
then `jail.local`, then `jail.d/*.local`, merging all of them into one set
of sections, and the package's own instructions say not to edit `jail.conf`
because a package upgrade replaces it. Deploying a separate `jail.local`
means this project never edits a packaged file, never has to merge with one,
and re-renders to exactly the same content on every run — `INV-9`'s
convergence argument, applied to the one file here that carries policy.
Mode `0644` matches the packaged configuration's own mode and holds no
secret; the file's contents are three durations, a count and two action
names.
**Verified:** the role's third task templates `jail.local.j2` to
`dest: /etc/fail2ban/jail.local` with `mode: "0644"`, `owner: root` and
`group: root`.
`test_property_27_fail2ban_installation_and_configuration` asserts the
template module, the template's filename and the exact `dest:` line as
substrings of the tasks file. Nothing asserts the mode, the owner or the
group of this file in any suite, and nothing reads them from a host. The
read order this requirement depends on was measured rather than assumed: see
`F2B-12`.

### F2B-4 — The SSH jail exists only when it is enabled

THE Bootstrap SHALL define an SSH jail that fail2ban activates when
`fail2ban_ssh_enabled` is true, and SHALL leave fail2ban supervising no jail
at all when it is false; `fail2ban_ssh_enabled` SHALL default to true.

**Why:** this is the only switch in the spec, and it is worth being exact
about what the "off" position produces, because it is not "fail2ban with a
dormant jail". Measured: with `fail2ban_ssh_enabled` false, fail2ban's own
configuration reader emits no `add` and no `start` command at all — the
server comes up supervising nothing, with the service still enabled by
`F2B-13` and still running after `F2B-14`. That is the right shape for an
off switch, because it leaves no half-configured jail that a later change
could accidentally activate with stale settings, and because a running
server with no jails is visibly different from a stopped one when an
operator goes looking. Defaulting to true rather than false is the choice
that matters less than it looks, because the distribution's own
`jail.d/defaults-debian.conf` already sets `[sshd] enabled = true`: the
requirement that carries weight here is the *false* branch, where this
project's `jail.local` — read after `jail.d/*.conf` — overrides the
package's enablement. Measured: it does, and what it produces is a server
with no jail at all rather than a disabled one.
**Verified:** the template renders `enabled = true` or `enabled = false`
from `fail2ban_ssh_enabled`, and the defaults file sets it to `true`.
`test_sshd_jail_enabled` renders the template with the flag true and asserts
both `[sshd]` and `enabled = true` appear.
`test_property_27_fail2ban_installation_and_configuration` asserts the exact
Jinja expression and that `fail2ban_ssh_enabled:` appears in the defaults
file. Nothing in either suite renders the template with the flag false, so
the "no jail at all" half of this requirement is covered only by the
measurement above, which was made by running the packaged
`fail2ban-client -d` over a rendered `jail.local` placed in a copy of the
package's whole configuration tree — `jail.d/defaults-debian.conf`
included, since without it the override being measured has nothing to
override. `VRFY`'s check that
`fail2ban-client status` mentions `sshd` covers the enabled half on a live
host.

### F2B-5 — The SSH jail watches the port sshd listens on

THE Bootstrap SHALL configure the SSH jail to watch TCP on the port named by
`ssh_port`, defaulting to 22.

**Why:** the jail's port is not what it reads — it reads the journal — it is
what a ban *blocks*. fail2ban's nftables action renders the jail's `port`
into the rule it installs, so a jail naming the wrong port produces bans that
are installed successfully, reported as active by `fail2ban-client`, and let
the banned source keep connecting to SSH. Measured: with `ssh_port` 2222 the
action's rendered `port` property is `2222`, and with the default it is `22`.
Reading the port from `ssh_port` rather than restating it is the same
indirection `FW-14` uses for the firewall's accept rule, and for the same
reason — three places naming the SSH port is three places to forget.
**Verified:** the template renders `port = {{ ssh_port | default(22) }}` and
`protocol = tcp` in the `[sshd]` section.
`test_ssh_port_in_jail` renders with `ssh_port` 22 and asserts `port = 22`.
`test_property_27_fail2ban_installation_and_configuration` asserts
`port = {{ ssh_port` and `protocol = tcp` appear in the template. No test
renders a non-default port, and nothing compares this value against the one
the `ssh` or `firewall` role was rendered with — the agreement is by
construction. The default in the `| default(22)` filter duplicates
`SSH-13`'s own default, so a change to that default reaches this jail only
if both are changed.

### F2B-6 — The SSH jail takes its evidence from the systemd journal

THE Bootstrap SHALL leave the SSH jail reading sshd's authentication records
from the systemd journal rather than from a log file path.

**Why:** sshd on this host writes to the AUTH facility at `LogLevel INFO`
and nothing in this project configures a file destination for it, so on a
journald-only host there is no `/var/log/auth.log` to tail. What a
file-tailing jail does with that is worth stating accurately, because the
tempting version of this argument is wrong. It does not start quietly and
ban nobody: measured, with a non-`systemd` backend and no `auth.log`
present, the configuration the server is actually started from raises
`Have not found any log file for sshd jail` and the start fails outright,
which on a bootstrap run would fail `F2B-14`'s task. So the reason the
journal is right here is not that a file backend fails silently — it is
that a file backend fails, full stop, on a host nothing gives a log file to,
and `LOG-1` makes the journal the durable place those records do live.
The honest ownership of this requirement is also worth stating: the choice
is the *distribution's*. `jail.d/defaults-debian.conf` sets
`[sshd] backend = systemd`, which this project neither makes nor could
override from where it sets `backend` today (`F2B-7`). This spec records the
outcome as a requirement so that a package change that moved it would be a
spec violation rather than a surprise.
**Verified:** measured, and the measurement is the reason this requirement
is worded as an outcome rather than as a setting. Running the packaged
`fail2ban-client -d` over the rendered `jail.local`, in a copy of the
package's whole configuration tree, reports `['add', 'sshd', 'systemd']`,
and reports the same `systemd` when `fail2ban_ssh_backend` is set to
`polling` — because `jail.d/defaults-debian.conf` sets `backend` inside its
own `[sshd]` section, and a jail-level setting beats the `[DEFAULT]` one
`F2B-7` deploys. Measured which file decides: changing
`paths-debian.conf`'s `sshd_backend` to `polling` leaves the jail at
`systemd`, and changing `jail.d/defaults-debian.conf`'s `[sshd] backend` to
`polling` moves it. So this requirement is true, and it is true for a reason
`F2B-7` does not supply; `design.md`'s `## Failure modes` records the
divergence and names the file. The loud-failure measurement above was made
through the same reader with `allow_no_files=False`, which is what a real
start uses; `fail2ban-client -d` passes `True` and therefore cannot show it.
`test_backend_is_systemd` and `test_fail2ban_journald_backend_configuration`
assert `backend = systemd` in the rendered file and in the defaults, which
is a statement about `F2B-7`'s line, not about this jail's effective
backend. The latter also asserts that the template's `[sshd]` section
mentions `journald` or `systemd` somewhere — a check that this requirement
is *documented* in the file, not that it holds. One property of the
inherited configuration is worth stating here so that nobody reads more
scoping into this requirement than it claims: the drop-in's
`journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd` is a **disjunction**,
so the jail reads records from `ssh.service` *or* from any process named
`sshd`. **Read, not measured** — and the distinction matters here, because
the `-d` dump shows only the `+` passing through as an uninterpreted token
and says nothing whatever about its meaning. The semantics come from reading
`filtersystemd.py`, where `addJournalMatch` starts a new match group at each
`+` and `_addJournalMatches` joins the groups with `add_disjunction()`;
`design.md` names that call. This requirement says the evidence comes from
the journal; it does not say it comes only from sshd's unit, because it does
not.

### F2B-7 — The jail file's default backend is configurable

THE Bootstrap SHALL set the `[DEFAULT]` backend in the deployed jail
configuration to the value of `fail2ban_ssh_backend`, defaulting to
`systemd`.

**Why:** this is a separate requirement from `F2B-6` because it is a
separate fact, and collapsing the two would state something false. `F2B-6`
is about what the SSH jail actually reads; this is about what the deployed
file says, which is what any jail that does *not* set its own backend would
inherit. The SSH jail does set its own, from the distribution's
`jail.d/defaults-debian.conf`, so this requirement's practical effect on
this host is nil and the variable is inert. Stating it anyway is what makes
the inertness visible rather than leaving a reader to assume the variable
does what its name says, and it leaves the right thing in place for a
future jail that the package does not pin.
**Verified:** the template renders `backend = {{ fail2ban_ssh_backend }}` in
the `[DEFAULT]` section and the defaults file sets it to `"systemd"`.
`test_backend_is_systemd` asserts `backend = systemd` in the rendered file.
`test_fail2ban_journald_backend_configuration` asserts that
`fail2ban_ssh_backend:` appears in the defaults file, that the file contains
its value in one of two spellings, and that the string
`backend = {{ fail2ban_ssh_backend }}` appears *anywhere* in the template —
not that it is in `[DEFAULT]`, which is the only section it could usefully
be in.
`test_property_27_fail2ban_installation_and_configuration` is the one that
asserts the line is inside the slice of the template before `[sshd]`. Every
one of those assertions is satisfied by the rendered text and none of them
observes the backend the jail is created with, which is `F2B-6`'s
measurement.

### F2B-8 — The SSH jail uses the packaged sshd filter in aggressive mode

THE Bootstrap SHALL apply the distribution's `sshd` filter in its
`aggressive` mode to the SSH jail.

**Why:** the packaged filter's default mode counts an authentication that
was attempted and refused. On a host configured by this project that is a
narrow set of events, because an attacker who never gets a key accepted
mostly does not produce one: measured against the filter fail2ban actually
compiles, a failed public key offer by a *valid* user is explicitly marked
as a non-failure, so the default mode's main signal is `invalid user` and
`Failed publickey for invalid user`. `aggressive` adds the two sets that
matter on a key-only daemon. Its `ddos` set matches sources that never
finish a protocol handshake —
`Did not receive identification string from <HOST>`,
`Timeout before authentication for <HOST>` (which is `SSH-15`'s grace time
expiring), bad protocol identifiers, and the
`Connection closed by authenticating user … [preauth]` line modern OpenSSH
clients produce. Its `extra` set matches
`Unable to negotiate with <HOST>: no matching … found`, which is what
`SSH-5`, `SSH-6` and `SSH-7`'s restricted algorithm lists produce for a
client this host will not talk to. Without `aggressive`, the scanners that
generate the most journal volume on a hardened host are exactly the ones the
jail cannot see, because they never get far enough to fail an
authentication. The cost is stated as a failure mode rather than hidden: the
same `extra` set bans a *legitimate* operator on an old client, who is
refused for the same reason a scanner is.
**Verified:** the template's `[sshd]` section sets
`filter = sshd[mode=aggressive]` and carries a comment giving the
`Connection closed by authenticating user` case as its reason. Measured:
`fail2ban-client -d` over the rendered file compiles a failregex list that
contains the `ddos` and `extra` patterns quoted above alongside the common
ones, and contains the `<F-NOFAIL>publickey</F-NOFAIL>` construction that
makes a valid user's failed key offer not count.
`test_property_27_fail2ban_installation_and_configuration` asserts only
`filter = sshd` as a substring, which every mode satisfies, so nothing in
either suite would notice `aggressive` being dropped.

### F2B-9 — A source is banned after a configurable number of failures in a configurable window

THE Bootstrap SHALL configure the SSH jail to ban a source address once it
has produced `fail2ban_max_retry` matched failures within `fail2ban_find_time`,
defaulting to 5 failures within 10 minutes.

**Why:** this is the requirement where the honest limit has to be stated,
because the threshold looks like a credential-guessing budget and is not
one. `INV-2` means sshd accepts no password, so there is no secret here that
five guesses gets an attacker five fifths of the way through. What the
counter actually meters, on this host, is a source's *rate of costing the
host something*: five refused connections — a scanner that cannot negotiate
`SSH-5`'s algorithms, a bot walking usernames past `SSH-12`'s `AllowGroups`,
a client exhausting `SSH-14`'s three attempts and being disconnected — buy
ten minutes of silence. What banning buys is therefore three things, none of
which is "keeps the attacker out": the host stops doing key exchanges for a
source that will never authenticate; the source stops writing lines into a
journal `LOG-2` caps at 500M, which is this spec's claim on `INV-7`; and the
records that do survive are readable, because a real anomaly is not buried
under a thousand identical failures from one address. Five and ten minutes
are the packaged defaults restated rather than values this project derived,
and the value of restating them is that they are declared and configurable,
not that they differ.
**Verified:** the template renders `maxretry = {{ fail2ban_max_retry }}` and
`findtime = {{ fail2ban_find_time }}` in both `[DEFAULT]` and `[sshd]`, and
the defaults file sets `5` and `"10m"`.
`test_max_retry_rendered`, `test_find_time_rendered` and
`test_custom_max_retry` render the template and assert the values land.
`test_property_27_fail2ban_installation_and_configuration` asserts both
lines appear in the `[DEFAULT]` slice and that both variables are defined in
the defaults; `test_fail2ban_configuration_consistency` asserts each appears
in both sections. Measured: `fail2ban-client -d` over the rendered file
reports `['set', 'sshd', 'maxretry', 5]` and
`['set', 'sshd', 'findtime', '10m']`. Nothing anywhere counts a real
failure or observes a real ban; no test and no verification step produces
authentication failures against a host and checks that a ban follows.

### F2B-10 — A ban lasts a configurable time

THE Bootstrap SHALL configure the SSH jail to hold a ban for
`fail2ban_ban_time`, defaulting to 10 minutes.

**Why:** the duration is a trade between the two ways this control fails.
Too short and a scanner simply waits it out, which costs it nothing because
it has thousands of other hosts to try in the meantime. Too long and the
operator locked out by `F2B-8`'s aggressive filter — on an old client, or
with too many keys in their agent — is locked out for that long, from a host
whose other access paths `SSH-18` and `FW-10` may have narrowed to a tailnet
they are trying to reach it over. Ten minutes resolves that towards
recoverability: it is long enough to make a brute-force attempt's effective
rate negligible and short enough that a self-inflicted ban is waited out
rather than escalated to the provider's console. It is also, deliberately, a
duration the operator can lengthen without this spec changing, because the
right value depends on how a deployment is reached.
**Verified:** the template renders `bantime = {{ fail2ban_ban_time }}` in
both `[DEFAULT]` and `[sshd]`, and the defaults file sets it to `"10m"`.
`test_ban_time_rendered` and `test_custom_ban_time` render and assert the
value, the second with `1h`.
`test_property_27_fail2ban_installation_and_configuration` and
`test_fail2ban_configuration_consistency` assert the line appears in each
section. Measured: `fail2ban-client -d` reports
`['set', 'sshd', 'bantime', '10m']`. Nothing observes a ban expiring, and
nothing anywhere establishes that a ban is still in force ten minutes after
it was installed — `design.md`'s `## Failure modes` records a reason it
routinely is not.

### F2B-11 — Bans are enforced through nftables

THE Bootstrap SHALL enforce bans through the nftables ban action named by
`fail2ban_banaction`, defaulting to `nftables-multiport`, and SHALL use that
same action for both the port-scoped and the all-ports ban actions.

**Why:** `FW-1` makes nftables this host's packet filter, and this
requirement makes the ban action agree with it explicitly rather than by
inheritance. The tempting justification — that fail2ban would otherwise
default to `iptables-multiport` and land the bans in a shim's table — is
false on the platform this project targets, and saying so is the point of
this `**Why:**`. Measured: the distribution ships
`jail.d/defaults-debian.conf` with `[DEFAULT] banaction = nftables`, read
after `jail.conf`, and the `nftables` action's own `type` already defaults
to `multiport`. With this project's `banaction` line removed the jail is
created with `nftables`, and the action's every command, tag and
initialisation value is byte-identical to the one `nftables-multiport`
produces — only the name differs. So what this requirement buys is not a
different mechanism; it is that the mechanism is *stated*, in this
project's own variable, where a reader of the role can see it and a
deployment can change it, instead of being a property of a package file
that could change under the host. The cost of stating it is one wart:
`nftables-multiport` is marked `Obsolete: superseded by
nftables[type=multiport]` in its own packaged header, so this project pins
a deprecated spelling of the action it would have inherited.
Setting `banaction_allports` to the same value is *not* the harmless
belt-and-braces it looks like, and this requirement is deliberately worded
as "that same action" so that the consequence is on the record rather than
hidden: the package sets `banaction_allports = nftables[type=allports]`,
and overriding it with a multiport action means a jail that later asks for
the all-ports shape gets a port-scoped ban instead. Measured, against a
probe jail using `%(banaction_allports)s`: the package's value renders a
rule with no `dport` at all, this project's renders the jail's own port. No
jail here uses the setting, so nothing is wrong on a host today; a jail
added later would be quietly narrower than it asked to be.
**Verified:** the template renders `banaction = {{ fail2ban_banaction }}`
and `banaction_allports = {{ fail2ban_banaction }}` in `[DEFAULT]`, and the
defaults file sets `"nftables-multiport"`.
`test_banaction_is_nftables` renders and asserts
`banaction = nftables-multiport`.
`test_fail2ban_nftables_banaction_configuration` asserts the exact default
value in the defaults file in one of two spellings, and asserts both lines
are inside the template's `[DEFAULT]` slice.
`test_property_27_fail2ban_installation_and_configuration` asserts the
`banaction` line and that the word `nftables` appears in the defaults.
Measured: `fail2ban-client -d` over the rendered file reports the action's
`actionstart` creating `inet f2b-table` with
`type filter hook input priority -1`, its `actionban` as
`nft add element inet f2b-table <addr_set> { <ip> }`, and its `blocktype` as
`reject`. Nothing observes a rule being installed on a host. Note that
`test_fail2ban_nftables_banaction_configuration`'s own failure message for
the `banaction_allports` assertion reads "for all-port blocking", which the
value it asserts does not produce; the message is inside the assertion and
was left as found, so this line is the record of it rather than a fix.

### F2B-12 — The jail's counters are pinned at jail level

THE Bootstrap SHALL state the SSH jail's failure count, counting window and
ban duration in the jail's own section as well as in `[DEFAULT]`, so that no
`[DEFAULT]` value from any configuration file fail2ban reads can change
them.

**Why:** the restatement looks redundant and is not, and the template's own
comments used to say the opposite of what it does. Measured: with a
`jail.d/*.local` file — the last thing fail2ban reads — setting
`[DEFAULT] maxretry = 99`, the jail is still created with `maxretry 5` while
the restatement is present, and is created with `maxretry 99` as soon as it
is removed. So the three restated lines are precisely what stops a later
`[DEFAULT]` override from reaching this jail; they do not "inherit from
`[DEFAULT]` if not specified", they are what makes the jail not inherit.
Whether that pinning is desirable is a judgement this requirement makes
explicitly rather than by accident: the jail's values come from this
project's variables, and an operator who wants to change them changes the
variables and re-runs, which is `INV-9`'s model. Both copies render from the
same variable, so they cannot disagree with each other. The same shadowing
rule, read the other way, is why `F2B-7` does not achieve `F2B-6` — the one
setting the packaged `jail.conf` does state at jail level is `backend`, and
this file states that one only in `[DEFAULT]`.
**Verified:** the template's `[sshd]` section restates `maxretry`,
`bantime` and `findtime`, each from the same variable as its `[DEFAULT]`
counterpart. `test_fail2ban_configuration_consistency` asserts all three
appear in both sections and that the template documents the inheritance
relationship; that last assertion is a substring test for the word
`inherit`, which the template satisfies whether the sentence around it is
true or false, so it is not evidence for this requirement. The measurement
above, made by running the packaged `fail2ban-client -d` with and without a
`jail.d/*.local` override, is.

### F2B-13 — Service enabled at boot

THE Bootstrap SHALL enable the fail2ban service to start at boot.

**Why:** a host reboots for the kernel updates `UPD` installs, and a jail
that has to be started by hand afterwards is a jail that is not running on
exactly the hosts nobody is watching. Enabling it is also what makes the
boot-time ordering work in this project's favour: the packaged unit declares
`After=nftables.service`, so on every boot the firewall's ruleset is loaded
before fail2ban starts and builds its table — which is the one ordering in
this spec that is right by construction rather than by luck.
**Verified:** the role's fourth task sets `enabled: true` on the `fail2ban`
unit via the `systemd` module.
`test_service_enabled_task_exists` parses the tasks file, finds the task and
asserts the module's `name` and `enabled` parameters.
`test_property_27_fail2ban_installation_and_configuration` asserts the
`systemd` module and one of two spellings of `enabled` appear in the file.
`VRFY` checks on a live host that the unit's `UnitFileState` is `enabled`,
which is the only assertion anywhere about the real system. The
`After=nftables.service` ordering was read out of the packaged unit file,
not observed at a boot.

### F2B-14 — Service running after a bootstrap run

THE Bootstrap SHALL leave the fail2ban service running when a bootstrap run
completes.

**Why:** the configuration this spec deploys has no effect until a server
reads it, and the state that matters at the end of a run is the running one
— an operator who is told the bootstrap succeeded should not have to check
separately whether the thing it configured is doing anything. Keeping this
separate from `F2B-13` rather than folding both into one `systemd` task is
what makes the two claims separately checkable: enabled-but-not-running and
running-but-not-enabled are different defects with different symptoms, and
`VRFY` tests them as two tests for that reason.
**Verified:** the role's fifth task sets `state: started` on the `fail2ban`
unit. `test_service_started_task_exists` parses the tasks file and asserts
the module's `name` and `state` parameters.
`test_property_27_fail2ban_installation_and_configuration` asserts
`state: started` appears somewhere in the file, which the handler's
`state: restarted` does not satisfy but which no other task in this role
would. `VRFY` asserts the unit's `ActiveState` is `active` on a live host,
and separately that `fail2ban-client status` mentions the `sshd` jail — the
second being the only check anywhere that the running server actually loaded
the jail this spec configured. Note what "running" does not establish: a
fail2ban with no jails is `active` too, which is the state `F2B-4` produces
when the flag is off.

### F2B-15 — Service restarted when the jail configuration changes

THE Bootstrap SHALL restart the fail2ban service when, and only when, the
deployed jail configuration changes.

**Why:** fail2ban reads its configuration when the server starts and not
afterwards, so a re-rendered `jail.local` is a statement about the next
restart and nothing else — the same reasoning `SSH-17`, `FW-19` and `LOG-4`
apply to their own deployed files. The "and only when" half is the ordinary
declarative argument — an unchanged file should produce an unchanged host —
plus one specific cost: a restart runs the ban action's stop and start, so
between them the kernel briefly holds no bans at all. Bans are not lost to
it, because fail2ban restores every currently-banned source from its own
database when a jail starts, with the remaining ban time recomputed. That
restore is worth noticing for a reason beyond this requirement: **a jail
start** is the only thing that puts back a ban `FW-15`'s flush discarded
for a source that does not offend again, and this requirement's restart is
the only thing in a bootstrap run that causes one. A reboot causes one too,
which is why `design.md` calls the reboot case self-healing. fail2ban rebuilds the *table* on its
own, at the next ban, and re-bans the source that triggered that rebuild;
what it never does is reinstate a ban for an address that has gone quiet.
So a run that changes both files heals itself and a run that changes only
the firewall's does not. `design.md`'s
`## Failure modes` sets that out in full.
**Verified:** the role's template task carries `notify: restart fail2ban`
and no other task in the role notifies anything; the handlers file defines
one handler, `Restart fail2ban`, listening on that topic and setting
`state: restarted` on the unit.
`test_property_27_fail2ban_installation_and_configuration` asserts the
`notify:` line appears in the tasks file and asserts the handler's name in
one of two capitalisations, its module, its target and `state: restarted`.
`test_template_deploy_notifies_restart` parses the tasks file, finds the
template task by name and asserts it has a `notify` at all — the only
assertion that ties the notification to that particular task rather than to
the file. Nothing asserts the "and only when" half: no test counts the
notifying tasks, and a `notify` added to the install task would fail no
check here. The restore-on-start behaviour this requirement's `**Why:**`
relies on was read out of the packaged fail2ban server, not observed at a
restart; `design.md` names where.
