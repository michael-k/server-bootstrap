# Incus tooling — Design

## Approach

The toolkit is a thin, synchronous wrapper around the `incus` command-line
client. Every operation is a `subprocess.run` of an `incus` or `ssh` or
`ansible-playbook` invocation whose output is parsed — `--format=json` where
Incus offers it, line-prefix matching where it does not (`vm.py`,
because `incus image info` refuses `--format=json` for a remote image). There
is no Incus SDK, no daemon socket, no async. The reason is that the CLI is
Incus's supported interface and the only one whose behaviour a developer can
reproduce by hand when a test fails, which for a test harness matters more
than either speed or type safety.

The package is eight modules, and no line count of them appears in this spec:
a number measured from the files this spec also writes citations into is a
claim that invalidates itself the next time somebody adds a docstring, which
has already happened twice here. What is stable is the shape. `vm.py` is the
largest by a wide margin — it holds `IncusVM` and the base-image builder —
and `__main__.py`, the command line, is next; `ssh.py`, `constants.py`,
`ansible.py` and `fixtures.py` are small and single-purpose;
`headscale.py` is a control-server helper
that belongs to the Tailscale integration suite rather than to this spec;
`__init__.py` re-exports two names. Nothing imports anything outside the
standard library except `pyyaml`, in `ansible.py`, and `pytest`, in
`fixtures.py` — which is why the package declares `pytest` as an optional
`fixtures` extra (`incus/pyproject.toml`) rather than a dependency: a
consumer that wants only `IncusVM` and `run_playbook` installs neither pytest
nor anything else.

One shape runs through the whole package and is worth naming, because it is
what makes the toolkit usable for firewall and SSH tests: almost nothing
raises on a non-zero exit. `exec`, `ssh`, `get_ip`, `destroy` and
`run_playbook` all pass `check=False`; the first two and the last hand the
`CompletedProcess` back, so
"the connection was refused" is a value a test asserts on rather than an
exception it has to catch, while `get_ip` turns a failure into an empty
string and `destroy` into a warning on stderr. The exceptions are the
operations where a failure
could not be a test's subject: `launch`, `put_file`, `get_file`, the
base-image build and `ssh-keygen` all use `check=True`, and four of the
readiness poll's five phases raise `TimeoutError` naming which one ran out.

Machines are named, not tracked. There is no registry, no lock file and no
state directory: a machine is identified by a name built from a prefix plus
four random bytes, and the command line finds machines again by asking Incus
for every instance and filtering on that prefix. The consequence is stated as
`INCUS-1` — the prefix is one shared namespace, and everything that claims to
find "test VMs" is really finding "instances whose name starts with
`bootstrap-test-`".

## Implementation map

| Path | Realises |
|---|---|
| `incus/src/incus/vm.py` | INCUS-1, INCUS-2, INCUS-3, INCUS-4, INCUS-5, INCUS-6, INCUS-8, INCUS-12, INCUS-13, INCUS-14, INCUS-15 |
| `incus/src/incus/ssh.py` | INCUS-1, INCUS-7, INCUS-8 |
| `incus/src/incus/constants.py` | INCUS-1 |
| `incus/src/incus/ansible.py` | INCUS-1, INCUS-9 |
| `incus/src/incus/fixtures.py` | INCUS-10 |
| `incus/src/incus/__main__.py` | INCUS-1, INCUS-11, INCUS-16 |
| `incus/src/incus/__init__.py` | INCUS-2, INCUS-7, INCUS-12, INCUS-13, INCUS-14 |
| `incus/README.md` | INCUS-1 … INCUS-16 (all sixteen) |

Every row was built by extracting the IDs actually written into the file,
not by reading intent, and every requirement `INCUS-1` to `INCUS-16` appears
above at least twice — once in the module that implements it and once in the
README that documents it to a consumer.

