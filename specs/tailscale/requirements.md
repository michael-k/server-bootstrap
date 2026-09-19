# Tailscale — Requirements

**Prefix:** `TS`

## Purpose

This spec covers the optional VPN enrolment that gives a bootstrapped host a
second, private address it can be reached on: the Tailscale client, joined
to a self-hosted Headscale control server rather than Tailscale's own SaaS
coordination service. Everything it does is gated behind one flag that is
off by default, because a host that never enrols is simply a host with no
tailnet address — but a host that *does* enrol becomes the foundation three
other specs build on. `SSH` binds sshd to the tailnet addresses this spec
produces, `FW` opens the SSH port only on the tailnet interface, and `EMRG`
bakes those same addresses into the break-glass script. Without this spec
none of the three has an address to narrow to; with this spec but without
its verification step, all three would narrow to an address that might not
work, locking the operator out of a host whose only remaining way in is the
provider's console. That is why the role's job does not end at "Tailscale is
installed": it ends at "the tailnet interface exists, carries an address of
each family, and those addresses are published as facts," and it must reach
that state before anything downstream acts on it.

## Scope

### In scope

- The `tailscale_enabled` flag, its default of `false`, and the fact that
  every other requirement in this spec is conditional on it.
- Installing the `tailscale` package from the official Tailscale apt
  repository, the repository's signing key, and the binding between the two.
- Selecting the repository suite and key file that match the host's own
  Debian release.
- The Headscale control server URL (`tailscale_control_server`) and its use
  as the client's login server.
- Registering the node with a pre-authentication key
  (`tailscale_pre_auth_key`) held in Ansible Vault, and how that key is
  supposed to reach the client without being exposed.
- Skipping re-registration on a host already registered.
- The two client-behaviour flags the registration sets: accepting routes
  advertised through the tailnet, and declining the tailnet's DNS
  configuration.
- Enabling and starting `tailscaled`.
- The interface name (`tailscale_interface`, default `tailscale0`).
- The connectivity verification that must pass before the run continues:
  the interface appearing, the backend reaching `Running`, an address of
  each family being assigned, and traffic passing over the interface.
- Publishing `tailscale_ipv4` and `tailscale_ipv6` as facts for downstream
  roles, and the requirement that all of the above completes before any
  role narrows SSH to those addresses.

### Out of scope

- Binding sshd to the published addresses, and what sshd listens on when
  Tailscale is disabled — owned by `SSH`. This spec produces the addresses;
  it does not consume them.
- Opening or closing any firewall rule, on the tailnet interface or
  anywhere else — owned by `FW`.
- The break-glass script that flips SSH between tailnet-only and publicly
  reachable — owned by `EMRG`, which reads this spec's two facts but is
  deployed and gated independently.
- Standing up, configuring, or operating the Headscale control server
  itself, and issuing the pre-auth keys it hands out. Both are the
  operator's responsibility off-host; this spec consumes a URL and a key it
  is given.
- Storing the pre-auth key: the encrypted vault file, the `vault_*`
  indirection convention, and the pre-flight assertion that the URL and key
  are non-empty when the flag is on all live in `site.yml` and `inventory/`,
  owned by `PRJ`. This spec governs what the role does with the key once it
  has it.
- Post-bootstrap confirmation that the tailnet is still up on a live host
  — owned by `VRFY`.

## Security invariants

**Upholds:** INV-5, INV-8
**Relies on:** INV-6
**Allowances claimed:** none

This spec is the reason `INV-8` exists. Narrowing SSH to a tailnet address
is the single most dangerous thing this bootstrap does to a remote host: if
the address is wrong, unassigned, or unreachable, the narrowing succeeds and
the operator's access does not survive it. `TS-15` through `TS-21` are the
checks that make the narrowing safe, and `TS-22` is what requires them to
have finished before anything acts on their result — together they are
`INV-8`'s "verify the replacement path works before narrowing access,"
stated as requirements this spec can be held to rather than as a property
someone hopes the role happens to have.

`INV-5` binds this spec through its one secret, the pre-authentication key.
`TS-7` requires that key to come from Vault; `TS-8` requires it to get from
Vault to the Tailscale client without passing through a process argument
list or Ansible's own output, which is the second half of what `INV-5`
demands and the half that is easy to satisfy on paper and miss in practice.
**`TS-8` is not realised in the implementation today** — it is annotated
`**Traceability:** pending`, and `design.md`'s `## Failure modes` sets out
exactly who can read the key and for how long as a result. The requirement
is written as intended rather than weakened to describe what the code does,
because `specs/` is authoritative: the gap is a bug in the implementation,
not a licence to narrow the invariant.

