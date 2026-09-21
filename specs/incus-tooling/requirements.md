# Incus tooling — Requirements

**Prefix:** `INCUS`

## Purpose

`TEST-3` says every integration test runs against a Debian virtual machine
the suite launches itself, and `TEST-4` says the tier skips rather than fails
where Incus is absent. Neither is a property of `tests/` — both are
properties of the eight-module Python package under `incus/`, which is what
actually launches the machine, waits for it to answer, runs a playbook at it,
knocks on its firewall and deletes it again. This spec covers that package:
what it promises a caller, what it leaves the caller to guarantee, and where
it has quietly fixed this repository's own names and defaults into code that
was written to be reused by other repositories.

The reuse claim is the reason the spec matters more than an internal helper
would. `docs/multi-repo-strategy.md:219-231` tells purpose repositories to
install this package as a dev dependency, by local path or by git URL, and
documents an API for them to build their own fixtures on. A package with that
audience has an interface contract, and a default inside it that names
`bootstrap-test` or Debian 13 is not a cosmetic blemish — it is behaviour a
downstream repository inherits and has no documented way to change.

The subject below is **THE Test Toolkit**: the installable `incus` package
under `incus/`, its command-line interface, and the pytest fixture it ships.
Nothing here is a requirement on a bootstrapped host. A `**Verified:**` line
in this spec describes the package, and the reader should notice which kind
of evidence it rests on. Three unit modules cover the package, and only one
of them runs anything: `tests/unit/test_ssh_keypair.py`'s seven tests really
invoke `ssh-keygen` and assert on the files it writes. Of
`test_incus_vm.py`'s 19 tests, 16 patch `subprocess.run` out and assert on
the command the package *would* have run. Of the three that do not,
`test_launch_raises_with_empty_image` asserts a `ValueError` and needs no
subprocess at all, while `test_name_uses_prefix_and_random_suffix` and
`test_name_hint_is_incorporated` patch `SSHKeyPair.create` instead and assert
on the generated name. Of `test_ansible_helpers.py`'s 9, only the 4 in
`TestRunPlaybook` patch `subprocess.run`; the other 5 call `build_inventory`
and `build_single_role_playbook` directly and assert on the YAML they return,
which is neither a command nor a machine. Measured with an AST pass that
collects each test's `patch` targets, decorator and in-body alike, and counts
only those naming `subprocess.run` — counting tests that patch *anything*
gives 18 and 4, and the first of those two numbers is wrong for this claim.
`TEST-2` records the same split from the other side. Everything else in
this spec is a reading of the implementation, or a measurement of what the
integration tier does with it, and says which.

## Scope

### In scope

- That no value or assumption specific to this repository is fixed in the
  package.
- The lifecycle of one virtual machine: construction with an optional name
  hint and image, launch, readiness, and force-deletion.
- The two ways a caller reaches a machine — the machine's own SSH daemon, and
  `incus exec` through the Incus agent — and the difference between them.
- Pushing a file into a machine and pulling one out.
- Knocking automatically on a machine whose knock sequence is configured.
- Starting a service on a machine for the duration of a block and stopping it
  again.
- The throwaway SSH keypair each machine gets, and how long its private half
  lives on the controller.
- Running an arbitrary Ansible playbook against a machine, with the playbook,
  the variables and the paths all supplied by the caller.
- The availability check and the one pytest fixture the package ships.
- The command-line interface's machine-management commands, and the guard
  that hides the bootstrap-specific ones.

### Out of scope

