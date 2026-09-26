# SSH Hardening — Design

## Approach

The role is one task. It renders a single template over
`/etc/ssh/sshd_config`, owned by root and mode `0644`, and notifies one
handler. Everything this spec requires of sshd's configuration is a
directive in that one file, so
there is no ordering to get right inside the role, no partially-applied
state, and no second place a setting could come from.

That last point is deliberate and is the largest structural decision here:
the template is a *replacement*, not an overlay. It carries no
`Include /etc/ssh/sshd_config.d/*.conf` line, so Debian's own drop-in
directory — which cloud and provider images routinely use to set
`PermitRootLogin` and `PasswordAuthentication` to values of their own — is
inert on a bootstrapped host. The rendered file is the whole of sshd's
configuration, which is what lets every requirement in `requirements.md` be
stated as a property of one file rather than as the outcome of a merge.

Two safety mechanisms sit around the write. `SSH-19`'s
`validate: /usr/sbin/sshd -t -f %s` runs sshd's own parser against the
candidate file *before* Ansible moves it into place, so a template that
renders to something sshd cannot parse fails the task and leaves the
previous configuration untouched — the host stays reachable. `backup: true`
keeps a timestamped copy of the file that was replaced. Both help with a
malformed configuration; neither helps with a well-formed one that binds an
address the host does not have, which is the failure mode
`## Failure modes` opens with. That asymmetry is why `SSH-19` is written as
a well-formedness requirement and nothing more.

The restart is a handler rather than an inline task, so it does not run at
the end of this role. It runs at the next handler flush after this role,
which is the one `roles/logging/tasks/main.yml` forces with
`meta: flush_handlers`: the firewall, emergency-access, fail2ban and
logging roles all run in between. `swap` does not — it runs after that
flush, against the restarted daemon.

## Implementation map

| Path | Realises |
|---|---|
| `roles/ssh_hardening/defaults/main.yml` | SSH-5, SSH-6, SSH-7, SSH-12, SSH-13, SSH-14, SSH-15, SSH-16, SSH-18 |
| `roles/ssh_hardening/tasks/main.yml` | SSH-1, SSH-2, SSH-3, SSH-4, SSH-5, SSH-6, SSH-7, SSH-8, SSH-9, SSH-10, SSH-11, SSH-12, SSH-13, SSH-14, SSH-15, SSH-16, SSH-17, SSH-18, SSH-19 |
| `roles/ssh_hardening/templates/sshd_config.j2` | SSH-1, SSH-2, SSH-3, SSH-4, SSH-5, SSH-6, SSH-7, SSH-8, SSH-9, SSH-10, SSH-11, SSH-12, SSH-13, SSH-14, SSH-15, SSH-16, SSH-18 |
| `roles/ssh_hardening/handlers/main.yml` | SSH-17, SSH-20 |
| `tests/unit/test_ssh_hardening.py` | SSH-1, SSH-2, SSH-3, SSH-4, SSH-5, SSH-6, SSH-7, SSH-8, SSH-9, SSH-10, SSH-11, SSH-12, SSH-13, SSH-14, SSH-15, SSH-16, SSH-18 |
| `tests/property/test_ssh_hardening_properties.py` | SSH-1, SSH-2, SSH-3, SSH-4, SSH-5, SSH-6, SSH-7, SSH-8, SSH-9, SSH-10, SSH-11, SSH-12, SSH-13, SSH-14, SSH-15, SSH-16, SSH-17, SSH-18, SSH-19 |
| `tests/property/test_ssh_interface_restriction_properties.py` | SSH-18, SSH-19 |
| `tests/property/test_playbook_behavior_properties.py` | SSH-17 |