This spec relies on `INV-6` for its own recovery story. Every failure mode
here — an interface that never appears, a backend that never reaches
`Running`, an address that never arrives — is handled by failing the run
*before* SSH is narrowed, so the host is left exactly as reachable as it was
when the run started. The one case this spec cannot protect against is a
tailnet that works during the run and breaks afterwards, and there `INV-6`
is what carries: `EMRG`'s script is a local file a root console session can
run, making no network call of its own.

## Requirements

### TS-1 — Tailscale enrolment is opt-in and off by default

THE Bootstrap SHALL accept `tailscale_enabled` (default `false`) as the
switch that decides whether this host enrols in a tailnet at all.

**Why:** enrolling a host in a tailnet gives it a second network identity
and, through the specs downstream of this one, changes what sshd listens on
and what the firewall admits — none of which a deployment that does not use
Tailscale should have to opt out of. Defaulting to `false` means the
dangerous, high-value path is the one an operator has to ask for explicitly,
and a bootstrap run that says nothing about Tailscale gets a host with no
tailnet, no narrowed sshd, and no break-glass script it would never need.
**Verified:** the defaults file defines `tailscale_enabled: false`.
`test_property_10_tailscale_installation_and_configuration` and
`test_property_11_tailscale_conditional_execution` each assert the literal
string `tailscale_enabled: false` appears in the defaults file. The
integration fixture is the only place the flag is ever set to `true` in this
project's own tests, and it runs only when Incus is available. No test in
the default suite exercises an enabled run.

### TS-2 — Nothing is installed, configured or verified when disabled

THE Bootstrap SHALL perform no Tailscale installation, registration, service
management or verification on a host where `tailscale_enabled` is false.

**Why:** an opt-in flag that only gates *some* of a role's work is worse
than no flag at all — it leaves a disabled deployment with a partially
configured client, an apt repository it did not ask for, or a verification
step that fails the run over a VPN it never wanted. Gating every include on
the flag keeps "disabled" meaning literally nothing happened.
**Verified:** both `include_tasks` in the role's entry point carry
`when: tailscale_enabled | bool`. `test_main_tasks_use_when_condition`
iterates every task in that file and asserts each one's `when` mentions
`tailscale_enabled`; `test_only_two_include_tasks_in_main` asserts there are
exactly two includes, which is what makes the first test's coverage
complete rather than coincidental;
`test_install_tasks_included_when_enabled` and
`test_verify_tasks_included_when_enabled` each assert the condition on one
include by name. `test_property_11_tailscale_conditional_execution` asserts
the same condition appears within five lines of each include. Nothing tests
that the tasks *inside* `install.yml` and `verify.yml` are unreachable by
any other path — the guarantee rests entirely on those two includes being
the only way in, which is true of the role as written but is not itself
asserted anywhere. The role is additionally gated a second time at the
playbook level; see `design.md`'s `## Key decisions`.

### TS-3 — Package installed from the official Tailscale repository

THE Bootstrap SHALL install the `tailscale` package from the official
Tailscale apt repository named by `tailscale_repo_url` (default
`https://pkgs.tailscale.com/stable/debian`).

**Why:** Debian ships no `tailscale` package of its own in a version this
bootstrap can rely on, so the client has to come from upstream. Naming the
repository in a role default rather than hardcoding it in a task keeps the
source auditable in one place and lets a deployment that mirrors upstream
point at its own mirror without editing tasks.
**Verified:** the defaults file defines `tailscale_repo_url` pointing at
`https://pkgs.tailscale.com/stable/debian`; the task "Add Tailscale
repository" builds its `deb` line from that variable, and the task "Install
Tailscale package" installs `tailscale` with `state: present`.
`test_repository_task_exists` and `test_install_package_task_exists` assert
those two tasks exist with those parameters;
`test_tailscale_repository_configuration` and
`test_property_10_tailscale_installation_and_configuration` assert the
default's value and the variable's use as substrings. No test confirms the
installed package actually came from that repository rather than from
another source that happened to offer the same package name.

