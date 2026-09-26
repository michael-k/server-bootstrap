# Verification — Requirements

**Prefix:** `VRFY`

## Purpose

This spec covers the one playbook in this project that changes nothing: run
against a host every other spec has already bootstrapped, it reads the
running configuration back — `sshd -T`, `nft list ruleset`,
`fail2ban-client status`, a handful of files under `/etc` — and asserts that
what it reads is what the feature specs required. It owns no policy of its
own. Every assertion it makes belongs to a feature spec, cited by that
spec's own requirement ID, and this spec's requirements are only about the
mechanism the assertions run inside: that the run is read-only, that it can
see the variables it needs despite declaring no `roles:`, that every check
reports explicitly rather than by silence, that a failure names the
requirement that broke, that a disabled feature's checks are skipped rather
than failed, and that any failure anywhere ends the run non-zero.

Before this spec existed, the playbook's 44 checks were also each restated
as a `Requirement 14.N` — a second, parallel copy of requirements that
already lived in their owning spec. The two copies drifted, because nothing
kept them in agreement: a feature spec could gain, lose or reword a
requirement with no corresponding edit here. This spec dissolves that
duplication. A verification block cites the ID of the requirement it
verifies directly; it does not restate the requirement, and it is not itself
a second source of what the requirement says.

## Scope

### In scope

- That the playbook makes no configuration change to the host it runs
  against.
- That the playbook can resolve every variable it needs — including a role's
  own default — without declaring `roles:`, and does so by bringing each one
  into scope explicitly rather than relying on Ansible's normal role-loading
  path, which this play does not use.
- That every check reports a pass or a fail explicitly, with a message in
  each direction.
- That a failing check's task name identifies the requirement it verifies,
  so a run's output says what broke without a reader cross-referencing a
  line number against a spec.
- That a check for a feature an inventory has left disabled is skipped
  rather than failed.
- That the run's exit code is non-zero if any check failed.

### Out of scope

- What each check actually verifies. Every assertion belongs to the feature
  spec whose ID it cites; this spec does not restate, duplicate or second-
  guess a feature requirement's content. `## Interactions` names which specs
  this playbook cites and what it assumes about them.
- Reaching a knock-gated host in the first place, *today* — but not the
  ownership of that gap, which is this spec's. This playbook is a single
  `hosts: all` play with no knock play of its own, unlike `site.yml`, which
  `KNOCK-11` requires to open one first; `specs/port-knocking/requirements.md`
  and `specs/port-knocking/design.md` both say this belongs to `VRFY`, and
  they are right — the missing play is a property of this playbook, not a
  precondition either of them owes it. It is recorded as an unresolved gap
  in `design.md`'s `## Failure modes` rather than closed in this pass, which
  remaps citations and does not add a knock play. A Tailscale-narrowed host
  needs no equivalent fix: whoever runs `make verify` against one must
  already be connecting from inside the tailnet, which is `SSH-18`'s and
  `TS`'s narrowing working as intended, not a gap in this playbook.
- A closing summary of the run. The playbook's last block prints a fixed
  "All verification tests passed successfully!" message unconditionally —
  not a per-check tally, and not something computed from
  `verification_results`, `tests_passed`, `tests_failed` or
  `tests_skipped`, which the play declares in `vars:` and never touches
  again. It states nothing that VRFY-6's exit-code behaviour has not
  already established by the time it runs: this block only executes at all
  once every check before it has passed, because a failed
  `ansible.builtin.assert` stops the host's run right there with no
  `ignore_errors` to carry it forward, so the message is reachable exactly
  when it is true and unreachable otherwise. That makes it decorative output
  rather than a check, and this spec deliberately holds no requirement for
  it — not `VRFY-3`, which is about a per-check pass/fail message, and not a
  new `VRFY-7`, which would have nothing to require beyond "print something
  friendly at the end." A requirement with no failure mode to guard against
  is not a requirement.
- Fixing a check that is wrong, missing, or resting on a variable this play
  cannot see. This spec states what a check must do; a check that does not
  is a defect in the file this spec maps, not a requirement this spec lacks.
