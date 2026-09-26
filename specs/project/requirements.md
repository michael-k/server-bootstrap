# Project — Requirements

**Prefix:** `PRJ`

## Purpose

This spec covers the bootstrap run as a whole: how it is entered, what it
refuses to start against, the order in which it applies the machine state that
the feature specs describe, what it reports, and the contract the repository
offers a developer who has to run or change it. Every other spec in the tree
describes one capability of the finished host; without this one, nothing states
that those capabilities are applied to a fresh host, in one run, in an order
where each capability's prerequisites already hold — which is the part that
cannot be inferred from any single feature spec.

Two subjects appear below. **THE Bootstrap** is the run itself, against a target
host. **THE Project** is this repository as a working environment: its tooling,
its dependency declarations and its documentation.

## Scope

### In scope

- Entering the run, and the privileges and facts it needs.
- The platform the run accepts, and every check it performs before it changes
  anything.
- The order in which capabilities are applied.
- What the run reports before it starts, and after it finishes.
- The run's behaviour on a host it has already configured.
- The source of the secrets the run consumes.
- The tooling contract: the managed environment, the dependency declaration and
  the operations exposed as make targets.
- The documentation obligations this repository's README carries.
- The obligation a purpose repository built on this bootstrap carries to
  register every hole it opens in the host's firewall.

### Out of scope

- What any individual capability configures on the host. Each feature spec owns
  its own behaviour, its variables and its defaults.
- The port-knock sequence and the firewall gating it unlocks, which `KNOCK`
  owns even though the knock runs from the same entry point.
- Post-bootstrap verification, owned by `VRFY`.
- The test suites' own requirements, owned by `TEST`.
- The local virtual-machine tooling and image publishing, owned by `INCUS` and
  `IMG`.

## Security invariants

**Upholds:** INV-5, INV-8, INV-9
**Allowances claimed:** none

INV-5 is upheld by `PRJ-15`: the run takes its secrets from an encrypted vault
rather than from the repository. INV-8 is upheld by `PRJ-12`: the fixed order
places every capability that verifies a replacement access path before the
capability that narrows access to it. INV-9 is upheld by `PRJ-13`, `PRJ-25` and `PRJ-14`:
a re-run converges on the same state instead of reopening what an earlier run
closed.

## Requirements

### PRJ-1 — Single-run bootstrap of a fresh host

THE Bootstrap SHALL bring a fresh Debian host, reachable only as root over SSH,
to its full configured state in a single run.

**Why:** The host starts with one way in — the provider's root credential — and
nothing else can be assumed present. A bootstrap that needed a second pass, or a
manual step between passes, would leave a window in which the host is neither in
its initial state nor in its hardened one.
**Verified:** the integration suite bootstraps a fresh virtual machine once and
then asserts the end state: both accounts exist, sshd refuses passwords, and the
firewall and intrusion-prevention services are active.

### PRJ-2 — Privileged execution

THE Bootstrap SHALL perform every configuration task with root privilege on the
target host.

**Why:** Every capability writes to system configuration under `/etc` or manages
a systemd unit. Escalating per task would leave the privilege boundary decided
in a dozen places instead of one, and a task that silently ran unprivileged
would fail in ways that look like a configuration error rather than a
permissions error.
**Verified:** privilege escalation is declared once for the whole bootstrap play,
and the idempotency property test asserts that declaration is present.

### PRJ-3 — Facts gathered before configuration

THE Bootstrap SHALL gather the target host's facts before evaluating any
conditional configuration.

**Why:** The platform floor, the network interfaces, the memory size and the
distribution version all come from gathered facts, and several capabilities
choose what to configure from them. A run with facts disabled would not fail
loudly; it would silently take the wrong branch.
**Verified:** fact gathering is enabled on the bootstrap play, and the
idempotency property test asserts it.

### PRJ-4 — Debian 13 platform floor

THE Bootstrap SHALL refuse to run against a host that is not Debian with a
distribution major version of 13 or newer.

**Why:** The configuration this playbook writes targets the package names,
service units and defaults of Debian 13 (trixie). On an older or unrelated
distribution the run would not fail cleanly — it would install the wrong
packages and write configuration the host's own services ignore, leaving a host
that looks hardened and is not.
**Verified:** a pre-flight assertion checks the reported OS family and
distribution major version and aborts the run with an explanatory message when
either fails.