Two files in the package have no row. `incus/src/incus/headscale.py` is out
of scope: it carries a `TEST-8` citation and no `INCUS` one, because the only
requirement stated about what it *does* is that its release fetch is
unpinned, and that requirement is `TEST`'s. `INCUS-1` binds it all the same —
every module shipped in this package is bound by it, and `headscale.py` is
one of its violation sites — but a requirement that binds the whole package
does not earn any one module a row here. `incus/pyproject.toml` has no row for a
different reason — it is not in `tests/spec_check.py`'s `SCAN_GLOBS`, so a
requirement ID written into it would be prose rather than a citation, and the
decisions it encodes are recorded below instead.

The unit modules that supply most of this spec's evidence —
`tests/unit/test_incus_vm.py`, `tests/unit/test_ssh_keypair.py` and
`tests/unit/test_ansible_helpers.py` — also have no row. They are `TEST`'s
by the same rule that keeps `specs/testing/` out of the business of what any
individual test asserts: they belong to the unit tier, `TEST-1` and `TEST-2`
are the requirements they realise, and this spec cites them in
`**Verified:**` lines as measurements rather than mapping them as
implementation.

## Key decisions

**A `src/` layout with its own `pyproject.toml`, inside the bootstrap
repository.** The package was extracted from `tests/infra/`, where it had
been a package-relative import that worked only because pytest put the
repository root on `sys.path`. Two things changed with the move and both were
the point. The `src/` directory means an `import incus` that resolves is
necessarily resolving the installed distribution rather than a directory that
happens to be next to the interpreter's working directory, so a broken
packaging change fails immediately instead of working locally and failing for
the first consumer. The separate `incus/pyproject.toml` means the package
declares its own dependencies — `pyyaml`, plus `pytest` behind a `fixtures`
extra — rather than inheriting the bootstrap's, which pulls in `ansible-core`,
`passlib`, `hypothesis` and `pytest-ansible`. A consumer installing the
toolkit gets a YAML parser and nothing else. The cost is a second dependency
file to keep current and a root `pyproject.toml` that has to name the package
twice, once as a dependency and once as a source (`pyproject.toml`).

**Generic code in the package, this project's opinions in
`tests/integration/`.** The split is drawn at the point where a value stops
being a fact about virtual machines and starts being a fact about this
playbook. `run_playbook` takes a playbook path and a variable dictionary;
`run_bootstrap_playbook` (`tests/integration/helpers.py`) is the
wrapper that knows `site.yml` is the playbook, that `DEFAULT_TEST_VARS` are
the variables, that the public key file sits beside the private one, and that
a successful run has moved the machine's SSH port. The same line runs through
the fixtures — `clean_vm` ships in the package because an unbootstrapped
Debian machine is not a bootstrap concept, while `bootstrap_vm` and `swap_vm`
stay in this repository's conftest because they run this repository's
playbook — and through the command line, where `create`, `list`, `destroy`
and `ssh` are unconditional (`INCUS-16`) and `publish` and `images-clean` are
behind `INCUS-11`'s guard. The decision is sound and the execution is not:
`INCUS-1`
records that the values the package kept are themselves this project's, so
the split separated the *code* correctly and left the *data* on the wrong
side of the line. The earlier design document that specified the split named
`VM_NAME_PREFIX`, `IMAGE_PREFIX` and `DEFAULT_DEBIAN_VERSION` explicitly as
"generic", which is how it happened: they were classified by what kind of
thing they are rather than by what value they hold.

**A path dependency, never published.** The root `pyproject.toml` declares
`incus = { path = "incus", editable = true }` and lists
`incus[fixtures]` in its test group with no version bound; `uv.lock` records
it as `source = { editable = "incus" }`. Nothing in the repository publishes
it, and `docs/multi-repo-strategy.md:223-229` gives consumers a local
editable path or a git URL with `#subdirectory=incus` — never a package name.
That is the right shape for what the package is: it changes in lockstep with
the roles it exists to test, a consumer pinned to a released version would be
testing against a toolkit older than the images it launches, and an editable
path means a fix made while debugging a purpose repository's test is
immediately the fix in the bootstrap repository too. Those three reasons are
the decision, and none of them depends on anything outside the repository.