- Any unit, property or integration test of a feature role. This playbook is
  the only suite that reads a live host supplied by an inventory; the testing
  spec's unit and property tiers read templates and task files instead, which
  `specs/fail2ban/design.md` and others record as a real difference in what
  is actually confirmed. Its integration tier does read a live, bootstrapped
  host — one it launched itself under Incus — and runs this playbook against
  that host as one of its own tests; `specs/testing/design.md`'s
  `## Interactions` records the crossing point.

## Security invariants

**Upholds:** INV-9 — verification is how a re-run is shown not to have
weakened anything.

Every other spec's claim on `INV-9` is a claim about what the bootstrap
playbook does: a template that converges, a membership that only grows, a
mode reasserted on every run. None of that is self-evidently true from
reading a role's source alone — a converging template can still render the
wrong thing, a membership grant can still be missing the account it was
meant for. This spec is what closes that gap for a host that has actually
been bootstrapped: it reads the running system back and asserts that the
state every other spec promises is the state that is actually there, so
"a re-run never weakens" is a claim checked against a host rather than
merely a property argued about a template. `VRFY-1`'s read-only guarantee is
what makes that safe to run repeatedly — a verification pass that changed
the host while checking it would confound the very re-run it exists to
confirm didn't weaken anything.

**Allowances claimed:** none. This spec opens nothing, narrows nothing and
writes nothing; every requirement here is about how a read is reported, not
about what is read or changed.

## Requirements

### VRFY-1 — The playbook runs read-only against a bootstrapped host

THE Bootstrap SHALL make no configuration change to a host while verifying
it.

**Why:** a verification pass that changed the host while checking it would
no longer be evidence about the state the bootstrap playbook left behind —
it would be evidence about a state this playbook itself just created, on top
of whatever else was already unwritten. A check that runs safely and
repeatedly against a production host, before and after every other change,
is only possible if reading the state costs nothing.
**Verified:** measured directly against the file. Every one of the 38
`ansible.builtin.command` tasks carries `changed_when: false`. The other
modules used are `ansible.builtin.systemd` (queried with no `state:`
argument, which only reads unit status), `ansible.builtin.stat`,
`ansible.builtin.slurp`, `ansible.builtin.set_fact`,
`ansible.builtin.include_vars`, `ansible.builtin.debug` and
`ansible.builtin.assert` — none of which writes to the host. No module that
creates, modifies or removes a file, package, service state or user appears
anywhere in the file. `become: true` is set on the play, but every task it
enables is one of the read-only modules above; nothing here uses the
elevated access to change anything. No test in either suite runs this
playbook against a host and diffs the result — the guarantee rests on the
absence of a writing module, confirmed by reading the file rather than by
observing a run leave a host unchanged.

### VRFY-2 — Externally supplied variables this playbook needs are brought into scope explicitly

Because this play declares no `roles:` keyword, `roles/*/defaults/main.yml`
is not in its variable scope, so a role default has to come from the
inventory, the command line, or this file itself if it is to resolve at
all. THE Bootstrap SHALL
bring every variable this playbook references that is not defined in the
play's own `vars:`, not `register:`ed by an earlier task in this file, and
not an Ansible fact, into scope explicitly — by `include_vars` under an
appropriate namespace, or by guarding the reference with `| default(...)` —
rather than relying on an inventory happening to set it. A role's own
default is one instance of such a variable; a bare inventory-level name with
no role default of its own, read directly by this playbook, is another, and
this requirement covers both alike.

