# Testing — Requirements

**Prefix:** `TEST`

## Purpose

Every other spec in this tree ends its requirements with a `**Verified:**`
line, and that line is only worth what the suite behind it is worth. This
spec covers the suites: what each one is able to establish, what it is
structurally unable to establish, and how a reader of a `**Verified:**` line
elsewhere can tell which of the two they are looking at. Without it, "the
unit suite asserts the directive is present" and "the integration suite
connects to the daemon and is refused" read as the same kind of evidence,
and they are not.

There are two tiers in the sense that matters — whether a test needs a
running system — and they partition the suite exactly: each test is marked
`unit` or `integration`, and no test carries both. `property` is a third
name but not a third tier: each test marked `property` is also marked
`unit`, and it marks a technique — Hypothesis-generated inputs — layered on
top of the unit tier rather than a different relationship to the system
under test. `slow` is a fourth declared marker that currently selects
exactly the integration tier and nothing else.

The subject below is **THE Project**: this repository as a working
environment — its test modules, its markers, its fixtures and the external
tools those fixtures fetch. Nothing here is a requirement on a bootstrapped
host; `**Verified:**` lines in this spec describe the suites themselves.

## Scope

### In scope

- That every test declares which tier it belongs to.
- That the unit tier runs without a target host or a virtual machine.
- That the integration tier runs against a virtual machine the suite itself
  launches.
- That the integration tier skips, rather than fails, where Incus is
  unavailable.
- That a tier can be selected or excluded by a marker expression alone.
- That a Hypothesis-generated input is actually read by the assertions it
  feeds, and that Hypothesis's example budget is declared where Hypothesis
  reads it.
- That the external tools and base image the integration tier fetches at run
  time are not pinned.
- That a change to a role is exercised on a virtual machine before it
  reaches a live host — stated as an intent, and marked as unenforced.

### Out of scope

- What any individual test asserts. Every assertion belongs to the feature
  spec whose requirement ID it cites; this spec does not restate, duplicate
  or second-guess what a `SSH-*` or `FW-*` test is checking. `design.md`'s
  `## Interactions` records what each feature spec may and may not assume
  about the tier its `**Verified:**` lines rest on.
- Whether a given feature is adequately covered. A requirement whose only
  evidence is a substring check against a template is a finding for the spec
  that owns the requirement, recorded there; several specs already record
  exactly that about their own coverage. This spec states what each tier is
  structurally able to establish, not whether any particular spec used the
  right one.
- `tests/verify_bootstrap.yml`, owned by `VRFY`. That playbook is not
  collected by pytest and carries no marker; it reads a live,
  inventory-supplied host rather than a fixture.
  The integration tier does run it once, against its own virtual machine,
  as one of its 47 tests — but the playbook's own requirements are `VRFY`'s.
- The make targets themselves. `PRJ-19` requires each routine operation to
  be exposed as a make target and `PRJ-16` requires each to run through
  `uv`; this spec requires only that the marker expressions those targets
  pass are enough to select a tier. What `make test-unit` is named and how
  it invokes pytest is `PRJ`'s.
- The `incus` package's own requirements — the VM lifecycle, the SSH
  keypair, the image handling — owned by `INCUS`, whose spec is not yet
  written. This spec names that package only where an integration fixture
  depends on it.
- Fixing a test that is weak, dead or misdescribed. This spec states what a
  tier must do; a test that does less than its name claims is a defect in
  the module this spec maps, recorded in `design.md`'s `## Failure modes`
  rather than corrected here.

## Security invariants

**Upholds:** INV-8, INV-9
**Allowances claimed:** none. Nothing in this spec opens a port, relaxes a
permission or writes to a host; the integration tier's virtual machines are
created and destroyed by the suite and are not part of any fleet.