A fourth observation reinforces it without carrying it, and is dated because
it can change. Checked on 2026-09-21, the name `incus` on PyPI belongs to an
unrelated acoustic-simulation library at version 0.0, and the root
`pyproject.toml` declares PyPI as its default index — so a
consumer who follows the obvious instinct and runs `uv add incus` gets that
package, with no error and a confusing `ImportError` later. If that name were
ever released by this project the collision would go away and the decision
above would not move. It is also not what makes the install instructions in
`incus/README.md` and in the multi-repo document carry an explicit
`--path` or git URL: they have to, because nothing publishes this package at
all. That is also why
`__init__.py`'s claim that the package "is published from the
`server-bootstrap` repository" was wrong in a way worth correcting rather
than merely stale; it is corrected in this pass.

**`incus exec` as the working path, SSH as the thing under test.** Both are
offered (`INCUS-3`), but they are not symmetric in how the suite uses them:
every assertion in `tests/integration/` reaches its machine through `exec`,
and the SSH client is used only by `wait_ready()` to decide the machine is
up. That is deliberate rather than accidental. The bootstrap's business is
narrowing SSH, so a helper that depended on SSH to look at the result would
lose its own access at exactly the moment the thing it is testing starts
working — and would report the success as a harness failure. `exec` goes
through the Incus agent, not the network, so it survives a default-drop
ruleset, a knock gate and a `ListenAddress` bound to a tailnet interface.
The price is recorded under `## Failure modes`: `IncusVM.ssh()` itself is
dead code in this repository, and the option list it would use exists twice.

## Failure modes

- **The package is named for reuse and defaulted for one repository.**
  `INCUS-1` enumerates the sites. The consequence a reader should take from
  it is not that four constants have awkward values, but that
  `docs/multi-repo-strategy.md` documents an installation path and an API for
  purpose repositories without anywhere saying what they inherit: machines
  named `bootstrap-test-*` in a namespace shared with this repository's, a
  cached base image aliased under `bootstrap/`, a Debian-only `wait_ready()`,
  a `destroy --all` that force-deletes every prefixed machine on the daemon
  including another repository's, and a `knock()` that falls back to this
  project's sequence. None of
  it is configurable and none of it is documented as a limitation. Left as
  found; making any of it configurable is a change to the package's
  behaviour.

- **`IncusVM.ssh()` is unreachable in this repository, and its option list
  exists twice.** No file under `tests/integration/` calls it, and none sets
  `knock_sequence`, so both the SSH command path (`INCUS-3`) and the
  automatic knock built on it (`INCUS-5`) are exercised only by five unit
  tests with `subprocess.run` patched. A real `ssh` does run, in
  `wait_ready()`'s fifth phase, but that phase builds the same command
  inline at `vm.py` — the same five `-o` options, the same `-p`, the
  same `-i` — rather than calling `ssh()`. The two
  copies can diverge — a hardening option added to one, a timeout changed in
  the other — and no test in the project would fail.

- **Nothing exercises the command line at all.** `INCUS-16` records the
  measurement: no test module imports `incus.__main__`. The `site.yml` guard,
  the dispatch table, the prefix filters and `cmd_ssh`'s `os.execvp` fallback
  are covered by nothing, and the one static check that reaches them —
  `make python-typecheck` — reports `call-non-callable` at `__main__.py:364`,
  which is a real consequence of building the dispatch dictionary in two
  stages. That diagnostic and one mock-typing artifact in
  `tests/unit/test_incus_vm.py` are the project's only two; both predate
  this spec and both are left in place, because an annotation is a code
  change.

- **A private key can outlive the machine it opens.** `INCUS-8` states the
  requirement and the gap: `IncusVM` is not a context manager, so the key is
  removed only when `destroy()` is called, and what calls `destroy()` on
  every path is the fixture contract rather than the class. `TEST-4` records
  the same shape from the other side — nothing routes a new test through
  those fixtures.

- **`get_file` is offered, documented and called by nothing.** `INCUS-15` is
  documented in `incus/README.md`, in
  `docs/multi-repo-strategy.md` and in the original design, and has no caller
  and no test in this repository. Its remote-path concatenation is also
  unvalidated in both directions: a destination that does not begin with `/`
  addresses a different instance rather than failing.