- `incus/src/incus/headscale.py`. The module lives in this package's
  directory but is not part of its interface: `__init__.py` exports only
  `IncusVM` and `SSHKeyPair`, and the package design that created the `src/`
  layout removed `HeadscaleServer` from `__all__` deliberately. Its only
  consumer is `tests/integration/test_tailscale_integration.py`, which
  imports it directly, and the one property required of *what it does* — that
  it fetches the current upstream headscale release rather than a pinned one —
  is `TEST-8`'s and is cited from the module. What is out of scope is a
  requirement of its own; `INCUS-1` still binds it, as it binds every module
  shipped in this package, and names `headscale.py`'s hardcoded cache
  directory among its violation sites. `design.md`'s `## Failure
  modes` records that `headscale.py`, serving one
  repository's tests alone, sits
  inside a package advertised as reusable; that placement is a finding here,
  not a requirement.
- What a published bootstrap image contains, what variables build it, and the
  `bootstrap/` alias scheme — `IMG`'s, whose `cmd_publish` and
  `cmd_images_clean` live in this package's `__main__.py`. `INCUS-11` states
  the guard that decides whether those commands exist; it says nothing about
  what they do.
- What any integration test asserts, which tier it belongs to and whether it
  runs — `TEST`'s. This spec states what the package offers a fixture; `TEST`
  states what the suite built on it establishes.
- The `vm-create`, `vm-list`, `vm-destroy`, `vm-ssh`, `images` and
  `images-clean` make targets, and the `uv` environment they run in —
  `PRJ-19`'s and `PRJ-16`'s. This spec requires only that the command line
  they invoke behaves as stated.
- Fixing anything. Every divergence below is recorded and left in place: the
  project-specific defaults of `INCUS-1`, the key that can outlive its
  machine in `INCUS-8`, the untested command line in `INCUS-16` and the type
  error `INCUS-11`'s guard leaves in it. Correcting any of them is a change
  to the package's behaviour, and this pass makes none.

## Security invariants

**Upholds:** none. The invariants in `specs/project/security-invariants.md`
bind what a bootstrap run leaves on a host, and nothing in this spec runs
against a fleet host: every machine the toolkit touches is one it created
under Incus and deletes again, and every credential it creates is generated
for that machine alone.
**Relies on:** INV-5, in one direction only. INV-5 — "THE Bootstrap SHALL
deliver every secret to the host only through Ansible Vault, never through
the repository, a log, or a process argument list" — is a requirement on the
bootstrap, and this toolkit is the thing that invokes the bootstrap when a
test bootstraps a machine. The clause it could break is the last one:
`run_playbook` writes its extra variables to a JSON file inside a
`tempfile.mkdtemp` directory and passes `-e @<file>` (`ansible.py`), so the
values — including the password hash the
integration suite and the publishing command both pass — never appear in an
`ansible-playbook` argument list that `ps` would show. The directory is mode
`0700` and is removed in a `finally` (`ansible.py`), so the file
inside it, which the process umask leaves group- and world-readable, is
unreachable for as long as it exists. What the toolkit does not do is supply
a Vault: it is not a bootstrap run against a fleet host, and it passes its
test variables in clear.
**Allowances claimed:** none.

The credentials the toolkit creates are throwaway and confined to machines it
owns. Each `IncusVM` gets its own passphrase-less ed25519 keypair, generated
into a directory of its own with the private key at mode `0600`
(`ssh.py`), injected into that one machine's `authorized_keys`
(`vm.py`) and removed when the machine is destroyed (`INCUS-8`). No
key is written into the repository and none is printed: the one place a key
path reaches standard output is `print_debug_info` (`fixtures.py`),
which prints the path so a developer can reach a preserved machine, never the
key material. The headscale pre-authentication key is minted inside the test
machine and returned in memory (`headscale.py`); nothing writes it to
disk on the controller. The single credential this package does carry in the
repository is the SHA-512 hash at `__main__.py:54-58`, with its plaintext in
the comment above it — a deliberate test-only value that belongs to `IMG`'s
`_PUBLISH_VARS`, mirrors `DEFAULT_TEST_VARS` in
`tests/integration/helpers.py`, and is never used on a host outside
Incus.

## Requirements

### INCUS-1 — Nothing specific to one project is fixed in the package

THE Test Toolkit SHALL take every project-specific value and assumption it
uses — the prefixes it puts on machine names, temporary directories and image
aliases, the operating system whose package manager it drives, the image it
launches when its caller names none, and the port sequence it knocks — from
its caller rather than fixing it in the package.

**Why:** the package was separated from `tests/` for one reason, and
`docs/multi-repo-strategy.md:219-231` states it: purpose repositories install
it and write their own fixtures against its API. A default that names this
project is inherited silently by every one of them, and two of the defaults
are not passive. Because the name prefix lives in the package rather than in
the caller, every repository that installs the toolkit names its machines
identically, and `list` and `destroy --all` select on exactly that prefix —
so a `destroy --all` run in one repository force-deletes another
repository's running test machines on the same daemon, and neither has a way
to say which machines are its own. A knock sequence fixed in the package is
worse in kind: `KNOCK-10` exists
precisely because a sequence that is the same on every host is a sequence an
attacker reads once out of a public repository, and a test helper that
hardcodes this project's default teaches a consumer to keep it.
**Verified:** measured by reading the package for values that name a project.
It does not hold, at the sites enumerated below.

**This requirement is violated, in `constants.py`, `ssh.py`, `vm.py`,
`__main__.py` and `headscale.py`.**

Four of `constants.py`'s seven constants carry values specific to this
project: `VM_NAME_PREFIX = "bootstrap-test-"`,
`IMAGE_PREFIX = "images:debian/"`, `DEFAULT_DEBIAN_VERSION = "13"` and
`BASE_IMAGE_PREFIX = "bootstrap/internal-base-"`. The
other three — `VM_READY_TIMEOUT_SECONDS = 120`,
`SSH_CONNECT_TIMEOUT_SECONDS = 10` and `SSH_POLL_INTERVAL_SECONDS = 2` — are
generic and are not part of this finding. The
four are read at every point that matters: `VM_NAME_PREFIX` names every
generated machine (`vm.py:214`) and the base-image build machine
(`vm.py:109`), and filters both `list` and `destroy --all`
(`__main__.py:119`, `:149`); `BASE_IMAGE_PREFIX` names the cached image
(`vm.py:68`); `IMAGE_PREFIX` and `DEFAULT_DEBIAN_VERSION` together form
`IncusVM`'s default image (`vm.py:189`), the image `clean_vm` launches
(`fixtures.py:66-67`), the image `create` launches (`__main__.py:91`,
`:327`), and the upstream stream `ensure_base_image` reads (`vm.py:59`,
`:69`, `:239-240`). No constructor parameter, environment variable or
configuration hook changes any of the four.

Five further sites spell the prefix out again rather than reading the
constant, so they would not follow even if the constant were made
configurable: `ssh.py:41` (the keypair's temporary directory,
`bootstrap-test-{name}-`), `ssh.py:50` (the key comment,
`bootstrap-test-{name}`), `__main__.py:182` and `:183` (the two glob patterns
`ssh` searches for a saved machine), and `headscale.py:27`
(`/tmp/bootstrap-test-headscale-cache`). A sixth literal,
`__main__.py:63`'s `"target_hostname": "bootstrap-test"`, is excluded because
it is inside `_PUBLISH_VARS`, which only the guarded publishing command reads
and which `IMG` owns.

The operating system is assumed rather than defaulted, and at more than the
package manager. Three sites drive Debian's, all in `vm.py`: the base-image
build runs `apt-get update && apt-get install openssh-server curl`, and
`_setup_ssh` runs `dpkg -s` and then `apt-get install`. Four more assume the
rest of the layout: the base-image build and `_setup_ssh` each `sed`
`/etc/ssh/sshd_config` in place, so the path, the directive's spelling and
OpenSSH itself are fixed; `_setup_ssh` runs
`systemctl restart ssh || systemctl restart sshd`, which fixes systemd and
guesses between the two unit names Debian and Red Hat use; and
`ansible.py` writes `ansible_python_interpreter: /usr/bin/python3` into
every inventory the toolkit generates, so a machine whose interpreter is
anywhere else fails the Ansible run rather than being discovered. Five of the
seven run unconditionally; `_setup_ssh`'s `apt-get` runs only when `dpkg -s`
reported the package missing, and its `sed` only for an SSH user of `root`.
Those two guards
decide *whether* a Debian-specific command runs, not what it assumes, so the
consequence is the same either way: a consumer who passes a non-Debian image
gets a machine that launches and then fails in `wait_ready()`. The command
line agrees: its
flag is spelled `--debian` (`__main__.py:327`, `:356`), and `clean_vm` reads
an option named `--debian-version` (`fixtures.py:66`).

Finally, `vm.py` falls back to the literal `[7000, 8500, 9100]` when
neither an explicit `ports` argument nor `knock_sequence` is given. That one
is documented honestly where it sits — the docstring at `vm.py` says
the copy "is a copy, not a read" and that a deployment changing the sequence
must change it here too — and `INCUS-5` records that it matches `KNOCK-10`'s
default today.

**The enumeration above is a floor, not a closed set, and should be read as
one.** The named literals were found by searching every module in
`incus/src/incus/` for `bootstrap`, `debian`, `apt-get`, `dpkg` and the three
knock ports, and classifying every hit; that search is complete for those
keywords, and each hit is either listed here, a docstring or help string, or
inside the publishing commands `IMG` owns. But it cannot reach an assumption
that names no keyword, and four of the sites above — the two `sed` calls on
`/etc/ssh/sshd_config`, the `systemctl` unit-name guess, and the hardcoded
Python interpreter path — were found only by reading the modules, after two
earlier readings of this same requirement had missed them. A count here has
been wrong three times. Treat the list as the sites known to date and the
requirement as violated in kind, not as an inventory anything may be
concluded absent from. Nothing is changed: making any of these configurable
means adding a parameter or an environment hook, which is a change to the
package's behaviour rather than to a document.

### INCUS-2 — One object launches one machine

THE Test Toolkit SHALL give a caller a single object that launches one
virtual machine under Incus.

**Why:** a test that has to remember a name, a key path, an IP address and
the order in which Incus wants them told is a test that will leak a machine
the first time it raises. Folding all of that into one object is what makes
the teardown a single call, and makes the fixture that wraps it short enough
to read in one screen. `INCUS-12`, `INCUS-13` and `INCUS-14` are the rest of
what that object owes its caller; this requirement is the part that puts a
machine on the daemon in the first place.
**Verified:** `IncusVM` (`vm.py`) is a dataclass, and `launch()`
(`vm.py`) runs `incus launch <image> <name> --vm`, raising
`ValueError` on an empty image. The `auto_launch` `InitVar` calls it from
`__post_init__` (`vm.py`), so a caller may launch at construction or
in two steps. Six of `tests/unit/test_incus_vm.py`'s 19 tests cover it,
including that the base-image swap happens for `images:debian/…` and not for
`bootstrap/…`, and that no cloud-init argument is passed.

### INCUS-3 — Two ways in, and the difference is the point

THE Test Toolkit SHALL offer both a command path that goes through the
machine's own SSH daemon as the configured user on the configured port, and
one that bypasses SSH entirely and runs as root through the Incus agent.

**Why:** the two answer different questions. A bootstrapped machine's whole
subject is what its SSH daemon will and will not accept, so a test of that
has to be a real SSH connection made the way a real client makes it. But the
same test needs a way to look inside the machine before sshd is configured,
after the bootstrap has locked it down, or as a user sshd would refuse — and
a path that depends on the thing under test cannot do that. `incus exec`
goes through the Incus agent rather than the network, so it keeps working
when SSH deliberately does not.
**Verified:** `ssh()` (`vm.py`) runs the `ssh` binary with
`-p self.ssh_port`, `-i self.private_key_path` and
`f"{self.ssh_user}@{self.ip_address}"`, forcing `PubkeyAuthentication=yes`,
`BatchMode=yes`, `StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null`
and `ConnectTimeout=SSH_CONNECT_TIMEOUT_SECONDS`. `exec()` (`vm.py`)
runs `incus exec <name> -- sh -c <cmd>`, which reaches the machine as root
through the agent and passes the command to a shell so pipes and redirection
work. Both return `subprocess.CompletedProcess` and both use `check=False`,
so a non-zero exit is a value the caller asserts on rather than an exception.
Five tests in `TestIncusVMSSH` and one in `TestIncusVMExec` pin the two
command lines, with `subprocess.run` patched.

**`IncusVM.ssh()` has never connected to anything in this repository.**
Measured: `.ssh(` appears zero times in all four files under
`tests/integration/`; every integration assertion goes through `exec()` or
through a raw socket. The SSH path's only evidence is those five mocked unit
tests. A real `ssh` process does run during `wait_ready()`'s fifth phase, and
it honours `ssh_user` and `ssh_port` exactly as `ssh()` would — but it builds
the command inline at `vm.py` instead of calling `ssh()`, so the
package holds two near-identical copies of the same option list and only the
copy inside `wait_ready()` has ever been exercised against a machine. The two
can drift without any test noticing.

### INCUS-4 — A local file is pushed into a machine

THE Test Toolkit SHALL let a caller push a local file into a machine.

**Why:** some things cannot be arranged from a command's output. A binary a
test needs inside the machine has to be put there, and writing it through a
here-document over a connection mangles anything that is not text. The
transfer goes through Incus rather than `scp`, so it works on a machine whose
SSH is shut.
**Verified:** `put_file` (`vm.py`) runs `incus file push <src>
<name><dst>` with `check=True`, so a failed transfer raises
`CalledProcessError` rather than returning a result. It has no unit test. It
is used twice — `headscale.py` pushes the headscale binary, and
`test_tailscale_integration.py` pushes a file onto the tailnet peer.

It builds the remote side by plain concatenation, `f"{self.name}{dst}"`,
which produces Incus's `<instance>/<path>` form only because every call site
passes an absolute path. A relative `dst` — `"etc/hosts"` rather than
`"/etc/hosts"` — yields `myvmetc/hosts`, which addresses an instance named
`myvmetc` instead of failing. Nothing validates the argument and no docstring
mentions the requirement. `INCUS-15`'s `get_file` has the same shape and the
same gap.

### INCUS-5 — A knock-gated machine is knocked before SSH is tried

WHERE a knock sequence is configured on a machine, THE Test Toolkit SHALL
perform the knock before an SSH attempt whose last knock is older than the
window that knock buys.

**Why:** a knock-gated machine refuses the connection rather than delaying
it, so a helper that does not knock produces a failure indistinguishable from
the one a genuinely closed port produces — and a poll loop that knocks once
and then keeps trying will start failing part way through for no reason a
reader of the output could guess. Re-knocking on a threshold rather than
before every attempt keeps the packet count down while staying inside the
window.
**Verified:** both SSH paths carry the same guard. `ssh()` re-knocks when
`time.monotonic() - self._last_knock_time > 20` (`vm.py`), and
`wait_ready()`'s fifth phase applies the identical test on every iteration of
its poll loop (`vm.py`). `knock()` (`vm.py`) opens a TCP
connection to each port in order with a 0.3-second default delay,
suppressing `ConnectionRefusedError`, `TimeoutError` and `OSError` so a
closed port counts as a knock, and records `_last_knock_time` at the end.
Three of `TestIncusVMSSH`'s five tests pin the guard: it knocks when a
sequence is set and the last knock is stale, does not when the last knock was
just recorded, and does not when no sequence is configured.

The thresholds consume `KNOCK`. `KNOCK-7` bounds partial sequences by a
five-second stage timeout and passed entries by a thirty-second pass timeout;
the 20-second re-knock threshold is chosen to leave ten seconds of margin
inside the thirty, and the 0.3-second inter-knock delay to stay well inside
the five. `KNOCK-5` and `KNOCK-6` are why the loop preserves order.
`vm.py`'s fallback `[7000, 8500, 9100]` matches `KNOCK-10`'s default
today; it is a copy rather than a read, which `INCUS-1` records and the
docstring at `vm.py` states.

**As this repository is wired, the automatic path never runs.** Both guards
require `knock_sequence` to be set; `grep -rn knock_sequence tests/` finds it
in two unit tests in `test_incus_vm.py` and in a Hypothesis strategy and the
property test that draws from it in `test_firewall_properties.py`, and
nowhere under `tests/integration/`. No integration test calls `ssh()` either. Every knock
the integration tier performs is an explicit `knock()` call written into the
test — twelve of them across `test_bootstrap_integration.py` and
`test_tailscale_integration.py`. `specs/port-knocking/design.md` records the
same measurement from `KNOCK`'s side.

### INCUS-6 — A background service started for a test is stopped when the test leaves

WHERE a caller starts a service on a machine for the duration of a block, THE
Test Toolkit SHALL run the stop command when the block ends, including when
it ends in an exception.

**Why:** the integration tier's machines are session-scoped, so a service
left running by a failed test is still running for every test after it. That
turns one failure into a run whose later failures describe the leftover
rather than the cause — and the tests that use this are firewall tests, where
a stray listener is exactly the sort of thing that makes a later assertion
lie.
**Verified:** `background_service` (`vm.py`) is a
`@contextlib.contextmanager`: it runs `start_cmd` through `exec`, sleeps
`settle` seconds (default 1) to let the service come up, and wraps the
`yield` in `try: … finally: self.exec(stop_cmd)`. The `finally` is what makes
the stop unconditional against an exception raised in the body. One caller:
`tests/integration/test_bootstrap_integration.py` starts a
`python3 -m http.server 8080` inside the machine, confirms it is listening
from the inside, and asserts the firewall refuses it from the outside. The
stop's own outcome is discarded — `exec` runs with `check=False` and the
`CompletedProcess` is dropped — so a stop command that fails leaves the
service running and reports nothing.

### INCUS-7 — Each machine gets its own throwaway keypair

THE Test Toolkit SHALL generate a fresh passphrase-less ed25519 keypair for
each machine whose caller supplies none, in a directory of its own, with the
private key readable only by its owner.

**Why:** a key shared between machines makes one leaked test key a way into
every machine a run created, and a key reused between runs is a key that ends
up committed the first time somebody moves it out of `/tmp`. Generating one
per machine makes the key as disposable as the machine. Ed25519 and no
passphrase are the two choices that let `ssh` and `ansible-playbook` use it
unattended while matching the algorithm the bootstrap's own SSH hardening
expects.
**Verified:** `SSHKeyPair.create` (`ssh.py`) makes a directory with
`tempfile.mkdtemp`, which creates it at mode `0700` (measured), runs
`ssh-keygen -t ed25519 -f <dir>/id_ed25519 -N "" -C <comment>` with
`check=True`, then `chmod`s the private key to `0600` and reads the public
half off disk. `cleanup()` (`ssh.py`) removes the whole directory when
it still exists, so calling it twice is harmless. The seven tests in
`tests/unit/test_ssh_keypair.py` assert the private key exists, that its mode
is exactly `0o600`, that the public key is a non-empty string containing
`ssh-ed25519`, that two keypairs land in different directories, that cleanup
removes both the key and the directory, and that a second cleanup does not
raise. These seven are among the unit tests `TEST-2` names as running an
external binary on the controller.

The "whose caller supplies none" qualifier is not decoration. `IncusVM`'s
`ssh_key` `InitVar` (`vm.py`) is used verbatim when it is not `None`
(`vm.py`), so a caller may hand the same `SSHKeyPair` to several
machines, and the per-machine guarantee then holds for none of them. Nothing
in this repository does it outside the unit tests, which pass a `MagicMock`;
nothing forbids it either, and a caller who does it also makes `INCUS-8`'s
cleanup destructive — the first `destroy()` removes the directory the other
machines are still reading their key from.

### INCUS-8 — A throwaway key does not outlive the machine it was made for

THE Test Toolkit SHALL remove a machine's private key from the controller's
disk by the time the run that created the machine ends.

**Why:** the key is a working credential for a machine on the developer's own
Incus daemon, and it sits in a predictable directory under `/tmp` that any
process running as that user can read. One run leaving one key behind is
minor; a helper that leaks one per failed test accumulates them for as long
as the developer's `/tmp` survives, and a key the `create` command made sits
next to a `vm-info.json` naming the address it opens. The machine itself is
the obvious thing to clean up, and it is the key that gets forgotten.
**Verified:** `destroy()` calls `self._ssh_key.cleanup()` (`vm.py`) after
deleting the machine, and `cleanup()` removes the whole temporary directory
(`ssh.py:65-68`) — the private key, the public key, and the `vm-info.json`
the command line writes beside them (`__main__.py:102-107`). The unit suite
pins the removal itself: `test_cleanup_removes_private_key` and
`test_cleanup_removes_temp_directory`, plus
`TestIncusVMDestroy::test_destroy_calls_incus_delete_force`, which asserts
`cleanup` was called once.

**The class does not guarantee this; the fixtures do.** `IncusVM` is not a
context manager — `grep -n "def __" incus/src/incus/vm.py` returns
`__post_init__` and nothing else, so there is no `__enter__`, no `__exit__`
and no `__del__` — and nothing else in the module removes the key. It goes
when somebody calls `destroy()`. In this repository the fixtures always do:
`clean_vm` (`fixtures.py`), `bootstrap_vm` and `swap_vm`
(`tests/integration/conftest.py`) each wrap setup in `try/except` and
destroy on the exception path, then destroy again in teardown. A caller that
builds an `IncusVM` directly and raises before `destroy()` leaves an ed25519
private key at mode `0600` in a `/tmp/bootstrap-test-*` directory that
nothing later removes; `TEST-4` already records that nothing routes a new
test through those fixtures, and this is the cost of the same gap. The
requirement is also violated on purpose, by `KEEP_VM_ON_FAIL`, and the two
paths that honour it do not test the same thing. On the setup-failure path
the environment variable alone decides (`fixtures.py`): set it, and a
fixture that fails in `wait_ready()` or in the bootstrap prints connection
details and does not destroy, whatever the session's failure count is. In
teardown the fixture goes through `_should_keep` (`fixtures.py`), which
additionally requires the session to be carrying a failure
or an error. Either way the key is kept deliberately, because it is what
makes the preserved machine reachable.

### INCUS-9 — The playbook runner takes its subject from the caller

THE Test Toolkit SHALL take the playbook, the variables, the working
directory and the roles path of a run entirely from its caller, pass the
caller's variables through unchanged, and change no state on the object it
was given.

**Why:** this is the function that decides whether the package is reusable or
is this repository's test harness with a `src/` directory around it. A runner
that merged `site.yml`'s variables, or that reached for a workspace root, or
that quietly rewrote the machine's SSH port on success, would be usable by
exactly one repository. Keeping the defaults in the caller is what lets
`tests/integration/helpers.py` hold this project's opinions while a purpose
repository holds its own.
**Verified:** `run_playbook` (`ansible.py`) takes the playbook path,
the variables, the working directory and the roles path as arguments and
declares no variable dictionary of its own — the module contains no constant
at all. It writes a one-host inventory naming `vm.ip_address`,
`vm.ssh_port` and `vm.private_key_path` (`ansible.py`), writes
`extra_vars` to JSON verbatim — `json.dumps(extra_vars)`, no merge — and
passes `-e @<file>`, generates a temporary
single-role playbook when `roles` is given (`ansible.py`), sets
`ANSIBLE_ROLES_PATH` only when both `roles` and `roles_path`
are supplied (`ansible.py`), and removes its temporary directory in a
`finally`. It invokes `ansible-playbook` directly rather than `uv run
ansible-playbook`, so the binary comes from whatever environment the caller
is already in. `check=False` leaves the return code to the caller. Four tests
in `tests/unit/test_ansible_helpers.py`'s `TestRunPlaybook` cover it — the
other five cover `build_inventory` and `build_single_role_playbook` — and
they include
`test_does_not_mutate_vm_ssh_port`, which pins the no-mutation half against
the earlier design where the runner did mutate it.

The inventory is not empty of opinions, and the requirement is worded to say
what it does rather than to claim otherwise. `build_inventory`
(`ansible.py`) writes six host variables. Four come from the caller or
from the machine — `ansible_host`, `ansible_port` and
`ansible_ssh_private_key_file` off the `IncusVM`, and `ansible_user` from the
`user` parameter, which the caller may set and which defaults to `"root"`
(`ansible.py`). The remaining two are literals the caller cannot reach at
all: `ansible_python_interpreter: /usr/bin/python3`, and
`ansible_ssh_common_args` forcing `PubkeyAuthentication=yes`,
`IdentitiesOnly=yes`, `StrictHostKeyChecking=no` and
`UserKnownHostsFile=/dev/null`. The SSH options are properties of reaching a
throwaway machine with a throwaway key and are generic; the interpreter path
is an assumption about the guest and is one of `INCUS-1`'s violation sites.
None of them is a
playbook variable the caller supplied, and none is merged into `extra_vars`.
The bootstrap-specific
wrapper that does merge defaults and does rewrite `vm.ssh_port` lives outside
the package, at `tests/integration/helpers.py`, which is the split this
requirement exists to keep.

`_get_ssh_public_key_file` (`ansible.py:86-88`) carries a leading underscore
and is imported by two modules outside its own — `__main__.py:46` and
`tests/integration/helpers.py:11` — so the line between the package's private
and public surface is drawn in a name and contradicted in fact.

### INCUS-10 — Incus's absence is a skip, not an error

THE Test Toolkit SHALL expose one check for whether Incus can be used, and
apply it to the fixture it ships, so that an absent Incus skips a test rather
than failing it.

**Why:** `TEST-4` states the consequence for this repository's suite; the
reason it belongs here too is that the check has to be one function and it
has to live where every consumer can reach it. Two copies of "is Incus
available" drift, and a consumer that writes its own gets a different answer
from the fixture it is using in the same session.
**Verified:** `incus_available()` (`fixtures.py`) is
`shutil.which("incus")` followed by the return code of `incus list
--format=json`, defined once in the package and exported for consumers.
`clean_vm` (`fixtures.py`) calls it and `pytest.skip("Incus not
available")` before doing anything else. It is the same function `TEST-4`
counts; three of the four fixtures that call it live in `tests/` rather than
here, which is why `TEST-4` is the spec that can state the property for the
whole suite and this one can only state it for what the package ships.
`clean_vm` reads its Debian version through `request.config.getoption(name,
default)`, which returns the supplied default when the option was never
declared — measured against the installed pytest, whose `Config.getoption`
falls back whenever the attribute is missing — so the fixture works in a
consumer that never registers `--debian-version`. The option itself is
declared in this repository's `tests/integration/conftest.py`, not in
the package.

`clean_vm` is used by no test in this repository, which `TEST-3` records from
the other side, so the fixture the package ships satisfies this requirement
here without ever running. Its evidence is the definition, not a run.

### INCUS-11 — The bootstrap-specific commands appear only where the bootstrap is

WHERE the bootstrap playbook is not present, THE Test Toolkit's command line
SHALL NOT register its bootstrap-specific commands.

**Why:** the package is installed by repositories that have no `site.yml`,
no roles and no bootstrap variables. A `publish` subcommand offered there
would appear in `--help`, be reachable by anyone reading the documentation,
and fail somewhere inside Ansible rather than at the point where the mistake
was made. Hiding it keeps the command line's surface equal to what the
directory it was run in can actually support. `INCUS-16` is the other half:
what the command line offers everywhere, regardless of this guard.
**Verified:** `main()` (`__main__.py:318-364`) adds `publish` and
`images-clean` — both the subparsers and the dispatch entries — inside `if
Path("site.yml").exists():` (`:351-361`), and nowhere else. What those two
commands do belongs to `IMG`.

**The guard's subject is the process's working directory, not the package and
not a repository root.** `Path("site.yml")` resolves against the current
working directory, so the same installation offers different commands
depending on where it is invoked: `python -m incus publish` run from `tests/`
does not have the command that `make images` reaches from the repository
root, and run from a purpose repository that happens to have its own
`site.yml` it offers `publish` and points it at that repository's playbook
with this repository's `_PUBLISH_VARS`. Nothing in the package looks for a
marker of *this* repository.

**Nothing tests the guard**, which `INCUS-16` records for the command line as
a whole: no module under `tests/` imports `incus.__main__`, so neither the
`site.yml` check nor the dispatch table it feeds is exercised by anything but
a make target run by hand. The guard has left one mark that a static check
does reach. `make python-typecheck` reports `error[call-non-callable]` at
`__main__.py:364`, `commands[args.command](args)`: `commands` is annotated
`dict[str, object]` at `:343` because the two guarded entries are added
afterwards, so the dispatch is a call on a value the checker cannot see is
callable. The diagnostic predates this spec, it is one of exactly two the
project reports, and it is recorded rather than fixed because an annotation
is a change to the code.

### INCUS-12 — A launched machine is brought to the point where it accepts SSH

THE Test Toolkit SHALL bring a launched machine to the point where it accepts
an SSH connection on the configured port as the configured user.

**Why:** Incus reports a machine as `Running` long before anything inside it
will answer, and the Debian images this toolkit launches have no cloud-init,
so nothing puts a key on the machine on the caller's behalf. Without a single
call that closes that gap, every consumer writes its own poll loop, and the
ones that get it wrong fail intermittently in a way that reads as a broken
test rather than a machine that was not ready. Split out of `INCUS-2`: a
machine that launched and never became reachable has satisfied `INCUS-2` and
is useless.
**Verified:** `wait_ready()` (`vm.py`) runs five phases against one
shared deadline of `VM_READY_TIMEOUT_SECONDS` = 120 seconds: the machine
reaching `Running`, the Incus agent answering `incus exec`, a global IPv4
address appearing, `_setup_ssh()` installing openssh-server and appending the
ephemeral public key to the SSH user's `authorized_keys`, and an `ssh … echo
ready` poll. The four that poll each raise a `TimeoutError` naming which one
ran out; `_setup_ssh()` is straight-line work with no deadline of its own, so
a hang inside it is bounded only by the individual `exec` timeouts it passes.
**`wait_ready()` has no unit test at all**; it is reached only by the
integration tier, and therefore only on a machine with Incus. The evidence
above is a reading of the implementation, not a run — which is what
`TEST-2`'s tier cannot supply for this requirement and `TEST-3`'s can.

### INCUS-13 — A machine is force-deleted on request

THE Test Toolkit SHALL force-delete a machine when its caller asks, whatever
state the machine is in.

**Why:** a test machine that cannot be removed because it is running, or
because a previous run left it half-configured, is a machine somebody has to
clean up by hand — and `INCUS-8`'s key removal hangs off this call, so a
delete that refused would leave the credential behind as well. Forcing it is
right here precisely because nothing on these machines is worth preserving.
Split out of `INCUS-2`.
**Verified:** `destroy()` (`vm.py`) runs `incus delete <name>
--force`, prints a warning to stderr rather than raising when that fails, and
calls `self._ssh_key.cleanup()`. One of `tests/unit/test_incus_vm.py`'s 19
tests covers it, asserting the exact argument list and that `cleanup` was
called once. What nothing here guarantees is that `destroy()` is ever
called — that is `INCUS-8`'s finding, and it applies to the machine as much
as to the key.

### INCUS-14 — A machine's name and access key are generated when the caller supplies neither

THE Test Toolkit SHALL generate a machine's name and its access key when its
caller supplies neither.

**Why:** a fixed name means two runs on one developer's machine collide, and
a session-scoped fixture cannot be run twice; a caller forced to invent one
per machine will reach for something stable and hit exactly that. The key is
the same argument in a sharper form — `INCUS-7` wants one per machine, and
that only happens by default if the default is to make one. Split out of
`INCUS-2`.
**Verified:** `__post_init__` (`vm.py`) builds `VM_NAME_PREFIX` + an
optional `name_hint` + `secrets.token_hex(4)` when `name` is empty
(`vm.py`), and creates an `SSHKeyPair` when `ssh_key` is `None`
(`vm.py`). `ssh_key`, `name_hint` and `auto_launch` are `InitVar`s, so
none of them survives on the instance. Two of
`tests/unit/test_incus_vm.py`'s 19 tests cover the name — that it carries the
prefix and a non-empty suffix, and that a `name_hint` appears in it.
`INCUS-1` records that the prefix is this project's, and `INCUS-7` what the
generated key is.

### INCUS-15 — A file is pulled out of a machine

THE Test Toolkit SHALL let a caller pull a file out of a machine to a local
path.

**Why:** a log, a rendered configuration file or a captured ruleset is far
easier to assert against as a local file than through `cat` over a
connection, and reading it through Incus rather than `scp` works on a machine
whose SSH is shut. Split out of `INCUS-4`, whose push direction is separately
exercised; this one is not.
**Verified:** `get_file` (`vm.py`) runs `incus file pull
<name><src> <dst>` with `check=True`, so a failed transfer raises
`CalledProcessError` rather than returning a result. It has no unit test.
**It is called by nothing in this repository**: searching every `.py` and
`.md` file outside `docs/superpowers/` finds no call at all — only its
definition, the module docstring naming it, and two documentation examples,
in `incus/README.md` and `docs/multi-repo-strategy.md`. The pull direction is
offered, documented and unexercised, and its remote path is concatenated
without validation exactly as `INCUS-4` records for the push direction.

### INCUS-16 — The machine-management commands are available everywhere

THE Test Toolkit's command line SHALL register its machine-management
commands wherever it is run.

**Why:** these four are the reason a consumer has a command line at all — a
machine left behind by an interrupted run has to be findable and removable
from whatever directory the developer happens to be in, and a cleanup command
that is itself conditional is a cleanup command that is missing on the day it
is needed. `INCUS-11` is the other half: what is hidden, and where.
**Verified:** `main()` (`__main__.py:318-364`) registers `create`, `list`,
`destroy` and `ssh` — subparsers and dispatch entries alike — at
`:325-348`, outside every conditional.

**Nothing tests the command line.** No module under `tests/` imports
`incus.__main__` or any `cmd_*` function, so these four commands and the
dispatch table are exercised only by the `vm-create`, `vm-list`,
`vm-destroy` and `vm-ssh` make targets, by hand. One consequence is already
visible in the code: `cmd_list` and `cmd_destroy --all` filter on
`VM_NAME_PREFIX` (`__main__.py:119`, `:149`) while `cmd_ssh` spells
`bootstrap-test-` out in its two glob patterns (`:182-183`), so changing the
constant would break `ssh` and leave `list` and `destroy` working —
`INCUS-1`'s hazard with a concrete shape.
