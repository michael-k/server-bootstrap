# Tailscale — Design

## Approach

The role is three task files behind one flag. `tasks/main.yml` is the entry
point and contains nothing but two `include_tasks`, each gated on
`tailscale_enabled`: `install.yml`, then `verify.yml`. That split is the
shape of the spec — installation and registration produce a client, and
verification decides whether the run is allowed to continue on the strength
of it — and it is also what makes `TS-2`'s "nothing happens when disabled"
guarantee checkable: two `when:` clauses in one short file, rather than a
condition repeated on twenty tasks where one omission would go unnoticed.

`install.yml` runs five package-management tasks, then a status check, then
one registration command, then two service tasks. The registration is a
single `ansible.builtin.command` invocation of `tailscale up` carrying five
flags, four of which this spec has a requirement for: the login server
(`TS-6`), the auth key (`TS-7`), route acceptance (`TS-10`) and the DNS
opt-out (`TS-11`). Because the command is written as a folded YAML scalar
with one flag per line, no comment can be placed on an individual flag —
anything starting with `#` inside a folded block becomes part of the command
string. All of that task's citations therefore sit in a comment block
directly above the task, which is also where the `TS-8` non-compliance note
lives.

`verify.yml` is a chain of measure-then-assert pairs: wait for the
interface, fail if it did not appear; retry the status command until the
backend reports `Running`; read each address family, publish both as facts,
fail if either is empty; ping, fail if the ping failed; report what was
verified. Every measurement that tolerates its own failure
(`failed_when: false`) is followed by an explicit `fail` task, so the run
stops with a message naming lockout as the reason rather than with a module
error. That pattern is why this role's checks are not inert — the results
are acted on — and `## Failure modes` records the one place where what is
measured is not what the requirement asks for.

The role defines no handlers. `handlers/main.yml` exists as a placeholder
and is empty of behaviour; nothing in this spec needs a restart hook,
because the only service involved is started directly by `TS-13` and its
state is then verified rather than assumed.

## Implementation map

| Path | Realises |
|---|---|
| `roles/tailscale/defaults/main.yml` | TS-1, TS-3, TS-4, TS-5, TS-6, TS-7, TS-14 |
| `roles/tailscale/tasks/main.yml` | TS-2, TS-22 |
| `roles/tailscale/tasks/install.yml` | TS-3, TS-4, TS-5, TS-6, TS-7, TS-8 (recorded as not met), TS-9, TS-10, TS-11, TS-12, TS-13 |
| `roles/tailscale/tasks/verify.yml` | TS-15, TS-16, TS-17, TS-18, TS-19, TS-20, TS-21 |
| `roles/tailscale/handlers/main.yml` | none — the role defines no handlers; see `## Approach` |
| `tests/unit/test_tailscale.py` | TS-2, TS-3, TS-4, TS-6, TS-7, TS-12, TS-13, TS-14, TS-15, TS-16, TS-17, TS-21 |
| `tests/property/test_tailscale_properties.py` | TS-1, TS-2, TS-3, TS-4, TS-5, TS-6, TS-7, TS-9, TS-12, TS-13, TS-14, TS-15, TS-16, TS-17, TS-19, TS-21 |
| `tests/integration/test_tailscale_integration.py` | TS-1, TS-6, TS-7, TS-12, TS-13, TS-17, TS-18, TS-21, TS-22 |

Three requirements are cited from one place only. `TS-10` and `TS-11` name
flags no test asserts, so their sole citation is the registration task.
`TS-20` is cited only in `verify.yml`: the property suite's
address-validation assertion names the IPv4 guard and has no IPv6
counterpart. `TS-8` is cited only from the registration task, and that
citation is a note recording that the task does not satisfy it — see
`## Failure modes`.

`site.yml` also gates this role on `tailscale_enabled` and fixes its
position ahead of `ssh_hardening`, `firewall` and `emergency_access`, which
is half of what `TS-22` requires. That file is `PRJ`'s and carries no `TS`
citation; `TS-22`'s citation sits on the verification include inside this
role, the half this spec owns. The property suite's
`test_property_11_tailscale_conditional_execution` additionally asserts
things about `roles/emergency_access/`, which belong to `EMRG` and are left
uncited here.