**Why:** a bare reference to an externally supplied variable in a play with
no `roles:` and no inventory obligation of its own resolves only if the
inventory happens to set it; where it does not, Ansible fails the task with
`'<name>' is undefined`, not with whatever default a role's author or this
playbook's own author had in mind. Commit `4fbdee7` fixed exactly this
failure once already — the play aborted at "Verify login.defs hardening"
because `login_policy_umask`, `login_policy_retries` and
`login_policy_timeout` are `users` role defaults this play never loaded —
and the fix must not regress by a second variable making the same mistake,
whether or not that second variable is itself a role default. `include_vars`
under a namespace, rather than a bare `include_vars` of the role's defaults
file, is what keeps the role-default case of the fix from itself becoming
the regression it prevents: an unnamespaced include would inject
`login_policy_umask` directly into the play's variable scope, at the same
precedence Ansible gives `include_vars`, which outranks an inventory's
`group_vars` value for the same name — so an inventory that set
`login_policy_umask` to override the role's default would be silently
overridden right back by this playbook's own read of the default.
Namespacing the include under `users_role_defaults` and referencing
`users_role_defaults.login_policy_umask` only inside a `| default(...)`
guard keeps an inventory value in first place, exactly as `INV-9`'s
convergence argument requires: this playbook must confirm what the bootstrap
run actually set, not silently substitute a packaged or hardcoded default
for it. A variable with no role default at all needs the same discipline for
a narrower reason: nothing brings it into scope on its own, ever, so a bare
reference to it is undefined on every host whose inventory does not happen
to set it — which is precisely `port_knocking_sequence`'s case below, and
precisely why this requirement is worded around "externally supplied"
rather than "role default".
**Verified:** the play's first task, tagged `always`, loads
`roles/users/defaults/main.yml` under the name `users_role_defaults`; it is
the only `include_vars` task in the file. Three requirements reference
`users` role defaults this way — `login_policy_umask`,
`login_policy_retries` and `login_policy_timeout` in the login.defs check,
and `pam_faillock_deny` in the faillock check — each as
`<inventory_name> | default(users_role_defaults.<name>)`.
`test_verification_playbook_resolves_role_default_variables` checks the
role-default half of this requirement mechanically: it collects every key
defined in any `roles/*/defaults/main.yml`, subtracts the names in the
play's own `vars:`, the keys of every `inventory/**/*.example` file, and the
namespace (not the contents) of every `include_vars`, and fails if a name
that is left over appears in the playbook's text with no `.` before it and
no `| default(` after it. **No test checks the other half.** Nothing in
either suite enumerates every variable this playbook references that is
*not* a role default and confirms each is either guarded or brought into
scope; the check that exists is scoped to `roles/*/defaults/main.yml` keys
by construction, so a bare inventory-level name with no role default at all
— this requirement's other case — is invisible to it regardless of whether
it is guarded correctly.

**This requirement is violated in the very file it governs, right now.**
`port_knocking_sequence` is referenced three times, at
`port_knocking_sequence[0]`, `[1]` and `[2]`, with no `| default(...)` guard
and no `include_vars` bringing it into scope — reproducing the `4fbdee7` bug
class this requirement exists to prevent, on a variable that is not even the
shape `4fbdee7` fixed. It is not defined in the play's `vars:`, not
`register:`ed anywhere in this file, not an Ansible fact, and not a role
default either: no `roles/*/defaults/main.yml` defines a key named
`port_knocking_sequence`. The firewall role defines
`firewall_port_knocking_sequence: "{{ port_knocking_sequence |
default([7000, 8500, 9100]) }}"`, which reads the same bare name — but that
`| default(...)` lives inside the *role's* default value, one indirection
away from this playbook, and is invisible to it. Being outside the role-
default shape does not exempt it from this requirement, which is written to
cover exactly this case; it only exempts it from the one test that checks
the role-default case, and does so for the reason stated above:
`test_verification_playbook_resolves_role_default_variables`'s
`role_defaults` dictionary is built from the *keys* of
`roles/*/defaults/main.yml` (`firewall_port_knocking_sequence`, among
others), never from the bare inventory-level names those defaults'
`| default(...)` expressions read. `port_knocking_sequence` is exactly such
a name, and no test in either suite checks for it. Resolved against the
shipped example inventory with the real resolver
(`ansible-inventory -i inventory/group_vars/all.yml.example --host testhost`),
`port_knocking_sequence` is absent and `port_knocking_enabled` is absent
too — so on a host with Tailscale disabled, the block's `when:` evaluates
true, `port_knocking_sequence[0]` is undefined, and the play aborts there
with no `ignore_errors` to catch it. This is block `#32` of the 55
verification blocks; the 23 after it never run. `design.md`'s
`## Failure modes` records
the same fact from the mechanism's side; it is not fixed here, per this
task's own instruction not to fix the playbook.

