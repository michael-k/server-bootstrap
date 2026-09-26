# Verification — Design

## Approach

The whole of this spec is one file, `tests/verify_bootstrap.yml`: a single
play, `hosts: all`, with one preliminary task and 55 independent checks.
Each check is a `block:` containing one or more read-only gather tasks and
exactly one `ansible.builtin.assert` — with one exception, `Verify PAM-2,
PAM-5, PAM-6, PAM-7, PAM-8, PAM-9: faillock configuration`, whose block
contains two asserts, one for `faillock.conf`'s settings and one for the
PAM profiles and their ordering in `common-auth`. There is no shared
harness beyond the play's `vars:` block, which exists but is unused by any
check — `tests_passed`, `tests_failed` and `tests_skipped` are declared and
never incremented, a leftover from a design this file does not implement.
Nothing here counts a per-check result; the report an operator gets is
Ansible's own per-task output, `fail_msg` and `success_msg` included, plus
`ansible-playbook`'s ordinary non-zero exit on the first failure.

The play declares no `roles:` keyword, which is deliberate and load-bearing:
this playbook checks a host that was bootstrapped by roles, not one it
applies itself, so pulling those roles in would apply their tasks rather
than merely read their defaults. The cost of that choice is that
`roles/*/defaults/main.yml` is simply not in scope for this play the way it
would be inside `site.yml`, and every reference to a role default — or to
any other variable this playbook does not itself supply — has to be
resolved some other way — `VRFY-2` is the whole of what this design does
about that, and `## Failure modes` below records where it currently does
not do enough.

Every check asserts against the *running system* — `sshd -T`, `nft list
ruleset`, a live `systemd` unit's `ActiveState`, a file's actual content
read with `slurp` — never against a template or a task file. That is the
one property this playbook has that no unit or property test in the
`testing` spec shares, and it is also this playbook's whole reason to
exist: a template that renders correctly and a role that reports `changed:
false` on a second run are both claims about what Ansible *believes* it did,
and this playbook is the one place any of that is checked against what the
host actually has. The cost is that every check here needs a live target —
`make verify` runs against an inventory, not against a fixture — so none of
it runs in `make test-unit` or `make test-property`. A broken check is
caught either by whoever next runs `make verify` against a real host, or by
`make test-integration`, whose
`TestBootstrapVerification::test_verify_playbook_passes` runs this playbook
against a machine that suite bootstrapped and fails if it does not exit
zero. Neither happens on a controller without Incus unless somebody runs
`make verify` by hand.

## Implementation map

| Path | Realises |
|---|---|
| `tests/verify_bootstrap.yml` | VRFY-1, VRFY-2, VRFY-3, VRFY-4, VRFY-5, VRFY-6 |
| `tests/property/test_verification_properties.py` | VRFY-3, VRFY-4, VRFY-5 |

`VRFY-2`'s own violation — the `port_knocking_sequence` reference with no
guard — lives in the same file this row cites; it is not a separate site.

## Key decisions

**Asserting against the running system, not the templates it came from.**
The alternative would have been to fold these 55 checks into the unit or
property suites, rendering each role's template with a fixed variable set
and asserting on the rendered text — which is exactly what most of those
suites already do. That alternative is cheaper to run and needs no target,
but it can only ever confirm that a template renders what its own author
expected; `specs/fail2ban/design.md`'s closing note that "the whole spec is
verified by reading text" is the general statement of what that leaves
unchecked; `specs/ssh-hardening/requirements.md`'s `SSH-3` finding — that
the keyboard-interactive half of public-key-only authentication has "no
test coverage at all, in the template or on a live host" — is a concrete
instance of it. This playbook is what closes that gap, at the cost
of needing a target to run against at all. It is not a substitute for the
template-level suites; it is the one place a rendered file, a running
daemon and an actual kernel ruleset are read back rather than assumed.

