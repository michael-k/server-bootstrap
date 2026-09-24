# Testing — Design

## Approach

The suite is one pytest invocation over `tests/`, split by marker rather than
by runner. `pyproject.toml`'s `[tool.pytest.ini_options]` sets `testpaths =
["tests"]` and declares four markers; the `Makefile` exposes four ways in,
three of which differ only in the `-m` expression they pass. There is no
separate harness, no tox, no per-tier configuration file, and — the point
worth stating plainly — no continuous integration of any kind: this
repository has no `.github/` directory and no workflow file, so every number
in this document and in `requirements.md` was produced by running the suite
on a developer's own machine, and nothing runs it on a push.

The directory layout and the markers agree exactly today, which is
convenient and is not enforced. The tests in `tests/unit/` are marked
`unit` and none is marked `property`; those in `tests/property/` are marked
both `property` and `unit`; those in `tests/integration/` are marked both
`integration` and `slow`. Nothing checks that a file added under
`tests/unit/` carries the `unit` marker, or that a test carrying
`integration` lives under `tests/integration/`; the correspondence is a
convention the modules currently keep.

What separates the tiers is what each one is able to establish, and the gap
is wide enough that it should be read as two different kinds of evidence
rather than as fast tests and slow tests. The unit tier — `tests/unit/` and
`tests/property/` together — renders a Jinja2 template with a
hand-maintained variable dictionary, parses a task file as YAML, or reads a
defaults file, and asserts on the text that comes back; the two modules that
cover the VM tooling instead assert on the commands that tooling would have
run, with `subprocess.run` patched out. It can establish that a directive is
present, that it is rendered from the intended variable and that a default
has the intended value. It cannot establish that sshd accepts the file, that
the kernel loads the ruleset, that a service starts, or that a second run
changes nothing — every one of those is a claim about a running system, and
this tier never has one. The nearest it comes is
`tests/unit/test_emergency_script_edge_cases.py`, which executes the
rendered emergency-access script against temporary fixture files with a
mocked `systemctl`: real behaviour of one artefact, on no host. The
integration tier launches
Debian virtual machines through Incus, runs `site.yml` against them, and
then reads the result back over SSH or `incus exec`. It is the only tier
that can settle any of those, and it runs only where Incus is installed.
`VRFY`'s playbook is a third kind again — it reads a live host from an
inventory rather than a fixture, and is not collected by pytest at all,
though the integration tier does run it once against its own machine.

The one place the two tiers are wired together is
`tests/integration/helpers.py`, which holds `DEFAULT_TEST_VARS` — the
variable set every integration bootstrap runs with — and the two wrappers
that invoke `site.yml` and `tests/verify_bootstrap.yml` against a machine.
That dictionary is a second hand-maintained copy of values the roles already
define; four of its entries sit under two comments saying they must match
`roles/users/defaults/main.yml`, which is an accurate description of the
hazard and not a mechanism against it.

## Implementation map

| Path | Realises |
|---|---|
| `tests/unit/` | TEST-1, TEST-2 |
| `tests/unit/conftest.py` | TEST-2 |
| `tests/property/` | TEST-1, TEST-6, TEST-7 |
| `tests/integration/` | TEST-1, TEST-3, TEST-4, TEST-8 |
| `tests/integration/conftest.py` | TEST-3, TEST-4 |
| `tests/integration/helpers.py` | TEST-3 |
| `incus/src/incus/fixtures.py` | TEST-3, TEST-4 |
| `incus/src/incus/headscale.py` | TEST-8 |
| `incus/src/incus/constants.py` | TEST-8 |
| `Makefile` | TEST-1, TEST-5, TEST-6, TEST-7 |
| `pyproject.toml` | TEST-5 |
| `docs/integration-testing.md` | TEST-3, TEST-4, TEST-8 |

`TEST-9` maps to nothing, which is the whole of its `**Traceability:**
pending` note: the tier that would supply its evidence is `tests/integration/`,
but no file in this repository gates a deployment on having run it.

One of the rows above is a site `tests/spec_check.py` cannot see:
`pyproject.toml`, which declares the markers `TEST-5` requires but is not in
the checker's `SCAN_GLOBS` at all. `tests/README.md` is not scanned either —
the bare `README.md` glob matches the repository root only, and
`tests/**/*.py` and `tests/**/*.yml` do not match a `.md` file — so the
requirement IDs written into it are prose rather than citations, and it has
no row above because it documents the suite rather than realising anything.
`TEST-1` and `TEST-5` are therefore cited from the `Makefile`, where the
marker expressions are actually passed.

`TEST-6` and `TEST-7` are cited from the `Makefile` too, at the
`test-property` target, for a different reason: `tests/property/` is
scanned, but both requirements are properties of the tier taken as a whole —
how its 90 drawing tests treat what they draw, and where the budget they run
under is declared — and no single module in it realises either. The
`test-property` target is the one place the tier is named and invoked.

## Key decisions

**Two tiers by whether a system is needed, and a technique marker on top of
one of them.** The suite is commonly described as three tiers, one per
marker. Measured, the structure is simpler and worth stating as it is: `unit`
and `integration` partition the suite, `property` is a strict subset of
`unit`, and `slow` currently selects the same tests as `integration`. The
reason to keep the extra names anyway is that they are cheap and they select
usefully — `make test-property` runs the Hypothesis-and-file tests without
the rest of the unit tier, which is a useful slice while working on a
strategy — and the reason not to describe them as tiers is that `property
and not unit` selects nothing and always has. A reader who believes there
are three disjoint tiers will reach for `-m "unit and not property"`
expecting the "plain" unit tests and get 256 of them, which happens to be
right, and will reach for `-m "not slow"` expecting to drop a few long tests
and drop the entire integration tier instead.

**Hypothesis for configuration-space coverage, and the gap between that
intent and what the suite does.** The property tier exists because most of
this project's requirements are parameterised — a port, a size, a list of
algorithms, an enabled flag — and a test fixed at one value proves the
template renders for that value only. Generating the value is the right
answer to that, and at most 29 of the tier's 90 Hypothesis tests do it. At
least 61 draw a value and never let an assertion depend on it, so they run
an identical file assertion 50 or 100 times; `TEST-6` states the
requirement, records the count and says why the count is a floor. The
decision recorded here is that the tier is kept and the requirement written
against it, rather than the marker being redefined to describe what the
tests currently do. Redefining it would make the documentation true at the
cost of making the coverage claim permanently false, and the coverage claim
is the one other specs' `**Verified:**` lines are leaning on.

**Virtual machines rather than mocks for the integration tier.** The
alternatives would have been a mocked Ansible connection, a container, or a
harness asserting on Ansible's own reported results. All three are cheaper,
and all three fail at the same place: this project's subject is
what a host will and will not accept over the network after it has been
narrowed, and a mock cannot be refused a connection. The three tailnet tests
that carry the most weight in this tree — SSH refused on the bridge address,
SSH refused with the firewall stopped and the ruleset flushed, SSH accepted
from a tailnet peer on both address families — are each a real TCP
connection from a second machine, and none of them has an equivalent that
does not boot something. The cost is paid in full and knowingly: the tier
needs Incus, it needs an authenticated `gh` for the headscale suite, it
takes minutes rather than milliseconds, and on a machine without Incus it
contributes nothing at all, which means every requirement whose only real
evidence lives there is unverified in the run most developers actually do.

**Unpinned upstreams in the integration tier, pinned dependencies
everywhere else.** These look contradictory in the same repository and are
not. `uv.lock` is checked in and `pyproject.toml` carries a lower bound on
every dependency it names bar the local `incus` package, so the Python
environment resolves identically on every machine — that is `PRJ-16`'s and
`PRJ-17`'s concern, and it is what makes a test failure mean something. The
external tools the integration tier fetches while running are deliberately
the opposite: latest headscale, the vendor's current Tailscale install
script, and the `images:debian/13` stream, whose fingerprint
`ensure_base_image()` re-reads on every run and rebuilds against when it has
moved. Pinning those would make the tier reproducible
and simultaneously make it stop testing the thing it exists to test, since
the hosts this playbook bootstraps track exactly those moving upstreams.
`TEST-8` states the rule and names the boundary; what it cannot state is
that anything watches for the resulting breakage, because nothing does.

## Failure modes

- **`slow` marks nothing that `integration` does not.** `tests/README.md`
  describes `slow` as applying to long-running tests "regardless of type".
  Measured, the two select the identical 47 tests: `integration and not
  slow` is empty and so is `slow and not integration`, because both
  integration modules apply the pair together in a module-level
  `pytestmark` and nothing else in the suite uses `slow` at all. A developer
  who runs `-m "not slow"` expecting to drop a few long tests drops the
  whole integration tier; and the first genuinely slow unit test to be
  marked `slow` would change what `-m "not slow"` means, silently, for
  everyone already using it.

- **Nothing enforces that a test carries a tier marker, and
  `--strict-markers` is not enabled.** `TEST-1` is measured, not checked. No
  test in either suite enumerates the collected tests and asserts each
  carries `unit` or `integration`, and the project sets no `addopts`, so a
  misspelled `@pytest.mark.uint` raises a warning during collection rather
  than an error and leaves its test selected by no target. The one thing
  that does fail loudly is a typo in a `-m` expression: pytest exits 5 when
  nothing is collected, and `make` propagates it.

- **`tests/README.md` carried a legacy requirement-to-test matrix, which
  has been removed.** It mapped a `Requirement 1`–`Requirement 16` scheme
  that no longer exists onto tests, linked to a requirements document that
  has been deleted, and cited checks in `tests/verify_bootstrap.yml` by a
  `Test 14.N` numbering the playbook no longer uses. Its place is taken by a
  pointer to `specs/_traceability.md`. The file's `### Verification Playbook`
  entry, which gave the playbook a check count and a `Test 14.N` range, now
  describes the checks in words instead.