### TS-4 — Repository bound to the official signing key

THE Bootstrap SHALL bind the Tailscale repository to the official signing
key fetched from `tailscale_repo_key_url`, stored at
`/usr/share/keyrings/tailscale-archive-keyring.gpg` and named in the
repository's `signed-by` option.

**Why:** a third-party apt repository that is not pinned to a specific key
is trusted by whatever keys apt already holds, which turns any one of them
into a signing authority for this repository's packages. `signed-by` narrows
the trust to exactly one key for exactly one repository, so a compromise
elsewhere in apt's keyring cannot be used to serve a forged `tailscale`
package — a package that, by the nature of this role, is about to be given
the credentials to join the operator's private network.
**Verified:** the defaults file defines `tailscale_repo_key_url` under
`pkgs.tailscale.com`; the task "Add Tailscale GPG key" fetches it to
`/usr/share/keyrings/tailscale-archive-keyring.gpg` with mode `0644`, and
the repository line carries
`signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg`.
`test_gpg_key_task_exists`, `test_gpg_key_uses_official_url`,
`test_tailscale_repository_configuration` and
`test_property_10_tailscale_installation_and_configuration` assert those
substrings. `test_gpg_key_uses_official_url` is satisfied by the string
`tailscale` appearing anywhere in the URL, so it would pass for a URL on an
entirely unrelated host containing that word. No test verifies the
fetched key's fingerprint, and the fetch itself trusts TLS to
`pkgs.tailscale.com` alone — there is no out-of-band pin. The prerequisite
task "Ensure gpg is installed for apt_repository" exists so
`apt_repository` can validate the key at all.

### TS-5 — Repository and key selected for the host's Debian release

THE Bootstrap SHALL select the repository suite and signing key for the
host's own Debian release, taken from
`ansible_facts['distribution_release']` rather than hardcoded.

**Why:** Tailscale publishes a separate suite and a separate key file per
Debian release; pinning either to one release name would install packages
built for the wrong release, or fail outright, the first time this bootstrap
runs against a newer Debian than the one it was written on. Deriving both
from the gathered fact makes the role survive the next stable release
without an edit.
**Verified:** `tailscale_repo_key_url` interpolates
`ansible_facts['distribution_release']`, and so does the `deb` line in the
task "Add Tailscale repository".
`test_tailscale_repository_configuration` asserts the fact name appears in
both the defaults file and the tasks file; it is parametrized over three
Debian release names but never substitutes any of them — the generated
value is not used by a single assertion in the test body. No test renders
the URL or the repository line for a given release, so nothing confirms the
fact lands in the right position in either string.

### TS-6 — Control server URL configurable and used as the login server

THE Bootstrap SHALL accept `tailscale_control_server` as the URL of the
Headscale control server and pass it to the client as its login server.

**Why:** the default Tailscale client coordinates through Tailscale's own
hosted service; this bootstrap deliberately points it at a self-hosted
Headscale instance instead, so the coordination server that learns every
node's addresses, keys and connection metadata is one the operator runs.
Making it a variable rather than a constant is what lets a deployment name
its own server — there is no sensible default to fall back on, which is why
the role's default is the empty string and `PRJ`'s pre-flight check refuses
to run an enabled bootstrap without it.
**Verified:** the defaults file defines `tailscale_control_server: ""`; the
registration task passes `--login-server={{ tailscale_control_server }}`.
`test_authenticate_task_uses_login_server` asserts both `--login-server` and
the variable name appear in the task's `cmd`, and
`test_property_10_tailscale_installation_and_configuration` asserts the
exact `--login-server={{ tailscale_control_server }}` substring. The
`valid_control_server_url` Hypothesis strategy generates URLs that no
assertion ever uses. No test confirms the client actually reaches the named
server, or that an empty value is refused — that refusal lives in
`site.yml`, owned by `PRJ`.

### TS-7 — Node registered with a pre-auth key held in Vault

THE Bootstrap SHALL register the node with the control server using the
pre-authentication key `tailscale_pre_auth_key`, supplied from Ansible
Vault.