- **`vm.image` stops describing the image the machine was launched from.**
  `launch()` swaps an `images:debian/…` image for the cached
  `bootstrap/internal-base-…` build in a local variable (`vm.py`) and
  never writes it back, so after a launch from the default image the
  attribute still reads `images:debian/13` while the instance was created
  from `bootstrap/internal-base-13`. `incus/README.md` documents the
  attribute as "Incus image used", which is then false for exactly the case
  the default produces. The README line is left as found and recorded here.

- **`_get_ssh_public_key_file` is private in name only.** It is imported by
  `__main__.py` and by `tests/integration/helpers.py`, so the underscore
  marks nothing and renaming it would break two callers outside the package.

- **`headscale.py` does not belong to this package.**
  It is not exported from `__init__.py`, has one consumer — this
  repository's Tailscale integration suite — and carries a `TEST-8` citation
  and no `INCUS` one. It is out of `INCUS`'s scope by that reasoning,
  but its physical location means a consumer installing the toolkit also
  installs a headscale control-server driver they will never call, and one
  that raises `RuntimeError` when `gh` is missing from `PATH`
  (`headscale.py`) rather than skipping — a failure mode
  `specs/testing/design.md` already records from `TEST`'s side.

- **`__init__.py`'s module list was stale and its publication claim was
  wrong.** Its "Key modules" section named `incus.vm`, `incus.ansible` and
  `incus.fixtures` while the package also holds `headscale.py`,
  `constants.py`, `ssh.py` and `__main__.py`, and its opening said the
  package "is published from the `server-bootstrap` repository" when it is a
  path dependency that no index carries and whose name on PyPI belongs to
  somebody else. Both are corrected in this pass, which is a docstring change
  rather than a behaviour change.

- **`specs/testing/design.md`'s implementation map claims a citation
  `fixtures.py` does not carry.** Its row reads
  `incus/src/incus/fixtures.py | TEST-3, TEST-4`. The `TEST-4` half is sound
  and this pass writes the citation into the module. The `TEST-3` half is
  not: `TEST-3` is about the integration tier running against a machine the
  suite launches, and the fixture this module ships — `clean_vm` — is used by
  no test in this repository, which `TEST-3`'s own text says. The row is left
  as found; the finding belongs to `TEST`.

## Interactions

- `TEST` — the two specs meet at exactly two surfaces and the division is by
  who is making the claim. `incus_available()` and the fixtures built on it
  are `INCUS-10`'s to provide and `TEST-4`'s to require of the whole suite,
  so a change to what `incus_available()` counts as "available" changes what
  `TEST-4` guarantees without touching a file `specs/testing/design.md` maps.
  `IncusVM` and `run_playbook` are `INCUS-2`'s, `INCUS-12`'s, `INCUS-13`'s,
  `INCUS-14`'s and `INCUS-9`'s to offer and
  `TEST-3`'s to require, since it is `TEST-3` that says every integration
  test must reach a real machine and this package that launches it. What this
  spec may not assume is that a unit test reaching this package reaches a
  machine: `TEST-2` establishes that `test_incus_vm.py` and
  `test_ansible_helpers.py` patch `subprocess.run` out, so their
  `**Verified:**` lines are evidence about a constructed command line and not
  about anything that ran. `test_ssh_keypair.py` is the exception on both
  sides — it patches nothing and really invokes `ssh-keygen` — and it still
  reaches no machine. What `TEST` may
  not assume is that `IncusVM` cleans up after itself — `INCUS-8` says the
  fixtures are what guarantee that, and `TEST-3` and `TEST-4` already
  describe those fixtures as routing rather than enforcement.