## Key decisions

**Headscale rather than Tailscale's own coordination service.** A tailnet
needs a control server: the component that authenticates nodes, distributes
their public keys and addresses, and tells each node how to reach the
others. Tailscale's own hosted service does this well, and choosing it would
have removed a whole piece of infrastructure from the operator's plate.
This bootstrap points at a self-hosted Headscale instance instead, for one
reason that outweighs the convenience: the control server is the single
component that knows the full topology of the private network and decides
who may join it, and in this design that network is the *only* path to SSH
on every enrolled host. A control-plane outage at a third party, or a
compromise of it, would not merely degrade a feature — it would be an
availability and access-control event for every host this bootstrap has
narrowed. Running the control plane means that blast radius stays inside
the operator's own estate. The cost is real and is accepted knowingly: the
operator now runs, secures and backs up a control server, and a pre-auth key
issued by it is a bearer credential this bootstrap has to handle carefully
(`TS-7`, `TS-8`). The client is unmodified upstream Tailscale — the
Headscale choice is expressed entirely in `--login-server` (`TS-6`), which
is why `TS-3` can install the ordinary official package.

**Why verification must precede any SSH restriction.** `SSH` binds sshd to
`tailscale_ipv4` and `tailscale_ipv6` and stops listening on everything
else; `FW` admits SSH only on the tailnet interface. Both act on data this
role produces, and both are irreversible from outside the host once applied:
if the addresses are wrong, absent or unreachable, the next connection
attempt does not fail with a diagnostic — it fails with nothing, from a host
the operator can no longer log into to investigate. Ansible offers no
rollback for that; the play that would undo it needs the same SSH connection
that was just removed. So the ordering is not a matter of tidiness, it is
the entire safety mechanism, and it is why `verify.yml` is a chain of
failures rather than a chain of warnings. Every check in `TS-15` through
`TS-21` stops the play on its own, in a role that runs before any consumer,
so the failure mode of an unhealthy tailnet is "the bootstrap did not
finish, and the host is exactly as reachable as it was" rather than "the
bootstrap finished and the host is gone." This is `INV-8` stated for the one
narrowing that can actually strand an operator, and `TS-22` is the
requirement that holds it.

**One gate in the role, one in the playbook.** `TS-2` is realised twice:
`site.yml` skips the whole role when the flag is false, and `main.yml` skips
both includes as well. The redundancy is deliberate. The playbook-level gate
is what makes a disabled run cheap; the role-level gate is what makes the
role correct when invoked any other way — by tag, from another playbook, or
from the verification suite — and it is the one this spec's tests assert,
because a role that depends on its caller for a security-relevant condition
is only as safe as every future caller.

**A single `set_fact` for both address families.** `TS-17` and `TS-18` are
two requirements realised by one task, deliberately: publishing the pair
atomically means no consumer can ever observe a play where `tailscale_ipv4`
is defined and `tailscale_ipv6` is not. `SSH`'s template guards on both
being defined, so a half-published pair would silently produce an sshd with
no `ListenAddress` narrowing at all — a security failure that looks like
success. The two `fail` tasks that follow (`TS-19`, `TS-20`) then check each
family separately, since by that point both facts exist and the question is
whether either is empty.

## Failure modes

- **The pre-auth key reaches the target's process argument list and the
  controller's log file. `TS-8` is not met.** The registration task
  interpolates `tailscale_pre_auth_key` into `--authkey={{ ... }}` inside
  `ansible.builtin.command`'s `cmd`, and there is no `no_log` in
  `roles/tailscale/` — or anywhere else in this repository. Three exposures
  follow. First, the argument vector: `command` executes the rendered string
  as the `tailscale` process's argv, so the key sits in
  `/proc/<pid>/cmdline` on the target for as long as `tailscale up` runs.
  That file is world-readable — this bootstrap mounts no `hidepid` option on
  `/proc` — so any local account on the host, including an unprivileged
  service account a later compromise lands in, can read it by polling. The
  window is short (seconds) but is reached by any process already running.
  Second, the registered result: `register: tailscale_auth` captures the
  module's result, whose `cmd` field is the full argument vector including
  the key, and the default callback prints that result on failure and at
  raised verbosity. Third, and most durable, `ansible.cfg` sets
  `log_path = ~/.local/state/ansible/bootstrap.log`, so that same `cmd`
  field is appended in plaintext to a file on the controller that survives
  the run indefinitely and is covered by no rotation or shredding policy
  here. A key recovered from any of the three admits its holder to the
  operator's tailnet as a new node until it expires or is revoked — which is
  the entirety of what Vault was protecting, undone at the point of use.
  Per this plan's rules, no behaviour was changed: the requirement is
  written as intended, annotated `pending`, and the role carries a comment
  at the offending task recording that it does not satisfy it. Two existing
  tests (`test_authenticate_task_uses_authkey` and
  `test_property_10_tailscale_installation_and_configuration`) assert the
  forbidden construction is present, so a fix means changing them too.