**The `include_vars` namespacing.** The naive fix for a role default this
play cannot see would be an unnamespaced `include_vars` of the role's
defaults file, injecting `login_policy_umask` and its siblings directly
into the play's variables. That would work for a host whose inventory never
overrides those names, and would silently break for one that does:
`include_vars` outranks a `group_vars`-level inventory value at the same
variable name, so a deployment that raised `login_policy_umask` to harden
it further would have this playbook read back the *packaged* default and
report success against a value the host was never actually running.
Loading the file under a name — `users_role_defaults` — and referencing
`users_role_defaults.login_policy_umask` only inside a `| default(...)`
fallback keeps the include from ever winning against an inventory value: an
inventory-set `login_policy_umask` is resolved first, and the namespaced
default is consulted only when nothing else supplied one. This is the same
shape `VRFY-2` describes in the abstract and the same fix `4fbdee7`'s commit
message applies; the reason it is recorded here rather than only in that
commit is that the *pattern* — namespace, then `| default(...)`, never a
bare include — is what future checks referencing a new role default need to
repeat, and a reader who only sees the working case has no way to tell the
namespacing was the load-bearing part of the fix rather than an incidental
style choice.

## Failure modes

- **The `include_vars` fix has not been applied uniformly, and this file
  currently reproduces the bug it fixed.** `VRFY-2`'s own text states the
  violation in full: `port_knocking_sequence[0]`, `[1]` and `[2]` are
  referenced with no `| default(...)` and brought into scope by nothing,
  and on the shipped example inventory — Tailscale disabled,
  `port_knocking_enabled` and `port_knocking_sequence` both absent — the
  guard on that block evaluates true and the play aborts there. Block `#32`
  of 55, `Verify KNOCK-4, KNOCK-5, KNOCK-6: port knocking sequence ports in
  NFTables`, is where it happens; the 23 blocks after it never run on the
  configuration this project ships as its own example. This is not a new
  failure mode: commit `4fbdee7`'s own message describes the identical
  shape once already, at a different variable — "every run aborted at
  'Verify login.defs hardening' with `'<name>' is undefined`. 50 of 55
  verification blocks ran; the last 5 never did." The mechanism that
  recurred is that a role's default is written as `{{ bare_name |
  default(...) }}`, which resolves the *role's* variable but leaves the
  *bare* name this playbook reads directly just as undefined as before.
  `test_verification_playbook_resolves_role_default_variables` cannot catch
  this shape by construction: it builds its set of names to check from the
  keys `roles/*/defaults/main.yml` actually defines — `firewall_port_knocking_sequence`,
  not `port_knocking_sequence` — so a bare inventory-level name that only
  ever appears on the right-hand side of another role default's own
  `| default(...)` is invisible to it. Fixing the test to also collect
  those right-hand-side names, or fixing the playbook to guard the
  reference, are both changes to files outside what this task edits; this
  entry records the gap rather than closing it.

- **This playbook cannot reach a knock-gated or Tailscale-narrowed host on
  its own.** `site.yml` opens with a `connection: local` knock play before
  its main play, exactly because `KNOCK-11` requires a host it has already
  closed to be reachable at all. `tests/verify_bootstrap.yml` is a single
  `hosts: all` play with no such play in front of it. On a host where SSH is
  knock-gated, `make verify` fails `UNREACHABLE` before its first task —
  including the `include_vars` task `VRFY-2` depends on — runs at all. On a
  Tailscale-narrowed host, whoever runs `make verify` must already be
  connecting from inside the tailnet, which is `TS`'s and `SSH-18`'s
  narrowing working as intended rather than a defect, but it does mean this
  playbook offers no path of its own onto such a host. The knock-gated case
  is a gap this spec owns and has not closed in this pass;
  `specs/port-knocking/requirements.md` names the same gap from its own side
  and agrees that `VRFY` is where it belongs. The Tailscale case is not the
  same kind of gap — no play this spec could add would substitute for
  actually being on the tailnet — so there is nothing to close there, only
  the operational fact to record.

- **Two checks establish less than a reader would assume.** `Verify F2B-14:
  fail2ban service is active` and `Verify F2B-13: fail2ban service is
  enabled` both pass on a host with `fail2ban_ssh_enabled` false — measured,
  and recorded from the fail2ban side in `specs/fail2ban/design.md`: that
  configuration produces a running, enabled fail2ban server supervising no
  jail at all. Only the third fail2ban check, `Verify F2B-4: fail2ban is
  monitoring SSHD`, which greps `fail2ban-client status` for `sshd`, can
  tell the two states apart. Likewise `Verify FW-18: NFTables service is
  active` reads `ActiveState`, and the packaged `nftables.service` is
  `Type=oneshot` with `RemainAfterExit=yes` — `active` records that the last
  load exited zero, not that the rules it loaded are still in the kernel.
  `specs/firewall/design.md`'s `## Interactions` names `FW-3`, `FW-4`,
  `FW-6` and `FW-7` as the four checks in this playbook that read
  `nft list ruleset` itself and are therefore worth more than the
  service-state check beside them.

- **`Verify F2B-4: fail2ban is monitoring SSHD` has no `when:` guard, and
  `VRFY-5` requires one.** `F2B-4`'s SHALL makes `fail2ban_ssh_enabled:
  false` a valid configuration, not an error: fail2ban runs, is enabled, is
  active, and supervises no jail at all. On such a host `fail2ban-client
  status` never mentions `sshd`, so this block's assert fails — not because
  the host is misconfigured, but because a correctly configured, disabled
  feature has no `when:` telling this block to skip it. `VRFY-5`'s own text
  states the violation in the same shape `VRFY-2` states its own; it is not
  fixed here for the same reason.

- **The port-knocking checks confirm less than their names suggest, in two
  different ways.** `Verify KNOCK-3: port knocking sets exist in NFTables`
  asserts `knock4_stage1`, `knock6_stage1`, `knock4_passed` and
  `knock6_passed` are present in a live ruleset; the two stage-2 sets,
  `knock4_stage2` and `knock6_stage2`, are asserted nowhere in this file.
  `Verify KNOCK-4, KNOCK-5, KNOCK-6: port knocking sequence ports in
  NFTables`, beyond the live bug recorded above, checks only that the three
  configured port numbers appear somewhere in the ruleset's text — not that
  they appear in the three staged rules `KNOCK-4` through `KNOCK-6`
  actually describe, and not in the order that would distinguish a correct
  sequence from the same three numbers configured in the wrong slots.

- **Two of the three checks this file makes about the emergency-access
  script establish less than "the script works."** `Verify EMRG-1:
  emergency script exists` confirms the file is present and executable at
  `/root/emergency-ssh-access.sh`, on a Tailscale-enabled host. It does not
  confirm the file's mode is `0700` or its owner is `root`, both of which
  `EMRG-1` also states, and it does not run the script in either direction.
  `specs/emergency-access/design.md` records that the tailnet integration
  suite is the only place in this project the script is actually executed
  against a narrowed host and its effect measured by opening a connection;
  that evidence, in `tests/integration/test_tailscale_integration.py`,
  cites `EMRG-3` and `EMRG-4` in `test_emergency_script_unrestricts_ssh`'s
  and `test_emergency_script_restore`'s docstrings.

- **The resource-limits check does not verify everything its own success
  message claims.** `Verify PAM-10, PAM-14: resource limits` asserts that
  the deployed file contains `nproc` and a `core` line matching `core.*0`.
  Its `success_msg` reads "Resource limits deployed (nproc, nofile, core)",
  naming `nofile` — but no condition in the `that:` list checks for
  `nofile` anywhere, so a rendered file missing that directive entirely
  would still pass this check and print a message claiming otherwise. This
  is a defect in the message, not in the assertion it decorates, and it is
  left as found rather than corrected here, the same treatment
  `specs/fail2ban/design.md` records for a comparably wrong message
  elsewhere in this project's test suite.

- **The zram-priority check verifies `SWAP-9` alone, not `SWAP-16`'s
  comparison, and its own `when:` still runs it under `SWAP-16`'s
  condition.** `Verify SWAP-9: zram device has its configured swap priority`
  asserts only that `swap_status.stdout` matches `/dev/zram0.*100` — the
  zram device's own configured priority, read as a literal rather than as
  `zram_swap_priority`'s resolved value, and never compared against
  `/swapfile`'s own priority in the same output. A ruleset in which an
  inventory raised `disk_swap_priority` above 100 would still pass this
  check, because nothing here reads the disk side at all. The block's
  `when:` guard fires only when both zram and disk swap are configured —
  `SWAP-16`'s precondition, not `SWAP-9`'s, which applies whenever zram
  alone is enabled — so the block's placement still advertises a comparison
  its assertion does not make; only the task's own name no longer claims
  one. This is recorded as a finding rather than corrected, since fixing the
  `when:` or adding the missing comparison would change what the check
  does, which is a decision for the swap spec's own requirements to make,
  not this playbook's to make unilaterally.

## Interactions

This playbook cites feature requirement IDs directly and owns none of the
assertions it makes. What follows is which specs it cites and what it
assumes about each; the requirement is always the other spec's to state,
never this one's to restate.

- `USR`, `SUDO`, `SSH`, `TS`, `EMRG`, `FW`, `KNOCK`, `HOST`, `F2B`, `LOG`,
  `TIME`, `SWAP`, `FS`, `LOGIN`, `PAM` — each is cited by ID from the
  relevant block, as the implementation map's row for
  `tests/verify_bootstrap.yml` and each requirement's own `**Verified:**`
  line record. This spec assumes each cited ID still names the condition it
  named when the citation was written; a feature spec that changes a
  requirement's SHALL without a corresponding change here is the drift this
  spec exists to prevent from being invisible, and `make spec-check`'s
  `dangling-citation` finding is what would catch an ID renumbered or
  retired out from under a citation here.
- `SSH` — two checks, sshd's `ActiveState` and `UnitFileState`, verify
  `SSH-20`. They cite it in a comment, not in their task names, so they
  fall short of `VRFY-4`, as that requirement's `**Verified:**` records.
- `KNOCK` and `TS` — that this playbook can reach the host at all. It
  cannot, unaided, on a knock-gated host, and depends on being run from
  inside the tailnet on a Tailscale-narrowed one; `## Failure modes` records
  both. The knock-gated case is this spec's own gap to close, not either of
  theirs — `specs/port-knocking/requirements.md` and
  `specs/port-knocking/design.md` both say so and this spec agrees; neither
  of them owes this playbook a knock play, and this playbook does not yet
  have one of its own. The Tailscale case is different in kind, not just in
  owner: no play this spec could add would let an outside connection reach
  an interface the tailnet itself gates, so `TS` may assume this playbook
  never attempts one.
- `F2B` — this playbook's `fail2ban-client status` check for the `sshd`
  jail is the only one of its three fail2ban checks that distinguishes a
  supervising server from an idle one; `F2B` may assume this playbook
  checks the jail by name rather than only the unit's own state.
- `EMRG` — that a bootstrap run left the script deployed, at the right
  path, executable, and did not run it; `EMRG` may not assume this playbook
  confirms the script's mode, its ownership, or either of its two
  behaviours, since nothing here executes it.
- `PRJ` — this playbook is invoked by `make verify`, defined in the
  `Makefile` `PRJ` maps; this spec assumes only that the target exists and
  runs `ansible-playbook` against this file, and states nothing about how
  `make` itself is organised.
- The testing spec — that `tests/property/test_verification_properties.py`
  is the only test of this playbook's own *structure*, and that it reads the
  playbook's YAML and text rather than running it. One integration test,
  `TestBootstrapVerification::test_verify_playbook_passes`, does execute
  `tests/verify_bootstrap.yml` — against a virtual machine that suite
  bootstrapped, through `run_verify_playbook` rather than through `make
  verify` — and asserts the run exits zero with `failed=0`. That is the
  only place in the project this playbook is run by a test, it runs only
  where Incus is available, and it exercises the passing direction alone.
  No unit or property test executes this playbook.