### PRJ-5 — Pre-flight checks precede every change

THE Bootstrap SHALL complete every pre-flight check before the first task that
changes the target host.

**Why:** A check that fires halfway through leaves a half-configured host: some
hardening applied, some not, and no single state to reason about. Checked first,
a failure is free — the host is exactly as it was.
**Verified:** the checks run in the play's pre-tasks, ahead of every role, and
the idempotency property test asserts that no state-changing module appears
there.

### PRJ-6 — Required user configuration is present

THE Bootstrap SHALL refuse to run unless the manual and deploy account names,
the manual account's password and both accounts' public key file paths are
defined and non-empty.

**Why:** These five values decide who can reach the host once the run finishes.
An undefined name would create an account called nothing; an undefined key path
would deploy no key, and the run would end having disabled root login without
having enabled anyone else.
**Verified:** a pre-flight assertion checks each variable is defined and, for the
account names, non-empty, and names the inventory file in its failure message.

### PRJ-7 — Public key files exist on the controller

THE Bootstrap SHALL refuse to run unless both accounts' public key files exist
on the controller.

**Why:** A path can be defined and still be wrong — a typo, a key not yet
generated, a home directory that is not the one the path assumes. The file is
read on the controller, so its absence is knowable before the first change to
the host rather than at the moment the account is created.
**Verified:** a pre-flight check stats each public key file on the controller and
fails the run when either is missing.

### PRJ-8 — Tailscale configuration is present when Tailscale is enabled

WHERE Tailscale is enabled, THE Bootstrap SHALL refuse to run unless the control
server URL and the pre-authentication key are defined and non-empty.

**Why:** With Tailscale enabled, the run narrows sshd to the Tailscale
addresses. Enrollment that cannot even be attempted, because there is no control
server or no key, would fail after the host has already been changed — and the
narrowing it is a prerequisite for is precisely the step that decides whether
anyone can still reach the host.
**Verified:** a pre-flight assertion, evaluated only when Tailscale is enabled,
checks both variables are defined and non-empty.

### PRJ-9 — Configuration summary before the first change

THE Bootstrap SHALL display a summary of the configuration it is about to apply
before it changes anything.

**Why:** The run is destructive to the host's existing access model, and the
variables driving it are spread across several inventory files. Printing the
effective values — target, platform, account names, SSH port, and whether
Tailscale, a hostname and swap are configured — gives the operator one place to
notice that the run is pointed at the wrong host or reading the wrong inventory,
while stopping it is still free.
**Verified:** the summary is the last pre-task, after the checks and before the
first role.

### PRJ-10 — Reboot notice after the run

THE Bootstrap SHALL report, when the run finishes, whether the host needs a
reboot.

**Why:** Package updates may install a new kernel or replace a running library,
and the host keeps running the old one until it restarts. The playbook does not
reboot on its own — that decision belongs to whoever owns the host's uptime —
so the only alternative to reporting it is leaving the operator to discover it
later, or not at all.
**Verified:** a post-task checks for the reboot-required marker and prints a
warning when it is present.

### PRJ-11 — Completion summary

THE Bootstrap SHALL print, when the run finishes, the access paths the host now
has and the restrictions now in force.

**Why:** The run ends by closing the way the operator got in. A summary naming
the accounts to use, the verification step, the emergency path when Tailscale is
enabled, and the restrictions that are now active turns a successful run into
something the operator can act on without going back to the documentation.
**Verified:** a post-task builds the summary from the run's own variables and
prints it as the final task.

### PRJ-12 — Fixed order of application

THE Bootstrap SHALL apply its capabilities in a single fixed order in which each
capability's prerequisites are established by the capabilities before it.

**Why:** Three orderings are load-bearing. Package updates come first, so the
host's outstanding security patches are applied before it is exposed with its
new access paths, and so every later capability configures the package versions
the host will keep — an upgrade run late would replace freshly hardened
configuration with the package maintainer's own defaults. Accounts
and VPN enrollment come before sshd hardening, because the hardened sshd
configuration names those accounts and binds its listen addresses to VPN
addresses that exist only once enrollment has succeeded — this is what makes
INV-8 hold. The firewall comes after the services it admits. Reordering does not
fail loudly: it produces a plausible configuration that locks the operator out.
**Verified:** the order is declared in one place, and the idempotency property
test asserts every capability appears in that declaration.

### PRJ-13 — A re-run completes without error