**Why:** interactive enrolment requires a human to follow a login URL in a
browser, which a non-interactive bootstrap run cannot do; a pre-auth key is
what lets the node enrol unattended. That key is a bearer credential — it
admits whoever holds it to the operator's private network as a new node —
so it is exactly the kind of secret `INV-5` requires to be delivered through
Vault and never committed. The role's default is the empty string precisely
so that nothing is registered by accident if the vault variable is missing.
**Verified:** the defaults file defines `tailscale_pre_auth_key: ""` with a
comment directing it at `vault_tailscale_pre_auth_key`; the registration
task passes the variable as the client's auth key.
`test_authenticate_task_uses_authkey` asserts both `--authkey` and the
variable name appear in the task's `cmd`, and
`test_property_10_tailscale_installation_and_configuration` asserts the
exact `--authkey={{ tailscale_pre_auth_key }}` substring — which is to say
both tests assert the very construction `TS-8` forbids, and would fail if
`TS-8` were implemented. The `valid_pre_auth_key` Hypothesis strategy
generates `tskey-auth-…` strings no assertion uses. Nothing verifies the
value actually came from a vault rather than from plaintext inventory.

### TS-8 — Pre-auth key kept out of the argument list and out of run output

THE Bootstrap SHALL deliver the pre-authentication key to the Tailscale
client without it appearing in any process's argument list or in Ansible's
task output, log or registered results.

**Traceability:** pending — the implementation passes the key as a literal
`--authkey=` command argument on a task with no `no_log`, so it reaches both
places this requirement forbids. See `design.md`'s `## Failure modes`.

**Why:** `INV-5` requires every secret to reach the host through Vault and
never through a log or a process argument list, and the second clause is the
one that decides whether Vault was worth anything. A process's argument
vector is world-readable on a Debian host through `/proc/<pid>/cmdline` —
this bootstrap sets no `hidepid` mount option, so every local account can
read it, including any unprivileged service account a later compromise lands
in. Ansible's own handling is the more durable exposure: a `command` task's
result carries the full argument vector in its `cmd` field, that result is
what `register:` captures and what the default callback prints on failure or
at any raised verbosity, and `ansible.cfg` sets `log_path`, so the same
`cmd` field is appended to a plaintext file on the controller that persists
indefinitely after the run. A pre-auth key read out of either place lets its
holder join the operator's tailnet as a new node until the key expires or is
revoked — which is the whole of the protection Vault was providing, undone
at the last step.
**Verified:** nothing verifies this, because nothing implements it. There is
no `no_log` anywhere in this repository, and no test asserts the key's
absence from an argument list, a registered result or a log. Two existing
tests assert the opposite construction is present (see `TS-7`), so
implementing this requirement means changing those tests as well as the
role. The single `TS-8` citation in the tree sits on the registration task
itself and reads as a record of non-compliance, not as evidence: it is there
so a reader of the offending line finds the rule it breaks. `design.md`'s
`## Failure modes` records the exposure in full.

### TS-9 — Registration skipped on an already-registered host

THE Bootstrap SHALL skip registration on a host whose Tailscale backend is
already in the `Running` state.

**Why:** `tailscale up` with an auth key against an already-registered node
is at best redundant work on every re-run and at worst a re-registration
that consumes a single-use key or creates a duplicate node in the control
server's node list. Checking the backend's state first is what makes an
enrolled host converge silently rather than re-enrolling itself every time
the playbook runs — the same "a re-run changes nothing it does not have to"
reasoning `INV-9` applies elsewhere.
**Verified:** the task "Check Tailscale authentication status" registers
`tailscale status --json` with `failed_when: false`, and the registration
task's `when` compares that output's `BackendState` against `Running`.
`test_property_10_tailscale_installation_and_configuration` asserts the
strings `tailscale_auth_check`, `register: tailscale_auth` and
`changed_when: tailscale_auth.rc == 0` appear in the file. No test evaluates
the `when` expression itself, and its behaviour when the status command
produces no parseable output is a failure mode rather than a skip — see
`design.md`.

### TS-10 — Routes advertised through the tailnet accepted

THE Bootstrap SHALL configure the client to accept subnet routes advertised
by other nodes on the tailnet.

**Why:** a tailnet is frequently more than a set of point-to-point node
addresses — a subnet router advertises routes to networks behind it, and a
client that declines them can reach the advertising node but nothing it
fronts. Accepting them is what makes the tailnet a usable network from this
host rather than a list of peers, and it is a deliberate choice: it means
another node on the tailnet can influence this host's routing table, which
is acceptable only because every node on the tailnet was admitted by the
operator's own control server.
**Verified:** the registration task passes `--accept-routes`. No test in any
suite asserts this flag's presence, and nothing confirms an advertised route
is actually installed on the host.