- **`TS-21`'s connectivity test pings the host's own tailnet address, which
  the kernel answers locally.** `ping -c 3 -I <interface> {{ tailscale_ipv4 }}`
  sends to the very address `TS-17` just published for this host. Linux
  answers a ping to a locally-assigned address from the local stack
  regardless of whether the interface it was bound to can carry traffic
  anywhere, so this check passes as soon as the address exists — which
  `TS-19` has already established one task earlier. It therefore adds
  nothing beyond what the preceding checks proved, and in particular it does
  not establish that a packet reaches the control server, a peer, or any
  other node. The failure handling is real (the result is registered with
  `failed_when: false` and a `fail` task acts on a non-zero return code), so
  this is not a result that is measured and then ignored; the defect is in
  what is measured. `INV-5`'s neighbour `INV-8` is justified in
  `security-invariants.md` partly by this role checking "end to end
  connectivity" — on the strength of this task, that justification is
  stronger than what the code does. A check that pinged a known peer, or
  used `tailscale ping` (which traverses the tailnet rather than the local
  stack), would test the property `TS-21` states. The only genuine end-to-end
  evidence in the project is
  `test_ssh_open_from_tailnet_peer` in the integration suite, which runs
  only under Incus.
- **The registration task's `when:` guard raises a template error, rather
  than registering, when the status command produces no output.** The guard
  reads `(tailscale_auth_check.stdout | default('{}') | from_json)`. The
  `default('{}')` filter substitutes only for an *undefined* value, and a
  registered command result always defines `stdout` — as the empty string
  when the command wrote nothing. `'' | from_json` raises, so on a host
  where `tailscale status --json` fails to produce output (the daemon not
  yet started, the binary not yet on `PATH`, a socket that is not ready) the
  play fails on a Jinja error rather than proceeding to register. Note the
  ordering that makes this reachable: the status check runs immediately
  after `apt` installs the package and *before* `TS-13` starts the service,
  so the task depends on the Debian package's own post-install activation
  having already brought `tailscaled` up. On a host where that did not
  happen, the failure is a template error with no connection to its cause.
  `default('{}', true)` — the boolean form, which also substitutes for an
  empty value — would be the corresponding fix; it is a behaviour change and
  is not made here.
- **`TS-19`'s empty-IPv4 guard is difficult to reach, because the task that
  would produce the empty value usually fails first.** "Get Tailscale IPv4
  address" runs `tailscale ip -4` without `failed_when: false`. On a client
  with no address assigned, that command exits non-zero, so the task itself
  fails the play and the explicit, lockout-naming `fail` task two positions
  later never runs. The guard is not useless — it covers the case where the
  command succeeds with empty or whitespace-only output — but the common
  case produces a bare module failure instead of this spec's own message.
  The same applies to `TS-20`.
- **`tailscale_ipv4` and `tailscale_ipv6` exist only within the play that
  set them.** They are ordinary `set_fact` results with no `cacheable: true`,
  so despite `ansible.cfg` enabling the `jsonfile` fact cache they are not
  written to it and do not survive to a later run or a separate playbook.
  Every consumer in `site.yml` runs in the same play, after this role, so
  this is correct today — but a future playbook that ran `ssh_hardening`
  without `tailscale` would find both facts undefined and, through the
  `| default('')` fallbacks in `firewall` and `emergency_access` defaults
  and the `is defined` guard in `SSH`'s template, would silently render an
  unnarrowed configuration rather than fail.