Every requirement appears above, and every row was checked by grepping the
file rather than by reading intent. Three requirements have no citation in the
template, because none is a directive: `SSH-17` (its sites are the task's
`notify`, the handler, and the two property suites that check the
notify-and-handler pattern), `SSH-19` (its sites are the task's
`validate:` and the three tests that assert it is configured) and `SSH-20`
(its site is the handler, which restarts sshd; the
unit's enabled and running state comes from the base image). The
interface-restriction suite cites exactly two requirements — `SSH-18`, which
it exists for, and `SSH-19`, because it asserts the `/usr/sbin/sshd -t`
validation string against the task file.

`tests/integration/test_bootstrap_integration.py`,
`tests/integration/test_tailscale_integration.py` and
`tests/verify_bootstrap.yml` all exercise this role's output on a live host
and are named throughout `requirements.md`'s `**Verified:**` lines. The
playbook belongs to `VRFY` and its task names cite `SSH` IDs, except the
two blocks that check `SSH-20`, which cite it in a comment; the
integration modules belong to the testing spec and carry no `SSH-N`
citations.

`tests/verify_bootstrap.yml` asserts against a live `sshd -T` for twelve
requirements — `SSH-1`, `SSH-2`, `SSH-5`, `SSH-6`, `SSH-7`, `SSH-8`,
`SSH-9`, `SSH-10`, `SSH-11`, `SSH-12`, `SSH-13` and `SSH-18`, the last only
on a Tailscale-enabled host. The integration suite adds behavioural evidence
of a different kind for four: it attempts a root login and a password login
that must both be refused (`SSH-2`, `SSH-1`), bootstraps on a non-default
port and then connects on it (`SSH-13`), and reaches a narrowed host from a
separate tailnet peer over both address families (`SSH-18`). Its
`test_unknown_user_rejected` is consistent with `SSH-12` but does not
isolate it, since an account outside the group is also an account with no
key. The playbook also checks `SSH-20` live, through the unit's
`ActiveState` and `UnitFileState` rather than `sshd -T`. Nothing live
covers `SSH-3`, `SSH-4`, `SSH-14`, `SSH-15`, `SSH-16`, `SSH-17` or
`SSH-19`.

## Key decisions

**A group, not a list of users.** The superseded requirement this spec
replaces called for restricting sshd to two named accounts, and `AllowUsers`
is the directive that does that literally. The implementation uses
`AllowGroups` with a single group instead, and `SSH-12` is written to match
it, because the two differ in what happens *after* the bootstrap. A
purpose-specific deployment layered on this playbook needs to grant SSH
access to accounts this role has never heard of. With `AllowUsers` that
means editing this role's template or overriding a variable that must then
repeat every existing name, and the list has to be kept in agreement with
reality in a second place forever. With `AllowGroups` it means adding an
account to a group — a normal account-management operation, with no edit to
this role and no list to drift. The cost is one indirection: sshd now admits
whoever the group admits, so the group's membership becomes a security
boundary that `USR-13` and `USR-14` own and that this spec cannot see. That
is a real transfer of responsibility and it is accepted knowingly; it is
also why `SSH-12`'s `**Verified:**` line says plainly that nothing here
confirms the group exists.

**Post-quantum included, and why the list is not "elliptic curves only".** The
superseded requirement asked for modern elliptic curves only. The default
list is not that, and should not be: `sntrup761x25519-sha512` is a hybrid of
a lattice-based KEM and X25519, and `diffie-hellman-group16-sha512` and
`-group18-sha512` are finite-field Diffie-Hellman over fixed large MODP
groups. What the list actually expresses is a threat model rather than a
family of mathematics. Key exchange is uniquely retroactive — a recorded
session can be broken later — so the list includes an entry chosen to be
secure unless *both* of two unrelated problems fall. The list's order is not
a control: RFC 4253 §7.1 selects the first algorithm on the client's list
that the server also offers, so the client's order decides which entry a
session uses, and any entry is reachable by a client that prefers it. What
the server controls is membership, which is why `SSH-5` is stated as
membership. The two finite-field groups are a deliberate compatibility floor
for clients too old for curve25519. Order does not keep them from being
selected, so what makes them acceptable is their size: they are large
enough that the small-group attacks that motivated narrowing the list do not
apply. What is excluded, and why: anything SHA-1-based, for the collision
resistance the exchange's transcript hash depends on; the `group14` and
smaller MODP groups, whose 2048-bit-and-under moduli are within reach of
precomputation against a fixed, widely shared group; and the
NIST `ecdh-sha2-nistp*` curves, excluded not because they are broken but
because curve25519 achieves the same security with a rigid, verifiable
parameter derivation and constant-time implementations that are much harder
to get subtly wrong. The cipher and MAC lists follow the same shape:
`SSH-6` keeps only constructions that authenticate before acting on
plaintext, which excludes every CBC-mode cipher and the Encrypt-and-MAC
composition behind SSH's historical ciphertext-modification attacks, and
`SSH-7` keeps only the Encrypt-Then-MAC variants for the cases `SSH-6` has
already made unreachable.

**Binding to addresses, not to an interface.** sshd has no way to say
"listen on `tailscale0`" — `ListenAddress` takes an address, optionally with
a port, and nothing else. So the narrowing is expressed as two addresses
taken from facts `TS` publishes, which has a consequence worth stating: the
binding is only as current as the facts were at template-render time. A
tailnet address is stable in practice, because the control server assigns it
per node and reissues the same one, but it is not guaranteed by anything
this spec controls. If a node were re-registered and given a different
address, the deployed `sshd_config` would still name the old one and sshd
would fail to bind it on the next restart. Binding by interface name, were
it available, would survive that. The alternative available today —
listening on all interfaces and relying on the firewall to admit only the
tailnet interface — was not chosen: it leaves a listener on the public
address, so a firewall misconfiguration or a rule-ordering mistake exposes a
live sshd rather than nothing. The two controls are complementary and both are applied; this
is the one that makes the service absent rather than merely filtered.

**One conditional, two branches, one requirement.** `SSH-18` covers the
enabled and disabled cases together. They are not two independent policies:
the else-branch is the definition of "not narrowed", and it exists so that
the template always produces an explicit, complete pair of `ListenAddress`
lines rather than omitting them and inheriting whatever sshd's built-in
default would be. Specifying them separately would permit a future change
that satisfied each half and left some third state — a single-family
binding, or none at all — unexcluded. The condition also guards on both
Tailscale facts being *defined*, not merely on the flag, so a host where the
flag is truthy but the role never ran falls to the open branch instead of
failing the render on an undefined fact.

**Replacing the file rather than editing lines.** The alternative — a series
of `lineinfile` edits against Debian's shipped `sshd_config` — would be
gentler on a host with existing local customisation, and would leave the
`Include` line intact. It was not chosen because it cannot express absence:
a directive this spec does not mention would keep whatever value the image
shipped, and there would be no single artefact a reviewer could read to know
what sshd is configured to do. Deploying the whole file makes the template
and the effective configuration the same document. The cost is that any
local edit an operator makes to `/etc/ssh/sshd_config` is reverted on the
next run — which is deliberate for `INV-9`, and is also what makes the
break-glass interaction in `## Failure modes` a real one.

## Failure modes

- **`sshd -t` accepts an address the host cannot bind, so `SSH-19` cannot
  prevent the lockout `SSH-18` risks.** The deployment task's
  `validate:` hook runs sshd's own configuration parser against the
  candidate file before installing it, which catches a syntax error or an
  unknown directive. It does not attempt to bind anything: a file naming a
  `ListenAddress` that is syntactically valid but assigned to no interface
  on this host passes validation with a zero exit status. The file is then
  installed and the handler restarts sshd at the next handler flush after
  this role, which is the last task of the logging role — see the
  deferred-restart failure mode below. What happens next depends on how many
  of the configured addresses are unbindable, and the two cases behave very
  differently:
  - If **no** `ListenAddress` can be bound, sshd logs `Cannot bind any
    address.` and exits. systemd reports the restart as failed, the handler
    task fails, and the run fails with it — and the failure stops more than
    this handler. Measured, with ansible-core 2.20.3 on a play of the same
    shape: when the first handler at a flush point fails, the host is marked
    failed and **none of the remaining handlers runs**, the rest of the
    flushing role's tasks are abandoned, and so are every later role and the
    play's `post_tasks`. Neither `ansible.cfg` nor `site.yml` sets
    `force_handlers`. Because this role is listed before `firewall`, its
    handler is the one that runs first, so in this case `FW-19`'s reload
    never happens at all: the host is left with the daemon down, the
    *previous* ruleset still loaded, and the provider's console the only
    remaining way in. The narrowing this bullet used to describe as
    simultaneous does not occur — what occurs is worse in one respect and
    better in another, and an operator diagnosing it should not be looking
    for a new firewall rule.
  - If **at least one** address binds, sshd logs the individual bind
    failure, carries on, and serves on the addresses it did get. The restart
    succeeds, the handler succeeds, and the run reports success on a host
    listening on fewer addresses than `SSH-18` requires. This is the case in
    which `FW-19`'s handler does run — immediately after this one, since
    handlers run in role-definition order and `firewall` is listed next — so
    here the two narrowings do land close enough together to be hard to tell
    apart.

  `SSH-19` prevents neither, by construction: it parses, it does not bind.
  The entire protection is upstream: `TS-15` through `TS-21`
  establish that the interface exists, the backend is `Running`, and both
  addresses are assigned, and `TS-22` requires all of it to have completed
  before this role renders its template. `TS`'s own design records that its
  final connectivity check pings the host's own address and so proves less
  than it appears to. `TS-19` and `TS-20` do not make up for that: they
  refuse only an empty address, which `SSH-19` would refuse anyway. What
  this spec leans on is that the addresses `TS-17` and `TS-18` publish are
  the ones the client reports.
- **The restart is deferred, so the lockout lands long after this role
  has finished.** `SSH-17`'s handler fires at the next handler flush after
  this role — not the play's first, which is
  `roles/filesystem_hardening/tasks/main.yml`'s and runs before this role,
  and not the end of the play, but the one
  `roles/logging/tasks/main.yml` forces with `meta: flush_handlers` as its
  last task. So it is after the firewall, emergency-access, fail2ban and
  logging roles in their entirety, and before `swap`. On a host where the
  new configuration is one sshd cannot bind, this means the run appears to
  succeed through all of those roles and then loses the daemon well after
  the task that caused it. What happens to `FW-19`'s handler at that moment
  depends on which of the two cases below is in force, and it is not what
  an earlier revision of this bullet said; the cases spell it out. It also
  means the existing SSH session
  Ansible is running over survives — sshd's restart does not terminate
  established sessions — so the run is never cut off mid-flight and reports
  its result normally, whether that result is the handler failure of the
  no-address-bound case or the false success of the partial-bind case. In
  neither case does the loss show on the connection the run is using; it
  shows on the next new one.
- **A partial bind silently leaves a dual-stack host narrowed on one family
  only, and the verification play would not notice.** `SSH-18` renders a
  `ListenAddress` for each address family. sshd treats a bind failure as
  fatal only when *every* configured address fails; if the tailnet IPv4
  address binds and the IPv6 address does not — a stale fact, an address
  withdrawn by the control server, a tailnet interface that came up
  without IPv6 — sshd logs the one failure, starts, and serves IPv4 only.
  The handler succeeds, the run reports success, and nothing in the role or
  the play distinguishes that host from a correctly narrowed one.
  `verify_bootstrap.yml`'s `Verify SSH-18: SSH is restricted to Tailscale
  interface` does not close this: it asserts that `sshd -T` reports *a*
  `listenaddress` and does not report `listenaddress 0.0.0.0`, both of which
  an IPv4-only tailnet binding satisfies. This is `INV-4`'s "no separate, looser path for one family"
  failing in the other direction — not a hole, but a half-narrowing whose
  IPv6 half is simply absent, so an operator whose only route to the host is
  IPv6 is locked out while every check reports success. A check asserting an
  address of each family would catch it.
- **The break-glass script's edits are reverted by the next bootstrap
  run.** The emergency-access spec's script restores public reachability by
  deleting every `ListenAddress` line from `/etc/ssh/sshd_config` and
  inserting `0.0.0.0` and `::` after the `Port` line, then restarting sshd.
  That is an edit to the very file this role deploys from a template, so the
  next `make bootstrap` against that host re-renders it and puts the
  tailnet-only binding back — silently, as an ordinary `changed` result
  among many. An operator who used the break-glass path to recover a host,
  fixed the tailnet, and then re-ran the playbook would find that correct;
  an operator who used it and re-ran the playbook for an unrelated reason
  while the tailnet was still broken would be locked out again by their own
  remediation run. Nothing in either role warns about this. The script's
  `sed` anchors are also keyed to `^Port ${SSH_PORT}` and to
  `ListenAddress 0.0.0.0` / `ListenAddress ::` as literals, so it depends on
  `SSH-13`'s rendered port and on `SSH-18`'s else-branch defaults being
  exactly those values — a deployment that changed `ssh_listen_address_ipv4`
  to a specific public address would leave the script's idempotency check
  permanently unsatisfied.
- **`SSH-3`'s keyboard-interactive clause has no test coverage at all.**
  `ChallengeResponseAuthentication no` is the directive that stops PAM
  offering the manual account's password over the network, and it is the
  difference between `INV-2` holding and `INV-2` appearing to hold. No unit
  test, property test, verification play or integration test references it
  in any server-side form — not the directive, not its modern spelling
  `KbdInteractiveAuthentication` as something sshd is configured with, not
  the resolved value in `sshd -T` output. The one occurrence of that
  spelling anywhere in the suite is a *client* option:
  `tests/integration/test_bootstrap_integration.py` passes
  `-o KbdInteractiveAuthentication=no` to `ssh` in a fail2ban test, to stop
  the client falling back to another method so that sshd logs a publickey
  failure the jail can match. It constrains the client, asserts nothing
  about the server, and would behave identically against a host where the
  server directive had been deleted. Deleting the line would pass
  `make test-unit`, `make test-property` and `make spec-check` without a
  single failure, and the host would then accept the manual user's password
  from the network on a stack where `pam_unix` is present. This is the most
  consequential coverage gap in the spec.
- **The unit suite's fixture is a hand-written copy of the role defaults, so
  most "renders the configured value" assertions confirm the fixture.**
  `base_vars` in `tests/unit/test_ssh_hardening.py` restates every variable
  this role defines — the three algorithm lists, the port, the four session
  limits, the group name and the two fallback addresses — and the unit tests
  render the template from it. So an assertion such as `MaxAuthTries 3` or
  `Port 22` establishes that the template interpolates the variable, not
  that `roles/ssh_hardening/defaults/main.yml` holds that value. The clearest
  consequence is `sntrup761x25519-sha512`: the unit suite asserts it only
  against that fixture, and the two tests that
  do read the defaults file name only `curve25519` and the two finite-field
  groups — so **deleting the post-quantum algorithm from the role defaults
  fails nothing**. `SSH-6`, `SSH-7`, `SSH-12`, `SSH-13`, `SSH-14`, `SSH-15`,
  `SSH-16` and `SSH-18` are affected the same way, each to the extent that
  the property suite does or does not independently read the defaults file;
  every one of their `**Verified:**` notes says so. `tests/unit/conftest.py`
  carries a second copy of the same data in `default_ssh_vars`. This is the
  same inert-verification pattern recorded against the tailscale,
  user-accounts and swap specs; no test was changed.
- **Every algorithm-exclusion test is a denylist of specific strings, not an
  allowlist.** `test_no_weak_kex_algorithms`, `test_no_cbc_ciphers` and
  `test_no_non_etm_macs` assert that four, three and three named substrings
  respectively do not appear in the rendered configuration. They say nothing
  about what *does* appear. Adding `ecdsa-sha2-nistp256` to `ssh_ciphers`,
  or any weak key exchange algorithm not among the four named, would pass
  all three. The tests are worth keeping — they pin the specific regressions
  someone thought of — but they are not the "restricted to" guarantee
  `SSH-5`, `SSH-6` and `SSH-7` state, and no test in the repository compares
  the rendered list against the intended one as a set.
- **Two of the three session limits are asserted only for existence, not for
  value.** `test_property_8_ssh_session_security_configuration` parses the
  defaults file and asserts `ssh_max_auth_tries` is at most 6.
  `ssh_login_grace_time`,
  `ssh_client_alive_interval` and `ssh_client_alive_count_max` are checked
  only for the presence of their keys, so defaults of `600m`, `86400` and
  `999` would satisfy `SSH-15` and `SSH-16`'s tests while defeating their
  purpose entirely.
- **The SSH access group's name is held as a literal in two roles, with
  nothing keeping them in agreement.** `ssh_access_group` is defined once,
  in this role's defaults, as `ssh-users`. The `users` role does not define
  it: it creates the group and adds both accounts using
  `{{ ssh_access_group | default('ssh-users') }}`, an independently written
  copy of the same literal. Within `site.yml`'s single play the fallback is
  normally not reached, since a role's `defaults/` are loaded when the play
  is compiled and so are visible to the earlier `users` role as well. It
  becomes load-bearing the moment `roles/users` is consumed in a play that
  does not also include `roles/ssh_hardening` — which is exactly the case a
  purpose-specific repository layered on this bootstrap is likely to hit.
  Changing this role's default without changing that fallback then produces
  a host that creates one group and admits members of another: sshd starts
  cleanly, the firewall admits the traffic, and every login is refused. This
  was recorded against `USR-13` when the user-accounts spec was written and
  is repeated here because this spec is the other half of it.
- **Nothing in this spec's scope confirms the group has members.** `SSH-12`
  restricts login to `ssh-users`; `USR-13` creates it and `USR-14` populates
  it, and the user-accounts findings record that neither has test coverage
  of any kind in either default suite. The combination means the single
  condition on which every login depends — "the accounts that were given
  keys are in the group sshd admits" — is asserted nowhere outside the
  integration suite.
- **The role writes `Port` and `ListenAddress` into `sshd_config` and
  assumes sshd is not socket-activated.** Under systemd socket activation,
  the listening sockets are owned by a `.socket` unit and both directives in
  `sshd_config` are ignored; `SSH-13` and `SSH-18` would then be inert
  without any error, and `SSH-17`'s handler — which restarts `sshd`, not a
  socket unit — would not re-read them either. This bootstrap requires
  Debian 13 or newer and nothing anywhere in the repository mentions
  `ssh.socket`, checks for it, or disables it. The integration suite
  bootstraps with `ssh_port: 2222` and then successfully connects on that
  port, which is evidence that socket activation is not in effect for the
  image it uses, but that suite runs only under Incus and the image is one
  this project builds. Nothing establishes the same for an arbitrary
  provider image, and a future Debian that enables socket activation by
  default would break both requirements silently.
- **The deployed file supersedes `/etc/ssh/sshd_config.d/`, which is
  intended, and is invisible to an operator reading only the drop-in
  directory.** Because the template carries no `Include` line, a provider
  image's drop-in setting `PasswordAuthentication yes` has no effect after a
  bootstrap — correct, and the point of the design — but an operator who
  later adds a drop-in expecting it to be honoured will find it silently
  ignored, with the file still present on disk and apparently in force. No
  comment in the deployed file says so.
- **`backup: true` leaves the pre-hardening configuration on disk.** Each
  run that changes the file writes a timestamped copy of the previous one
  into `/etc/ssh/`. That is deliberate and useful for recovery, but it means
  a readable record of the host's earlier, weaker configuration accumulates
  next to the live one, and nothing prunes it.

## Interactions

**What this spec assumes of others:**

- `TS-17` and `TS-18` — on a Tailscale-enabled host, `tailscale_ipv4` and
  `tailscale_ipv6` are defined and non-empty when this role's template is
  rendered. `SSH-18` binds to exactly those two values and to nothing else,
  and its `is defined` guard is what turns a half-published pair into a
  fallback to the open branch rather than a failed render.
- `TS-19` and `TS-20` — neither address is the empty string. An empty fact
  renders an empty directive, which sshd rejects, so `SSH-19`'s validation
  would fail the deployment task; these two checks stop the run earlier,
  with a message that names the cause.
- `TS-22` — every Tailscale verification check has completed before this
  role runs. This is the requirement that makes `SSH-18`'s narrowing safe,
  and it is the only thing that does: nothing in this role can tell a good
  address from a bad one.
- `TS-1` — `tailscale_enabled` defaults to false, so `SSH-18`'s open branch
  is what an unconfigured deployment gets.
- `USR-13` — the group named by `ssh_access_group` exists on the host
  before sshd is restarted. `SSH-12` names it; it does not create it.
- `USR-14` — both bootstrap accounts are members of that group. Without
  this, `SSH-12` admits nobody.
- `USR-10` and `USR-12` — each account's `authorized_keys` file exists with
  a mode sshd will accept. `SSH-3` makes public keys the only way in; these
  are the keys.
- `PRJ` — `site.yml` orders the `tailscale` role ahead of this one and
  supplies the inventory that sets `ssh_port` and any algorithm or session
  overrides.
- `INV-4` and `FW-3` — on a Tailscale-disabled host, `SSH-18`'s open branch
  narrows nothing, and the only thing between sshd and the internet is the
  firewall's default-deny input policy (`FW-3`) plus whichever SSH branch
  that host's flags select. Which one matters: with port knocking at its
  default of enabled the branch is knock-gated, and `FW-13`'s open rule —
  reached only when knocking is disabled too — is not rendered at all.
  `FW-14` is what makes whichever rule is rendered name the same port
  `SSH-13` configured.

**What others may assume of this spec:**

- `FW-14` — `ssh_port` is the single source of the port number; the
  firewall's own `firewall_ssh_port` derives from it, so its SSH rules and
  this spec's `Port` directive agree by construction. `FW-10` may also
  assume that on a Tailscale-enabled host sshd is bound to the tailnet
  addresses only, so its tailnet-interface rule and this binding are two
  independent restrictions on the same path rather than one restriction
  stated twice — `FW-10` filters the packets, `SSH-18` removes the
  listener, and neither is a substitute for the other.
- The emergency-access spec — the deployed `sshd_config` contains a `Port`
  line rendered from `ssh_port` and exactly two `ListenAddress` lines, which
  is the structure its break-glass script's `sed` edits depend on. It may
  also assume that restoring `0.0.0.0` and `::` produces a reachable host,
  since those are `SSH-18`'s own else-branch values. It must not assume its
  edits survive a later bootstrap run; see `## Failure modes`.
  `specs/emergency-access/design.md` cites `SSH-13` for the port anchor and
  `SSH-18` for the address pair.
- `F2B` — `SSH-14` caps authentication attempts within one connection,
  which is what forces a brute-force attempt to open new connections and
  therefore what makes a connection-counting jail able to see it at all.
  That spec is now written and cites `SSH-14` in return, for this reason
  and also because `SSH-14`'s own
  `Disconnecting: Too many authentication failures` is one of the lines its
  filter counts. It records two further inputs from this spec, and they
  have different causes: `SSH-5`, `SSH-6` and `SSH-7` feed its counter with
  algorithm-negotiation refusals, which a client on old software produces,
  and `SSH-15` feeds it with grace-time expiries, which a slow or stalled
  connection produces regardless of the client's age. Neither is an
  authentication attempt, and both count.
- `PAM` and `LOGIN` — `UsePAM yes` means sshd consults the PAM stack those
  specs harden for account and session management. `SSH-3` closes the
  keyboard-interactive path, so PAM's *authentication* phase is not reachable
  from the network; its account, session and lockout phases still are.
- `VRFY` — what a completed bootstrap guarantees is a property of the
  **deployed file**, not of a running daemon, and the distinction is the
  whole of what `VRFY` is for. A completed run establishes that the template
  rendered, that `SSH-19`'s `sshd -t` parsed the result, that it was
  installed at `/etc/ssh/sshd_config` owned by root with mode `0644`, and
  that a restart was requested and systemd did not report it as failed. On
  that basis every directive the file carries says what this spec says it
  says: `SSH-1`, `SSH-2`, `SSH-3`, `SSH-4`, `SSH-5`, `SSH-6`, `SSH-7`,
  `SSH-8`, `SSH-9`, `SSH-10`, `SSH-11`, `SSH-12`, `SSH-13`, `SSH-14`,
  `SSH-15`, `SSH-16`, and `SSH-18` on whichever branch its condition
  selected.

  What a completed run does **not** establish is that the daemon is serving
  that configuration. A restart in which sshd could bind none of its
  addresses does fail the run — but one in which it bound some and not
  others succeeds, silently, and the run cannot tell the two apart; see
  `## Failure modes`. Nor does a completed run say anything about the
  daemon's state at the later moment `VRFY` actually runs.

  That is what makes the twelve `sshd -T` assertions worth *more* than this
  wider list rather than a subset of it: they can only answer at all if the
  daemon is up and serving, so they are the only thing in the project that
  distinguishes a deployed file from a live configuration — which no part of
  this spec can do for itself. The five requirements in the wider list and
  not in the twelve — `SSH-3`, `SSH-4`, `SSH-14`, `SSH-15` and `SSH-16` —
  are where `VRFY` is taking the deployed file's word for the daemon's
  behaviour, and `SSH-3`'s keyboard-interactive clause is the one place
  where that word is backed by no test of any kind. A `VRFY` spec that
  wanted to close the gaps would add five `sshd -T` assertions for those,
  and would assert an address of each family rather than the mere absence of
  `0.0.0.0`.
- The testing spec — the integration suite bootstraps with a non-default
  `ssh_port` and then connects on it, and its tailnet tests are the only
  place in the project where a real `ListenAddress` binding is exercised.
  Every claim in `requirements.md` that rests on a running daemon rather
  than on rendered text depends on that suite, which runs only under Incus.