### VRFY-3 — Every check reports pass or fail explicitly

THE Bootstrap SHALL give every verification check both a message identifying
what is wrong if its condition fails and a message confirming what held if
it passes.

**Why:** a check that only fails loudly and passes silently leaves a
successful run indistinguishable from a run in which the check itself never
executed — Ansible's own `assert` module reports a task as `ok` either way,
with nothing in the default output naming which security property that `ok`
stood for. Explicit messages in both directions are what turn 55 pass/fail
results into a report an operator can read without opening this file.
**Verified:** all 55 `ansible.builtin.assert` tasks in the file carry a
`fail_msg` and a `success_msg`, matching the count of asserts exactly — a
one-to-one correspondence measured by counting each string's occurrences
independently. `test_verification_tests_use_proper_assertions` asserts that
`ansible.builtin.assert:`, `fail_msg:`, `success_msg:` and `that:` each
appear somewhere in the file — a whole-file substring check that would not
notice a fifty-sixth assert added with no message, or a message moved to
the wrong assert, since it does not confirm the messages sit on the same
task as any particular assert.

### VRFY-4 — A failure names the requirement it verifies

WHERE a verification block checks a feature requirement, THE Bootstrap
SHALL name that requirement's ID in the block's task name, so that a
failure's own name — the first thing Ansible prints for it — identifies
what broke without a reader consulting this file's line numbers against a
spec.

**Why:** the block this replaces named a `Requirement 14.N` instead, a
number with no meaning outside this one file and no route back to the
feature spec that actually states what failed. Citing the owning
requirement's ID directly is what makes a CI failure or an operator's
terminal output self-describing — `Verify SSH-1: SSHD password
authentication is disabled` names both what broke and where to read why it
matters, where `Test 14.5` named neither.
**Verified:** 54 of the file's 55 verification blocks name at least one
requirement ID — several name more than one, where a single assert checks
conditions that belong to different requirements of the same feature (for
example `Verify SUDO-11, SUDO-12, SUDO-13: wheel group and su restriction`).
One block names none: the closing "Display verification summary" block is
this spec's own reporting, not a check of a feature requirement, so it has
none to cite. The checks of sshd's own service state (`ActiveState`,
`UnitFileState`) are named `Verify SSH-20: sshd service is running` and
`Verify SSH-20: sshd service is enabled`, citing `SSH-20` directly rather
than in a comment above each block, which this requirement does not count.
Every ID cited was checked against the `### ` headings of its spec's
`requirements.md` to confirm it exists.
`test_verification_playbook_covers_all_requirements` asserts, over the
renamed file, that at least 40 blocks cite at least one requirement ID and
that at least 40 distinct IDs are cited in total — replacing its previous
form, which counted blocks titled `Test 14.N` and asserted the numbering
ran from 1 to at least 40. That check is retired along with the numbering
it measured: a per-component ID scheme has no single sequence to start at 1
or reach 40, so the same assertion would be false of a healthy file under
the new convention. No test confirms which block is the one naming none;
that is asserted only in this document.

### VRFY-5 — A disabled feature's checks are skipped, not failed

WHERE a feature is disabled by its own configuration, THE Bootstrap SHALL
skip the verification block for that feature by a `when:` condition on the
block itself, rather than let its assertion run and fail.