INV-8 — "THE Bootstrap SHALL NOT narrow access before verifying the
replacement path works" — is an ordering property of a bootstrap run, and
the bootstrap's own claim on it is `PRJ-12`'s fixed role order. What this
spec contributes is the only place in the project where that ordering is
observed to have worked rather than argued from the order of a `roles:`
list. `TEST-3`'s tier holds the one suite that runs a Tailscale-enabled
bootstrap against real hosts, and its tests measure both halves of the
invariant on the same machine after the same run: access is narrowed —
`test_ssh_closed_from_host` and `test_ssh_closed_without_firewall` are
refused on the target's bridge address, the second with `nftables` stopped
and the ruleset flushed, so that the refusal is sshd's binding rather than
the firewall's — and the replacement path is open, since
`test_ssh_open_from_tailnet_peer` connects from a second machine over the
tailnet on both the IPv4 and the IPv6 address. The same tier also exercises
the second way back in that a narrowed host is meant to keep:
`test_emergency_script_unrestricts_ssh` runs the deployed script on the
narrowed machine and then opens a connection from outside the tailnet, and
`test_emergency_script_restore` re-narrows and confirms the outside
connection is refused again while the tailnet one still works.

INV-9 — "THE Bootstrap SHALL NOT let a re-run weaken state a previous run
established" — is upheld here in the same way and with the same limit.
`test_second_run_reports_no_failures` bootstraps the machine a second time
through the automation account and asserts the recap reports `failed=0` and
`unreachable=0`; `test_check_mode_reports_no_changes` runs it again in check
mode and asserts `changed=0`, naming the offending tasks when it does not.
Both are in the integration tier and neither runs without Incus.
`tests/property/test_idempotency_properties.py` is the unit-tier
counterpart, and it establishes much less than its name suggests: all four
of its tests read text — `site.yml`, the role task files, their defaults or
their handlers — and assert on module names and directive substrings. Not
one of them runs anything. It is an argument that the roles are
written in an idempotent style, not evidence that a second run changed
nothing. `PRJ-25` records the remaining gap from the bootstrap's side — no
test asserts that a real second run reports no changes, only that check mode
does.

## Requirements

### TEST-1 — Every test declares its tier

THE Project SHALL mark every test with the tier it belongs to, so that no
test is invisible to every tier-selected run.

**Why:** the three tier targets each select by marker, so an unmarked test
is not merely uncategorised — it is run by none of them. `make test`, which
passes no expression, is the only command in the project that would collect
it, so a test that loses its marker stops being run by every command anyone
reaches for while working on a particular tier, and does so without failing,
warning or disappearing from the tree. The cost of a marker scheme is
precisely that a test outside it becomes invisible; this requirement is what
keeps that cost paid.
**Verified:** measured by collection. `-m "not unit and not property and
not integration"` collects no test, and `unit and integration` collects
none, so `unit` and `integration` partition the suite exactly. The markers are applied per module —
`pytestmark = pytest.mark.unit` in each of the eleven modules in
`tests/unit/`, `pytestmark = [pytest.mark.integration, pytest.mark.slow]` in
both modules in `tests/integration/` — or per test function throughout
`tests/property/`. **No
test enforces this.** Nothing in either suite enumerates collected tests and
asserts each carries a tier marker, and `--strict-markers` is not enabled
anywhere in the project's pytest configuration, so a misspelled
`@pytest.mark.unt` produces a warning rather than an error and leaves its
test in exactly the invisible state this requirement exists to prevent.

### TEST-2 — The unit tier runs without a target host

THE Project SHALL let every test in the unit tier run to completion on a
controller with no target host and no virtual machine.

**Why:** this is the tier a developer runs on every edit, and it is the only
tier that runs at all on a machine without Incus. If any part of it needed a
host, the fast feedback loop would not exist on the machine where most of
the editing happens, and the tier's failures would become ambiguous between
"the change is wrong" and "the environment is missing something."
**Verified:** measured by what the tier reads. `tests/unit/conftest.py`
supplies the tier's whole shared fixture set, and every one of its fixtures
either returns a dictionary of variable values or returns a callable that
builds or renders from a role's `templates/` directory; none of them opens a
connection, starts a process or touches anything outside the repository.
The tier's tests either read files from the repository — a role's template
rendered with a fixed variable set, a task file parsed as YAML, a defaults
file, or this project's own spec tree — or exercise this project's own
Python helpers with `subprocess.run` patched out, or run an external binary
on the controller and no host: `tests/unit/test_ssh_keypair.py`'s tests
call `SSHKeyPair.create`, which shells out to `ssh-keygen` and writes into a
temporary directory it then removes, and
`tests/unit/test_emergency_script_edge_cases.py`'s tests execute the
emergency-access template rendered into a temporary directory, with
`systemctl` textually replaced by a mock script and both configuration
paths repointed at fixture files, so nothing they run reaches the
controller's own `/etc`. The two modules that test the VM tooling —
`test_incus_vm.py` and `test_ansible_helpers.py` — patch
`subprocess.run` and never invoke `incus` or `ansible-playbook`. No module
in `tests/unit/` or `tests/property/` imports `socket`, `urllib`,
`requests` or `http`. `make test-unit` and `make test-property` both pass on
this controller.