- **When the flag is false, neither fact is ever defined.** That is correct
  behaviour for `TS-2`, and every consumer handles it — but it is handled by
  each consumer independently, through its own `default('')` or
  `is defined` guard, rather than by anything this spec provides. A new
  consumer that forgot the guard would fail with an undefined-variable error
  on every disabled host.
- **The property suite generates values it never uses.** All four Hypothesis
  strategies in `tests/property/test_tailscale_properties.py` —
  `valid_control_server_url`, `valid_pre_auth_key`, `valid_interface_name`,
  and the `booleans()` and `integers()` draws — produce arguments that no
  assertion in any of the four test bodies reads. Every assertion is a
  substring check against a file on disk, so each test runs its identical
  file check 50 or 100 times per invocation and would pass unchanged if the
  `@given` decorators were deleted. What the suite actually verifies is a
  fixed text corpus, not a property over a generated input space; the
  `max_examples` settings buy nothing but runtime. No test was changed to
  address this, per this plan's rules.
- **Several assertions are file-wide rather than task-scoped.**
  `test_property_10_tailscale_installation_and_configuration` asserts
  `name: tailscaled`, `enabled: true` and `state: started` each appear
  *somewhere* in `install.yml`, not that they sit on the tasks that should
  carry them — the same presence-not-placement weakness recorded for
  `login-policy`, `sudo-hardening` and `pam-hardening`.
  `test_gpg_key_uses_official_url` passes on any URL containing the
  substring `tailscale`, wherever it is hosted. `test_fail_if_not_connected`
  asserts only that the status task has a non-zero `retries`, never that it
  has an `until` condition or what that condition tests.
- **No test in the default suite ever runs with `tailscale_enabled` true.**
  Both `make test-unit` and `make test-property` read task files as text.
  The only enabled run lives in the integration suite behind
  `incus_available()`, so on a machine without Incus every requirement in
  this spec is verified exclusively by reading YAML, and no failure mode
  above would be caught by a green test run.

## Interactions

**What this spec assumes of others:**

- `PRJ` — `site.yml` refuses an enabled run whose control server URL or
  pre-auth key is empty, orders this role ahead of every consumer of its
  facts, and supplies the key from an encrypted vault file. This spec's own
  defaults for both are the empty string precisely because that pre-flight
  check exists; without it, an enabled run with a missing vault variable
  would reach `tailscale up` with an empty `--authkey`.
- `INV-6` — a tailnet that works during the bootstrap and breaks afterwards
  is outside what any check here can prevent; recovery then depends on the
  break-glass path being usable from a console alone.

**What others may assume of this spec:**

- The `ssh-hardening` spec — once this role has run on an enabled host,
  `tailscale_ipv4` and `tailscale_ipv6` are defined, non-empty, and belong
  to an interface that exists and whose client reports `Running`. That spec
  binds sshd to exactly those two addresses and to nothing else, and on a
  disabled host binds to all interfaces instead. `specs/ssh-hardening/design.md`
  cites `TS-17` and `TS-18` for the facts and `TS-22` for the ordering that
  makes binding to them safe.
- The `firewall` spec — its ruleset reads `tailscale_interface` (`TS-14`),
  which its tailnet SSH rule matches by name, and `tailscale_enabled`, which
  selects the tailnet branch and decides whether port knocking applies at
  all. No rule matches either published address.
  `specs/firewall/design.md` cites `TS-14` for the interface and `TS-1` for
  the flag's default.
- The `emergency-access` spec — its break-glass script is rendered with both
  addresses baked in, and its own enable flag defaults to this spec's flag,
  so the script is deployed exactly on the hosts this spec narrowed. It is
  what makes `INV-6` hold for the narrowing this spec's facts cause.
  `specs/emergency-access/design.md` cites `TS-17` and `TS-18` for the
  baked-in addresses and `TS-1` for the flag's default.
- `VRFY` — post-bootstrap verification may assume an enabled host has a
  `Running` client, an interface by the configured name, and an address of
  each family, since the bootstrap could not have completed otherwise.
- The `testing` spec — the integration suite's three-VM fixture (headscale
  server, tailnet peer, bootstrap target) is the only place this project
  exercises an enabled run, and every claim in this spec that rests on real
  system state rather than on file text depends on it.