- `KNOCK` — the relationship runs one way and `specs/port-knocking/design.md`
  states it from its own side: `vm.py` appears in `KNOCK`'s implementation
  map as a **consumer**, not an implementer. Three of `KNOCK`'s requirements
  are consumed here. `INCUS-5`'s 20-second re-knock threshold is chosen
  against `KNOCK-7`'s thirty-second pass window and its 0.3-second delay
  against `KNOCK-7`'s five-second stage window; the knock loop's ordering
  depends on `KNOCK-5` and `KNOCK-6`; and `vm.py`'s fallback is a literal
  copy of `KNOCK-10`'s default sequence, accurate today and stated as a copy
  in its own docstring. This spec may assume those four values are what
  `KNOCK` says they are; it may not assume the fallback tracks them, and
  `INCUS-1` records the copy as a violation for that reason. In the other
  direction, `KNOCK` may not assume the automatic path is exercised: both
  specs measured independently that nothing in `tests/integration/` sets
  `knock_sequence` and that every knock the tier performs is an explicit
  `knock()` call.

- `IMG` — `cmd_publish` and `cmd_images_clean`, `_PUBLISH_VARS`,
  `IMAGE_VARIANTS` and the `bootstrap/` alias scheme live in this package's
  `__main__.py` but belong to `IMG`, whose spec is not yet written. The
  boundary is `INCUS-11`: this spec owns the guard that decides whether those
  two commands exist and says nothing about what they do. Two facts cross it.
  `IMAGE_PREFIX` and `DEFAULT_DEBIAN_VERSION` are read by `cmd_publish`
  (`__main__.py:242`) as well as by `IncusVM` and `clean_vm`, so `INCUS-1`'s
  finding about those constants is a finding about a value `IMG` depends on —
  the same shared ownership `specs/testing/design.md` already records for
  `TEST-8`. And `ensure_base_image()` builds and caches a
  `bootstrap/internal-base-…` image under the same `bootstrap/` alias
  namespace that `cmd_images_clean` deletes wholesale
  (`__main__.py:302-308`), so `make images-clean` removes the internal base
  image as well as the published ones and the next launch rebuilds it. That
  is a consequence of `IMG`'s prefix matching `INCUS`'s, and it belongs in
  `IMG`'s account of what `images-clean` deletes.

- `PRJ` — the six make targets that invoke this package's command line are
  `PRJ-19`'s, and the `uv` environment they run in is `PRJ-16`'s. The one
  place the two specs press on each other is `INCUS-9`: `run_playbook`
  invokes `ansible-playbook` directly rather than `uv run ansible-playbook`,
  precisely so that the package does not impose an environment manager on a
  consumer. `PRJ-16` — "THE Project SHALL run every playbook, verification
  and test command inside the `uv`-managed environment" — still holds here,
  but by the callers rather than by the function. `run_playbook` has seven
  call sites in this repository, and three of them actually run it:
  `tests/integration/helpers.py:58` and `:97`,
  reached through `make test-integration`, and `__main__.py:255` inside
  `cmd_publish`, reached through `make images` (`Makefile:119`). The other
  four are in `tests/unit/test_ansible_helpers.py` (`:75`, `:86`, `:97`,
  `:106`) with `subprocess.run` patched out, so they spawn nothing and
  `PRJ-16` does not reach them. Both entry
  points that do spawn go through `uv run` — pytest in the first case,
  `python -m incus` in
  the second — and `uv run` puts the managed environment's
  `ansible-playbook` first on `PATH`, so the subprocess inherits it. What this
  spec may not assume is that the binary is the managed one: a consumer
  calling `run_playbook` from outside such an environment gets whatever
  `PATH` offers, with no check and no error message naming the cause.
  `PRJ-17`'s "each with a minimum version" also has its one exception here —
  the root `pyproject.toml` names `incus[fixtures]` without a bound, because
  a path dependency has no version to bound, which `TEST-8` already records.

- `TS` — `headscale.py` is out of this spec's scope, but the reason the
  Tailscale integration suite can exist at all is `INCUS-2`, `INCUS-12`,
  `INCUS-3` and `INCUS-4`:
  `HeadscaleServer` drives its control server entirely through the
  `IncusVM` it is given, using `put_file` for the binary and `exec` for every
  command, and `tailscale_env` launches three machines through the same
  class and calls `wait_ready()` on each. `specs/tailscale/design.md` records
  that on a machine without Incus
  every Tailscale requirement that concerns a running system is verified by
  reading text; this spec is where that "without Incus" is decided, in
  `INCUS-10`.