- **`tests/integration/test_single_role.py` was documented but does not
  exist.** It was named in the README's test organisation list and in the
  integration document's directory tree; `tests/integration/` holds only
  `test_bootstrap_integration.py` (40 tests) and
  `test_tailscale_integration.py` (7 tests). Both documents have since been
  corrected: the integration document's tree lists the two modules, and the
  README's test organisation section describes each of the three test
  directories instead of listing modules. The consequence is not only
  documentary: `clean_vm`, the unbootstrapped-machine fixture, is imported
  into `tests/integration/conftest.py` and re-exported for pytest to find,
  and no test in this repository uses it. It is guarded by `incus_available()` like
  the other three, so it satisfies `TEST-4` vacuously.

- **The `unit` marker's own description claims something some of its tests
  contradict.** `pyproject.toml` declares it as "fast, no external
  dependencies". The speed half holds — the tier collects and runs in
  seconds — but the tier does have external dependencies:
  `tests/unit/test_ssh_keypair.py` runs `ssh-keygen` seven times, and
  `tests/unit/test_emergency_script_edge_cases.py` executes a rendered
  `bash` script twelve times. Neither reaches a host or a network, so
  `TEST-2` holds; the marker's wording overstates what the tier avoids. The
  description string is left as found — changing it is a change to the
  project's build metadata rather than to a document — and recorded here
  instead. `tests/README.md`'s copy of the same characterisation is
  corrected in this pass.