### TS-11 — Host DNS configuration left untouched

THE Bootstrap SHALL configure the client not to apply the tailnet's DNS
configuration to the host.

**Why:** Tailscale's DNS feature rewrites the host's resolver configuration
to point at the tailnet's own resolver. On a server whose name resolution is
already deliberate — and whose reachability from the outside must not depend
on the VPN being up — silently taking that over would make DNS a second
thing that breaks when the tailnet does, and would do it invisibly. Opting
out keeps the host's resolver exactly as the rest of this bootstrap left it.
**Verified:** the registration task passes `--accept-dns=false`. No test in
any suite asserts this flag's presence, and nothing confirms the host's
resolver configuration is in fact unchanged after enrolment.

### TS-12 — `tailscaled` enabled at boot

THE Bootstrap SHALL enable the `tailscaled` service so it starts on boot.

**Why:** a host whose tailnet membership does not survive a reboot is a host
that reboots into being unreachable, because `SSH` has by then bound sshd to
addresses that only exist while `tailscaled` runs. Enabling the unit is what
makes the narrowing downstream specs perform safe across a restart rather
than only until the next one.
**Verified:** the task "Enable Tailscale service" sets `enabled: true` on
`tailscaled`. `test_service_enabled_task_exists` asserts the task's module
parameters directly;
`test_property_10_tailscale_installation_and_configuration` asserts
`name: tailscaled` and `enabled: true` appear somewhere in the file, not
that they sit on the same task. `test_tailscale_services_running` in the
integration suite runs `systemctl is-enabled tailscaled` on a real host, and
is the only check of the actual system state — it runs only under Incus.

### TS-13 — `tailscaled` started

THE Bootstrap SHALL start the `tailscaled` service.

**Why:** enabling a unit arranges for the next boot; it does nothing for the
run in progress. The verification in `TS-15` through `TS-21`, and every fact
it publishes, needs a client that is running right now.
**Verified:** the task "Start Tailscale service" sets `state: started` on
`tailscaled`. `test_service_started_task_exists` asserts the task's module
parameters directly;
`test_property_10_tailscale_installation_and_configuration` asserts
`state: started` appears somewhere in the file — a substring that also
matches any other started service, were one ever added.
`test_tailscale_services_running` runs `systemctl is-active tailscaled` on a
real host under Incus. Note the ordering: this task runs *after*
registration, which therefore depends on the package's own post-install
activation rather than on this requirement; see `design.md`'s
`## Failure modes`.

### TS-14 — Interface name configurable

THE Bootstrap SHALL accept `tailscale_interface` (default `tailscale0`) as
the name of the network interface the client creates.

**Why:** every check in this spec's verification block and every rule `FW`
writes for the tailnet is expressed in terms of this interface name, so it
has to be stated once rather than repeated as a literal in each place that
needs it. `tailscale0` is the name the client uses on Linux; making it a
variable costs nothing and keeps a rename from meaning an edit in four
files.
**Verified:** the defaults file defines `tailscale_interface: "tailscale0"`;
the interface wait, the connectivity test and every failure message use the
variable. `test_interface_wait_uses_tailscale_interface_var` asserts the
variable appears in the wait task's `path`;
`test_property_10_tailscale_installation_and_configuration` asserts the
literal default value appears in the defaults file, and
`test_property_12_tailscale_connectivity_verification` asserts
`path: /sys/class/net/{{ tailscale_interface }}` and
`-I {{ tailscale_interface }}` as substrings. The `valid_interface_name`
Hypothesis strategy generates names no assertion uses — no test substitutes
a non-default name anywhere.

### TS-15 — Run fails if the tailnet interface does not appear

THE Bootstrap SHALL fail the run, with a message naming lockout as the
reason, if the tailnet interface does not appear within 30 seconds.