THE Bootstrap SHALL complete without error when re-run against a host it has
already configured.

**Why:** The playbook is the definition of the host's configuration, so
re-running it is how a change to that definition is delivered. A re-run that
errored on state it had itself created would make the playbook a one-shot
script, and every later change would have to be applied by hand — which is how
a host's real configuration drifts away from the one in the repository. Per
INV-9, a re-run must also never weaken what an earlier run established.
**Verified:** the integration suite runs the playbook a second time against a
bootstrapped host and asserts the recap reports no failed and no unreachable
hosts; the idempotency property test asserts the structural preconditions —
declarative modules, change conditions on commands, and handlers for restarts.

### PRJ-14 — Clean check mode

THE Bootstrap SHALL report no changes in check mode against a host it has
already configured.

**Why:** Check mode is how a change is reviewed before it is applied. It is
useful only if its output is quiet on a converged host: a check-mode run that
always reports changes cannot tell the operator which changes are the new ones.
**Verified:** the integration suite runs the playbook in check mode against a
bootstrapped host and asserts no task reports a change.

### PRJ-15 — Secrets from the vault

THE Bootstrap SHALL take every secret it applies to the host from an
Ansible Vault-encrypted file.

**Why:** Passwords and pre-authentication keys are the one class of input that
must not live in the repository, and the encrypted vault is the single mechanism
this project offers for supplying them. Upholds INV-5.
**Verified:** the example inventory indirects every credential through a vault
variable, and the bootstrap and verification entry points ask for the vault
password, or read it from a file the operator names.

### PRJ-16 — Every command runs in the managed environment

THE Project SHALL run every playbook, verification and test command inside the
`uv`-managed environment.

**Why:** Ansible's behaviour depends on the exact versions of its collections
and of Python. A command run against whatever happens to be on the developer's
`PATH` reproduces neither the pinned versions nor the one a colleague ran, and
the difference surfaces as a playbook failure rather than as an environment
problem.
**Verified:** every operation the project exposes invokes its tool through `uv`,
which resolves and installs the declared dependencies before running it.

### PRJ-17 — Declared dependencies

THE Project SHALL declare its runtime and development dependencies, each with a
minimum version, in its Python project metadata.

**Why:** One declaration, resolved and locked by the environment manager, is what
makes a run reproducible. Minimum versions rather than exact pins keep the
project on supported releases of Ansible and its tooling, which is where
security fixes land.
**Verified:** the project metadata declares the runtime dependencies and the
lint and test dependency groups, each with a lower bound.

### PRJ-18 — Python floor

THE Project SHALL require Python 3.14 or newer on the controller.

**Why:** The tooling and the tests are written against that release, and an older
interpreter fails at import time with an error that says nothing about the real
cause. Declaring the floor makes the environment manager refuse to build an
environment that would not work.
**Verified:** the project metadata declares the interpreter floor, and the
documented prerequisites state it.

### PRJ-19 — Routine operations are make targets

THE Project SHALL expose each of its routine operations — bootstrapping,
verification, testing, linting and spec checking — as a make target.

**Why:** These commands carry inventory paths, vault arguments, test markers and
lint scopes that are easy to get subtly wrong by hand. Naming each one makes the
correct invocation the shortest one, and gives the documentation and the CI a
single stable name to call.
**Verified:** each operation has a target, and the targets are the commands the
documentation tells a developer to run.

### PRJ-20 — Documented prerequisites

THE Project SHALL document, in its README, what a controller and a target host
must have before a bootstrap run.

**Why:** The run's pre-flight checks state the same requirements, but they state
them at the moment it is most expensive to find out. The README is where someone
decides whether they can run this at all.
**Verified:** the README's prerequisites list the controller tooling, the target
platform, the root access the run needs and the key pairs it deploys.

### PRJ-21 — Documented initial-setup scope

THE Project SHALL state, in its README, that the bootstrap is meant for the
initial setup of a fresh host.

**Why:** The run is idempotent, which invites the assumption that it is a general
configuration-management entry point. It is not: it establishes a baseline on a
host that has not had one, and the assumptions it makes about the starting state
are real.
**Verified:** the README says so in its opening, before the instructions.

### PRJ-22 — Documented run procedure

THE Project SHALL document, in its README, the procedure for running a bootstrap
from a clean checkout.