- **`DEFAULT_TEST_VARS` is a hand-maintained second copy of role defaults,
  and `docs/integration-testing.md` was a third.** `tests/integration/helpers.py`
  sets `ssh_port` to 2222, a deliberately non-default value that is the only
  evidence in the project that a configured port is honoured end to end. The
  integration document's "Default Test Variables" table said `22`. That is
  corrected in this pass, but the underlying hazard is not: the dictionary
  also restates `login_policy_umask`, `login_policy_retries`,
  `login_policy_timeout` and `pam_faillock_deny` with comments saying they
  must match `roles/users/defaults/main.yml`, and nothing checks that they
  still do.

- **The integration tier's fixtures are session-scoped and some of its tests
  depend on each other's leftovers.** `bootstrap_vm`, `swap_vm` and
  `tailscale_env` are all `scope="session"`, so one machine serves every
  test that asks for it. `TestTailscaleIntegration` says so in its own
  docstring — its tests "run in definition order", and the emergency-script
  restore test depends on the state the unrestrict test left. A failure part
  way through that class leaves the remaining tests asserting against a host
  in an unintended state, and their failures will not describe the original
  cause. `test_ssh_closed_without_firewall` stops `nftables` and flushes the
  ruleset, restoring it in a `finally`, so an ordinary assertion failure is
  covered but a hard interruption of the run would leave the shared machine
  unfirewalled for whatever runs next.

- **`KEEP_VM_ON_FAIL` leaves real machines running.** Every guarded fixture
  checks the environment variable together with the session's failure count
  and, when both are set, prints connection details instead of destroying
  the machine. The tailnet fixture leaves three. Nothing cleans them up
  later; `make vm-destroy` is the documented and manual remedy.

- **The Tailscale suite needs a working `gh` on the controller and said so
  nowhere.** `incus/src/incus/headscale.py` raises `RuntimeError` when `gh`
  is absent from `PATH`, and its two subprocess calls run with `check=True`,
  so a `gh` that is missing, unauthenticated or unable to reach GitHub fails
  the fixture rather than skipping it — a different outcome from the Incus
  check `TEST-4` covers, and one that makes seven integration tests error
  instead of skip. `docs/integration-testing.md`'s prerequisites listed only
  Incus; the `gh` requirement is added there in this pass.

- **The documented account of how the property tier is configured described
  a mechanism that does nothing.** `TEST-7` records the measurement in full.
  The residue worth naming here is why it went unnoticed: the inert
  `[tool.hypothesis] max_examples = 100` names the same number Hypothesis
  defaults to, so every observation anyone could have made of the suite's
  behaviour was consistent with the block working.

## Interactions