**Why:** this is the first of `INV-8`'s checks and the cheapest one: if
there is no interface, there is nothing for `SSH` to bind to and nothing for
`FW` to open, and continuing means narrowing access to an address that does
not exist. Failing here leaves the host exactly as reachable as it was
before the run, which is the whole point of verifying before narrowing.
**Verified:** the task "Wait for Tailscale interface to be created" polls
`/sys/class/net/<interface>` for 30 seconds with `failed_when: false`, and
the task "Fail if Tailscale interface does not exist" fails on its
`failed` result with a message mentioning lockout prevention.
`test_interface_wait_task_exists`, `test_interface_wait_uses_tailscale_interface_var`
and `test_fail_if_interface_missing` assert the two tasks exist with those
parameters; `test_property_12_tailscale_connectivity_verification` asserts
the wait module, the path, a timeout, the register name, the `failed_when`,
the fail module, the `when`, and the phrase `prevent lockout` all appear in
the file — as independent substrings, not as a connected pair of tasks. No
test runs the pair against a host with no interface.

### TS-16 — Run fails if the backend does not reach `Running`

THE Bootstrap SHALL fail the run if the Tailscale backend does not report
`BackendState: Running` within the retry budget.

**Why:** an interface can exist while the client is still negotiating,
logged out, or stuck needing a login — all states in which the host has no
usable tailnet address. `Running` is the client's own statement that it is
enrolled and operating, and it is the precondition under which the address
lookups in `TS-17` and `TS-18` return anything meaningful.
**Verified:** the task "Wait for Tailscale to reach Running state" retries
`tailscale status --json` 15 times at 2-second intervals `until` the parsed
`BackendState` equals `Running`, failing the run when the budget is
exhausted. `test_get_tailscale_status_task_exists` asserts the command, and
`test_fail_if_not_connected` asserts only that the task's `retries` is
greater than zero — it does not assert the `until` condition, so a task that
retried forever without ever checking the state would pass it.
`test_property_12_tailscale_connectivity_verification` asserts
`BackendState == "Running"` appears in the file. No test exercises a backend
that never reaches `Running`.

### TS-17 — IPv4 address published as `tailscale_ipv4`

THE Bootstrap SHALL publish the host's tailnet IPv4 address as the fact
`tailscale_ipv4`.

**Why:** this fact is this spec's primary output. `SSH` renders it into a
`ListenAddress`, `FW` builds its tailnet rule from it, and `EMRG` writes it
into the break-glass script; none of them queries the client themselves.
Publishing it as a play fact rather than leaving each consumer to shell out
means all three see one value, discovered once, at a point in the run where
`TS-16` has already established it is meaningful.
**Verified:** the task "Get Tailscale IPv4 address" runs `tailscale ip -4`
and the task "Set Tailscale IP facts" sets `tailscale_ipv4` from its trimmed
stdout. `test_get_tailscale_ip_task_exists` and `test_set_tailscale_ip_fact`
assert the tasks exist and that the `set_fact` names `tailscale_ipv4`;
`test_property_12_tailscale_connectivity_verification` asserts the command,
the register name and the exact `set_fact` line as substrings. The
integration fixture and `test_ssh_open_from_tailnet_peer` are the only
places a real address is produced and used, and that suite runs only under
Incus. No test confirms the published value parses as an address, or that it
lies in the tailnet's own range.

### TS-18 — IPv6 address published as `tailscale_ipv6`

THE Bootstrap SHALL publish the host's tailnet IPv6 address as the fact
`tailscale_ipv6`.

**Why:** the same consumers need an address of each family, and for the same
reason `INV-4` treats the firewall as one dual-stack table: a host that is
narrowed on one family and left inconsistent on the other has either a hole
or a lockout, depending on which way the inconsistency falls. `SSH` binds
both `ListenAddress` lines from this pair, so a missing IPv6 fact means sshd
silently listens on IPv4 only.
**Verified:** the task "Get Tailscale IPv6 address" runs `tailscale ip -6`
and the task "Set Tailscale IP facts" sets `tailscale_ipv6` from its trimmed
stdout, in the same `set_fact` as `TS-17`. Neither the unit suite nor the
property suite asserts anything about the IPv6 half — every assertion about
address discovery names the IPv4 task, the IPv4 register or the IPv4 fact.
The only evidence for this requirement is the integration suite's
`test_ssh_open_from_tailnet_peer`, which reaches the target over its tailnet
IPv6 address, and it runs only under Incus.

### TS-19 — Run fails if no tailnet IPv4 address is assigned

THE Bootstrap SHALL fail the run, with a message naming lockout as the
reason, if no tailnet IPv4 address is assigned.