**Why:** The steps are ordered and mutually dependent — generate the key pairs,
copy and edit the example inventory, encrypt the vault, then run. A reader who
finds only the final command runs it against an inventory that does not exist
yet.
**Verified:** the README gives the procedure as an ordered sequence, from key
generation to the bootstrap command.

### PRJ-23 — Documented secrets handling

THE Project SHALL document, in its README, how secrets are encrypted and
supplied to a run.

**Why:** `PRJ-15` puts every secret in an encrypted vault. That only holds if the
person filling in the inventory knows which values are secrets, which file they
belong in, and how to encrypt, edit and rekey it.
**Verified:** the README documents encrypting, editing and rekeying the vault
file, and generating a hashed password for the manual account.

### PRJ-24 — Documented test procedure

THE Project SHALL document, in its README, how to run the test suites.

**Why:** The suites differ in what they need — the unit and property suites run
anywhere, the integration suite needs a local virtual machine — and a
contributor who cannot tell them apart either runs nothing or runs the slow one
by accident.
**Verified:** the README names the target that runs everything and the targets
that run each suite on its own.

### PRJ-25 — A re-run reports no changes

THE Bootstrap SHALL report no changes when re-run against a host it has already
configured.

**Why:** A re-run that reports changes for state that already matched buries the
one change the operator is actually making. The noise is not merely cosmetic: it
is the signal that tells a reviewer whether a run did what its diff said it
would, and a run that always reports changes cannot be read that way. It is also
how INV-9 is noticed — a task that reports a change on every run is usually a
task that rewrites state rather than converging on it.

**Traceability:** pending — the integration suite re-runs the playbook and
asserts the recap reports no failed and no unreachable hosts, but it does not
assert that the recap reports no changed hosts. Only the check-mode run
(`PRJ-14`) asserts that, and check mode is not the same measurement: a task can
be check-mode clean and still report a change when it actually runs. Adding the
assertion is a change to the suite, which this spec tree's introduction does not
make; until then the requirement stands unverified rather than being written as
though the suite covered it.

### PRJ-26 — Documented configuration surface

THE Project SHALL document, in its README, where every configurable variable is
described.

**Why:** The variables live across several inventory files, and the README is the
only document a reader arrives at knowing nothing. Without a pointer, the
configurable surface is discoverable only by reading the roles — at which point
the reader is guessing which variables are a contract and which are an
implementation detail.
**Verified:** the README's configuration section names each example inventory
file and says what it configures, and each of those files describes its
variables with their purpose and default.

### PRJ-27 — Documented required variables

THE Project SHALL make clear, from its README, which configuration variables a
run requires.

**Why:** `PRJ-6` aborts a run whose required variables are missing, which is the
right behaviour and the worst moment to learn it. A reader who cannot tell
required from optional either fills in everything, including values they have no
basis to choose, or fills in too little and finds out at the pre-flight
assertion.
**Verified:** the configuration the README points to separates the required user
configuration from the optional sections, and marks each variable REQUIRED or
OPTIONAL with its default.

### PRJ-28 — Purpose repositories register the holes they open

A purpose repository built on this bootstrap SHALL document every hole it
opens in the host's firewall in exposure registers of its own, with the
columns of `specs/project/security-invariants.md`'s exposure registers and
the same split between public and tailnet exposure.

**Traceability:** exempt — this requirement's subject is a repository built
on this bootstrap, not this repository, so there is no code site here to
cite, and no test or check here could observe a downstream repository
obeying or breaking it. It is stated as a requirement so that changing what
purpose repositories owe is a spec change rather than an edit to a
document.

**Why:** a purpose repository is expected to open holes, because its
services need them, and the supported way to open one is the drop-in
directory (`FW-20`, `FW-21`). This project's job is to secure everything else, so
that a purpose repository can concentrate on its services and every host
built on the bootstrap gains from an improvement here without drifting from
the others. The price of that division is that the bootstrap's registers
cannot list a purpose repository's holes. Without this obligation the
host's exposure would be listed in one place for the bootstrap's part and
nowhere for the rest, which is the part a reviewer knows least about. With
it, the host's exposure is the bootstrap's registers read together with the
purpose repository's.
**Verified:** not verifiable here, which is what the exemption above records.
`specs/project/bootstrap-contract.md` states this rule to purpose
repositories, at the `/etc/nftables.d` extension point.
`docs/multi-repo-strategy.md` states it to purpose-repository authors; that
citation is documentation, not realisation.