- **Every feature spec, on what its `**Verified:**` lines rest on.** Those
  lines fall into three kinds and this spec owns two of them. A line citing
  a unit or property test rests on a file being read and asserted against;
  a line citing the integration suite rests on a machine this tier launched.
  The third kind rests on neither: a measurement the spec's author made by
  reading the implementation, recorded in the spec and confirmed by no
  suite at all — `VRFY-1`'s read-only guarantee and `VRFY-6`'s failing-exit
  behaviour are both of that kind and say so. What a feature spec may not
  assume is that a `**Verified:**` line implies a test: a substantial number
  of them rest on a reading rather than on a run, and the ones that do are
  expected to say which.

- `VRFY` — the two specs divide by what is read, not by what is asserted.
  `tests/verify_bootstrap.yml` reads a live host supplied by an inventory
  and is not collected by pytest; `tests/property/test_verification_properties.py`
  reads that playbook's own YAML and text and is. The one crossing point is
  `TestBootstrapVerification::test_verify_playbook_passes`, an integration
  test that runs the verification playbook against this tier's own virtual
  machine through `run_verify_playbook` and asserts its exit code is zero
  and its recap reports `failed=0` — so the playbook is executed by this
  spec's integration tier, though never by its unit or property tiers, and
  `make verify` itself is run by no test. `VRFY` may assume this tier
  exercises its playbook end to end on a bootstrapped machine under Incus,
  and may not assume anything about it is exercised on a machine without
  Incus.

- `PRJ` — the make targets are `PRJ-19`'s and the `uv` environment is
  `PRJ-16`'s; this spec assumes only that `test`, `test-unit`,
  `test-property` and `test-integration` exist and that the three tier
  targets differ from each other by nothing but their `-m` expression, which
  is what makes `TEST-5` a property of the markers rather than of the
  targets. In the other direction, this spec's integration tier is the only
  evidence `PRJ-13` and `PRJ-14` have — a second run reporting no failures,
  and a check-mode run reporting no changes — and `PRJ-25` has none at all:
  its `**Traceability:** pending` note is precisely a statement about an
  assertion this tier does not yet make.

- `TS`, `SSH`, `FW`, `EMRG` — the tailnet integration fixture is the only
  place in the project where a narrowed host is reached, or fails to be
  reached, over a real connection. Each of those four specs' `design.md`
  records the same dependency from its own side —
  `specs/tailscale/design.md` that this fixture is the only enabled-Tailscale
  run, `specs/ssh-hardening/design.md` that it is the only place a real
  `ListenAddress` binding is exercised, `specs/firewall/design.md` that it
  is the only place a packet is sent at a bootstrapped host's firewall,
  `specs/emergency-access/design.md` that it is the only place the emergency
  script is executed against a narrowed host — and each is right. With Incus
  absent, every requirement in those four specs that concerns a running
  system is verified by reading text. They may assume this tier runs an
  enabled-Tailscale bootstrap and exercises the emergency script in both
  directions; they may not assume it does so in any run that is not
  explicitly `make test-integration` on a machine with Incus.

- `KNOCK` — the relationship is narrower and runs the other way.
  `specs/port-knocking/design.md` records what the integration tier assumes
  about knocking rather than what it proves: that a bootstrapped test VM's
  sequence is `KNOCK-10`'s default unless the playbook was given another,
  and that the `incus` helper re-knocks when the last knock has gone stale.
  The tier does drive the sequence end to end, twice over: on the
  non-Tailscale machine, `test_ssh_blocked_without_knock` opens a raw socket
  to the SSH port and requires it to fail while
  `test_ssh_accessible_after_knock` knocks and then requires the same socket
  to connect; on the tailnet machine,
  `test_port_knocking_does_not_bypass_tailscale` knocks and requires SSH to
  stay shut. What `KNOCK` may not assume is that the sequence the helper
  sends is read from anywhere: `IncusVM.knock()` falls back to a hardcoded
  copy of `KNOCK-10`'s default, and its own docstring says a deployment that
  changes the sequence must change it here too.

- `INCUS` — `tests/integration/` does not manage machines itself. It calls
  into the `incus` package for the VM lifecycle, the ephemeral SSH keypair,
  the `run_playbook` wrapper, the headscale download and `incus_available()`
  itself. `TEST-3` and `TEST-4` are therefore both properties this spec
  states and that package implements, and a change to `incus_available()`'s
  definition of "available" changes what `TEST-4` guarantees without
  touching a file this spec maps. The four guarded fixtures and
  `incus_available()` are the surface the two specs share; `INCUS-10` states
  the package's side of it.

- `IMG` — `incus/src/incus/constants.py`'s `IMAGE_PREFIX` and
  `DEFAULT_DEBIAN_VERSION` are read both by this spec's integration fixtures
  and by the image-publishing command, so `TEST-8`'s "the base image is a
  stream, not a fingerprint" is a fact about a value `IMG` also depends on.
  Neither spec owns that constant alone.