**Why:** `TS-17` publishes whatever the client returns, including nothing.
An empty fact does not stop a downstream template from rendering — it
renders an empty `ListenAddress` or an empty firewall rule, which is how a
verification step that produced no address still ends in a host nobody can
reach. Failing explicitly on the empty value is what keeps `INV-8`'s
guarantee from depending on every consumer independently checking for it.
**Verified:** the task "Fail if Tailscale IPv4 is not assigned" fails when
`tailscale_ipv4` is the empty string, with a message mentioning lockout
prevention. `test_property_12_tailscale_connectivity_verification` asserts
the `when: tailscale_ipv4 == ""` substring. No test reaches this task with
an empty fact; `design.md`'s `## Failure modes` records why the preceding
task's own failure behaviour makes this guard hard to reach in practice.

### TS-20 — Run fails if no tailnet IPv6 address is assigned

THE Bootstrap SHALL fail the run, with a message naming lockout as the
reason, if no tailnet IPv6 address is assigned.

**Why:** the dual-stack half of `TS-19`, for the reason `TS-18` gives: sshd
binds both families from this pair, so an empty IPv6 fact is the same
lockout risk as an empty IPv4 one, one family over.
**Verified:** the task "Fail if Tailscale IPv6 is not assigned" fails when
`tailscale_ipv6` is the empty string, with a message mentioning lockout
prevention. No test in any suite asserts this task's presence or its
condition — the property suite's address-validation assertion names the IPv4
guard only.

### TS-21 — Traffic confirmed to pass over the tailnet interface

THE Bootstrap SHALL confirm that traffic passes over the tailnet interface,
failing the run with a message naming lockout as the reason if it does not.

**Why:** an interface that exists, a backend that says `Running`, and an
address that is assigned are three statements the client makes about itself;
none of them is a packet. This is the check that is supposed to turn
`INV-8`'s "verify the replacement path works" into something observed rather
than reported, and it is the last thing standing between the run and the
narrowing that follows it.
**Verified:** the task "Test connectivity through Tailscale interface" runs
`ping -c 3 -I <interface> {{ tailscale_ipv4 }}` with `failed_when: false`,
and the task "Fail if Tailscale connectivity test fails" fails on a non-zero
return code with a message mentioning lockout prevention; a final debug task
reports the verified interface, address and backend state.
`test_connectivity_ping_test_exists` and
`test_fail_if_connectivity_test_fails` assert the two tasks exist, and
`test_property_12_tailscale_connectivity_verification` asserts the ping
fragments and the `when: tailscale_ping.rc != 0` condition as substrings —
so the failure is wired up, and this is not an inert check in the sense of a
result that is measured and then ignored. What no test asserts is *what is
pinged*: the target is the host's own tailnet address, which the kernel
answers locally as soon as the address is assigned, without a packet ever
crossing the tailnet. The requirement above is therefore not met by the
implementation in substance even though the task and its failure handler are
present; `design.md`'s `## Failure modes` sets out what this does and does
not prove. The only genuine end-to-end evidence in this project is the
integration suite's `test_ssh_open_from_tailnet_peer`, which reaches the
target from a separate tailnet peer over both families and runs only under
Incus.

### TS-22 — Verification completes before SSH is narrowed

THE Bootstrap SHALL complete every check in `TS-15` through `TS-21` before
any role narrows SSH to the tailnet addresses.

**Why:** this is `INV-8` stated for the one narrowing this bootstrap
performs that can actually strand an operator. Each individual check is
worth something only if its failure stops the run in time; a verification
step that ran after sshd had already been rebound would report the problem
from a host nobody could log into to fix it. The ordering is therefore a
requirement in its own right, not an implementation detail of where the
tasks happen to sit.
**Verified:** the role's entry point includes `install.yml` and then
`verify.yml`, both before the role returns, and the playbook lists this role
ahead of `ssh_hardening`, `firewall` and `emergency_access`.
`test_verify_tasks_included_when_enabled` asserts the verification include
exists and is gated, but nothing in the unit or property suite asserts the
*order* of the two includes, and the cross-role ordering lives in `site.yml`,
which `PRJ` owns and which this spec does not cite. The integration suite's
`test_ssh_open_from_tailnet_peer` is the only check that would actually
catch a violation: it reaches a fully bootstrapped host over the tailnet
after every narrowing role has run, and it runs only under Incus.