**Why:** Tailscale, port knocking, zram, disk swap, a configured hostname
and — per `F2B-4` — the fail2ban SSH jail are each optional or configurably
disabled, and a host that never enabled one has nothing there for a check
to find — asserting anyway would report every unconfigured host as broken,
which is indistinguishable in the run's output from a host that enabled the
feature and failed to configure it correctly. Skipping is also what keeps
this playbook usable against the fleet as a whole: a single `hosts: all`
run against hosts in different configurations needs each host's checks to
match its own configuration, not the union of every configuration this
project supports.
**Verified:** fourteen of the file's 23 `when:` conditions sit on a block
itself, gating the assert along with everything above it: four on
`tailscale_enabled`, two on `not (tailscale_enabled) and
port_knocking_enabled` together, one on `system_hostname` being defined and
non-empty, four on `zram_enabled`, and three on `disk_swap_size` being
defined and non-empty (one of the four `zram_enabled` guards is combined
with a `disk_swap_size` check, for the block comparing the two swap
priorities). The other nine `when:` conditions in the file are not this
requirement's mechanism and do something narrower: six guard only a
`slurp` read of a file that may not exist, while the block's own assert
still runs unconditionally and fails on that file's absence rather than
skipping — `sudo_security_file`, `manual_sudo_file`, `ansible_sudo_file`,
`securetty_file`, `shell_timeout_file` and `limits_file` among them; the
remaining three choose whether to also query `systemd-timesyncd` after
`chrony` has already reported active, enabled or synchronized, which is a
fallback within one always-running check rather than a skip of it.
`test_verification_tests_handle_conditional_features` asserts that
`when:`, `tailscale_enabled`, `zram_enabled`, `disk_swap_size` and
`system_hostname` each appear somewhere in the file — a whole-file
substring check that does not distinguish a block-level skip from either of
the two narrower patterns above, and would not notice one of the four
feature guards moving from a block onto a single sub-task within it.

**This requirement is violated in the very file it governs, the same way
`VRFY-2` is.** `Verify F2B-4: fail2ban is monitoring SSHD` carries no
`when:` of any kind — the same as the other two fail2ban blocks, but the
only one of the three whose assertion actually depends on the jail
existing. `F2B-4`'s own SHALL states that
`fail2ban_ssh_enabled: false` is a valid, working configuration that leaves
"fail2ban supervising no jail at all," and `roles/fail2ban/defaults/main.yml`
defines that variable, defaulting to `true`. On a host where it is set
false, `fail2ban-client status` lists no jail, `fail2ban_status.stdout is
search('sshd')` is false, and this block's assert **fails** — on a
correctly configured host, for the one feature in this list whose disabled
state this playbook does not skip. The other two fail2ban blocks,
`Verify F2B-13` and `Verify F2B-14`, do not need the same guard: both check
the unit's own `ActiveState`/`UnitFileState`, which stay `active`/`enabled`
regardless of whether the flag is on, so nothing about them is disabled by
it. `specs/fail2ban/design.md`'s own `## Failure modes` already states the
same fact from the fail2ban side — "F2B-4's off position does not produce a
dormant jail... measured, it produces a fail2ban server with no jail at all,
which is still enabled and still active" — this requirement is what
translates that into a concrete instance of its own violation. Not fixed
here, for the same reason `VRFY-2`'s violation is not: this pass remaps
citations and does not change what any block checks or when it runs.

### VRFY-6 — A failure ends the run non-zero

THE Bootstrap SHALL exit with a non-zero status if any verification check
fails.

**Why:** a verification pass an operator or a CI job cannot script against
is one somebody has to read in full every time, which is exactly the class
of check that stops being read once it has passed a few times in a row. A
non-zero exit on failure is what lets `make verify` gate a deploy or a merge
mechanically, and it is also `INV-9`'s claim made checkable by a machine
rather than only by a person: a re-run that weakened something fails the
gate, not just the log.
**Verified:** measured, and stated as an absence rather than a mechanism,
because that is what it is. No task in the file sets `ignore_errors`,
`check_mode`, or `any_errors_fatal`, and no play-level `force_handlers` is
set either — all four are absent by grep count of zero. With none of them
present, a failed `ansible.builtin.assert` follows Ansible's own default
behaviour: the task fails, the host is marked failed, no later task runs
against it, and `ansible-playbook` exits non-zero once the run ends. This
requirement therefore rests entirely on the file continuing to add none of
those overrides, not on any mechanism this file adds itself. No unit or
property test runs this playbook end to end and inspects the process's exit
code — doing so needs a live or containerized target, which is outside what
`make test-unit` and `make test-property` reach. The integration tier does:
`TestBootstrapVerification::test_verify_playbook_passes` runs this playbook
against a virtual machine it bootstrapped and asserts the process returned
zero and its recap reported `failed=0`. That is an observation of the
*passing* direction only — no test has ever seen this playbook exit non-zero
on a failed check — so the failing direction, which is what this requirement
is about, remains confirmed by the absence of a defeating directive rather
than by an observed run.