### TEST-3 — The integration tier runs against a real virtual machine

THE Project SHALL run every test in the integration tier against a Debian
virtual machine that the suite itself launches, rather than against rendered
text or a mocked system.

**Why:** a rendered template and a parsed task file are claims about what
Ansible was told to do. They cannot distinguish a directive that is present
from a daemon that honours it, a rule that is written from a packet that is
dropped, or a task that reports `changed: false` from a host whose state
actually converged. Every spec in this tree has requirements whose substance
only a running system settles; this tier is where they are settled, and its
absence would leave the whole tree resting on text.
**Verified:** measured with `pytest -m integration --fixtures-per-test`: all
47 integration tests parse, and every one of them reaches its target through
a session-scoped fixture that constructs `IncusVM(..., auto_launch=True)`
and destroys it on teardown — `bootstrap_vm` and `swap_vm` in
`tests/integration/conftest.py`, and `tailscale_env`, which launches three
machines, in `tests/integration/test_tailscale_integration.py`. Zero tests
lack one. `bootstrap_vm` and `swap_vm` each run `site.yml` against the fresh
machine and raise if the run returns non-zero, so a test using either is
asserting against a host this suite bootstrapped in the same session.
A fourth guarded fixture, `clean_vm`, is re-exported into the integration
conftest from the shared `incus` package and is currently used by no test in
this repository. Teardown is not unconditional: with `KEEP_VM_ON_FAIL` set
and the session already carrying a failure or an error, every one of these
fixtures prints connection details and leaves the machine running instead.

### TEST-4 — The integration tier skips where Incus is unavailable

WHERE Incus is not installed or its daemon does not answer, THE Project
SHALL skip every test in the integration tier rather than fail it.

**Why:** the controllers this project is developed on do not all have Incus,
and a tier that errored on those machines would make `make test` red for a
reason that has nothing to do with the change under test. A red suite that
is red for environmental reasons stops being read, which costs more than the
coverage the tier provides. Skipping keeps the distinction between "this
was not checked here" and "this is broken" visible in the run's own output.
**Verified:** `incus_available()` is `shutil.which("incus")` followed by the
return code of `incus list --format=json`; it is defined once, in
`incus/src/incus/fixtures.py`, and called by exactly four fixtures, each
immediately followed by `pytest.skip("Incus not available")` — `clean_vm` in
that same file, `bootstrap_vm` and `swap_vm` in
`tests/integration/conftest.py`, and `tailscale_env` in
`tests/integration/test_tailscale_integration.py`. Combined with `TEST-3`'s
measurement — 47 of 47 integration tests reach one of those fixtures — every
integration test in the suite today skips rather than errors when the check
fails. **The guarantee is routing, not enforcement.** Nothing makes a new
integration test go through one of those four fixtures; a test that
constructed an `IncusVM` directly, or ran `incus` through `subprocess`
itself, would error on a machine without Incus rather than skip, and no test
or lint rule in this project would notice.

### TEST-5 — A tier is selectable by marker expression

THE Project SHALL declare a pytest marker for each tier, so that a tier can
be selected, or excluded, by a marker expression alone.

**Why:** the tiers differ by two orders of magnitude in what they cost to
run and by whether they can run at all on a given machine, so the choice of
which to run has to be available at the moment of running rather than
designed into the directory layout. Selection by marker is also what lets
one test belong to two categories at once, which the `property`/`unit`
overlap needs: a property test is a unit test, and both names have to select
it.
**Verified:** `[tool.pytest.ini_options]` in `pyproject.toml` declares
`unit`, `property`, `integration` and `slow`, each with a description. The
`Makefile`'s three tier targets select by nothing else — `uv run pytest -m
unit`, `-m property`, `-m integration` — and `make test` passes no `-m` at
all. Measured: `slow` selects the same tests as `integration`. Compound
expressions resolve as expected:
`property and not unit` selects 0 and `property and integration` selects 0,
confirming the overlap is with `unit` alone. A marker name that
is not declared, used in a `-m` expression, selects nothing and pytest exits
5, which `make` reports as a failure — measured with `-m unitt` — so a typo
in a target does not silently produce a green run. `pyproject.toml` is not
in `tests/spec_check.py`'s `SCAN_GLOBS`, so this requirement's citation sits
in the `Makefile`, where the expressions are actually passed.

### TEST-6 — A generated input is read by the assertions it feeds

WHERE a test draws its inputs from a Hypothesis strategy, THE Project SHALL
make at least one of its assertions depend on a value drawn.

**Why:** a `@given` whose body never reads what was drawn is not a property
test. It runs one fixed assertion `max_examples` times, costs that much
runtime on every developer's every edit, and — far worse than the runtime —
it advertises a generality the test does not have. A reader of a
`**Verified:**` line elsewhere in this tree who sees "the property suite
draws usernames and asserts the account is created" reasonably concludes
that names other than the default have been tried. Where the draw is unread,
none has. Two specs already record a local instance of exactly this —
`specs/tailscale/design.md` for all four of its Hypothesis tests, and
`specs/user-accounts/requirements.md` for its username strategy — and each
found it by reading a test body rather than by any signal the suite gave.
**Verified:** measured by parsing every function in `tests/property/`
carrying a `@given` decorator and comparing its generated parameter names
against the names its own body references. There are 90 such functions. 57
reference none of their drawn parameters anywhere in the body. 6 reference
some but not all. 27 reference every one. Hypothesis is not what the
`property` marker means either: `tests/property/` holds 187 test functions,
so 97 of the tier's tests draw nothing at all and are ordinary file
assertions carrying a `property` marker.

**This requirement is violated by at least 61 of the 90 Hypothesis-driven
tests, across 15 of the 21 modules in `tests/property/`.** The 57 that
reference nothing are unambiguous, and the shape is uniform across them: the
strategies are declared, the parameters are accepted, and the body then
reads a template or a task file from disk and asserts substrings against it.
`test_property_7_ssh_port_configuration` draws `ssh_port` and asserts that
`{{ ssh_port }}` appears in `sshd_config.j2` and that `ssh_port: 22` appears
in the role's defaults — neither statement can vary with the drawn value.
Four of the 6 partial cases are violations the parameter-name measurement
does not catch on its own: `test_ssh_configuration_template_validity`,
`test_property_5_ssh_daemon_hardening_configuration`,
`test_property_2_ssh_key_deployment_and_permissions` and
`test_property_33_playbook_idempotency` each reference a drawn value only
inside `if manual_user == ansible_user: return`, an early exit that skips
the test when two generated usernames collide, so no assertion in any of
them can depend on what was drawn either. The count is a floor rather than
an exact figure: it counts a parameter as used wherever its name appears,
which is why the four above had to be read individually, and the same
reading has not been done for all 27 of the fully-referencing cases.
Nothing is fixed here: correcting it means either feeding the drawn values
into a render and asserting on the output, or deleting the decorators and
the runtime they buy, and both are changes to test bodies rather than to
this spec. Recorded so that a reader of any `**Verified:**` line citing a
property test knows which of the two kinds it is.

### TEST-7 — Hypothesis's example budget is declared where Hypothesis reads it

THE Project SHALL declare Hypothesis's example budget only in a place
Hypothesis reads.

**Why:** a declaration the library ignores is worse than no declaration at
all. It reads as the suite's configuration, it gets documented as the
suite's configuration, and then editing it changes nothing while appearing
to change everything — a developer halving it to speed up the suite would
see no change and have no error to explain why. The failure is silent in
both directions: nothing warns at import, nothing warns at collection, and
the number the library actually uses may coincide with the ignored one, as
it does here.
**Verified:** measured against the installed library. Hypothesis 6.151.9
contains no code that reads `pyproject.toml` — searching every `.py` file in
the installed package for the string `pyproject` returns no matches — and it
exposes no settings loader for it. Neither of the repository's two
`conftest.py` files imports Hypothesis or calls `settings.register_profile`
or `settings.load_profile`. `settings.default.max_examples` is 100, which is
the library's own built-in default and not a value read from this
repository. The budget that actually applies is the 90 per-test `@settings`
decorators in `tests/property/`: 71 at `max_examples=100` and 19 at
`max_examples=50`, and no `@settings` in the project sets anything else.

**This requirement is violated by `pyproject.toml`, which carries a
`[tool.hypothesis]` block setting `max_examples = 100` that nothing reads.**
Its coincidence with the library's own default is what kept the violation
invisible: the observed behaviour — 100 examples per test unless a decorator
says otherwise — is exactly what the dead block appears to produce, so the
block has been read as working configuration. `tests/README.md` documented
it as such, in the words "Property-based tests use Hypothesis with the
following configuration (in `pyproject.toml`)"; that sentence is false and
is corrected in this pass. The block itself is left in place and annotated
with a comment recording that it is inert: deleting it is a change to the
project's build metadata rather than to a document, and this pass does not
make it.

### TEST-8 — External tools the integration tier fetches are not pinned

WHERE the integration tier fetches an external tool or base image at run
time, THE Project SHALL fetch the current upstream version rather than a
pinned one.

**Why:** the hosts this playbook bootstraps track Debian stable and install
Tailscale from its vendor's current repository, so a pin in the test
environment would not make the tests more faithful — it would make them less
so, by freezing the suite against a world the deployed hosts do not live in.
A Tailscale release that changes its install script, a headscale release
that changes its flags, or a Debian point release that moves a package is
something this project wants to discover from a red test, not from a
bootstrap run against a customer's server. The cost is accepted knowingly:
the tier is not reproducible across time, and a failure in it may mean
upstream changed rather than this repository did.
**Verified:** three sites fetch at run time and none of them pins.
`incus/src/incus/headscale.py` asks `gh release view --json tagName --jq
.tagName` for whatever the latest headscale release is and then downloads
that tag's Linux binary, caching it per tag under `/tmp`, so a new upstream
release is picked up on the next run that finds no cached copy — which also
makes an authenticated `gh` on the controller a real prerequisite of the
Tailscale suite. `tests/integration/test_tailscale_integration.py` installs
Tailscale on the tailnet peer with `curl -fsSL https://tailscale.com/install.sh
| sh`, the vendor's current script. `incus/src/incus/constants.py` sets
`IMAGE_PREFIX = "images:debian/"` and `DEFAULT_DEBIAN_VERSION = "13"`, so
the image is named `images:debian/13` — a stream, not a fingerprint — and
`ensure_base_image()` reads that stream's current fingerprint on every run
and rebuilds the locally cached base image whenever it has moved, which is
following upstream rather than pinning it. **The boundary matters and this
requirement does not cross it.** The Python environment is the opposite of
unpinned: `pyproject.toml` declares a lower bound on every dependency it
names except `incus`, which it sources from a path inside this repository,
and `uv.lock` is checked in, so `uv run` resolves the same versions on every
machine. This requirement is about tools fetched from outside that
environment while a test is running. **And the discovery is not automatic:**
this repository has no CI — there is no `.github/` directory and no workflow
file anywhere in it, the GitHub Actions snippet in `tests/README.md` being
an illustrative example rather than a configured pipeline — so a breaking
upstream change surfaces the next time somebody runs `make test-integration`
by hand, which is a weaker guarantee than "in CI" and the one this project
actually has.

### TEST-9 — A role change is exercised on a virtual machine before it reaches a live host

THE Project SHALL exercise a change to a role against a bootstrapped virtual
machine before that change is applied to a live host.

**Why:** the failure this guards against is not a wrong directive but a
locked door. This playbook's business is narrowing access — sshd bound to
one interface, a default-drop ruleset, a knock-gated port — and a change
that renders a template correctly can still leave a host that nothing can
reach, which is exactly the class of error no amount of reading text finds
and no rollback reaches. `TEST-3`'s tier is a disposable host on which that
error is cheap; a production host is one on which it is not recoverable
without a provider's console.

**Traceability:** pending — nothing enforces it, and this requirement is
recorded as an intent rather than written as though something did. There is
no CI in this repository (no `.github/` directory, no workflow file), no git
hook, and no gate of any kind between `make test-integration` and `make
bootstrap`: the bootstrap target runs `ansible-playbook` against whatever
inventory it is given, whether or not the integration tier has ever been run
against the change it is about to apply. The tier that would supply the
evidence exists and is capable of supplying it — 47 tests against machines
this suite launches and bootstraps — but running it before a deployment is a
convention held by whoever is deploying, not a mechanism. Closing the gap
means adding something that gates, which is a change to the project's
tooling rather than to its specs.
