# Image publishing — Requirements

**Prefix:** `IMG`

## Purpose

A purpose repository that wants to test its own software on a hardened host
has two choices: run the bootstrap playbook in front of every test, which
costs minutes per machine, or write its own approximation of a bootstrapped
host, which is a second implementation of the thing under test and will drift
from it silently. Publishing exists to remove that choice. `make images`
bootstraps a throwaway virtual machine per variant with the project's own
playbook and freezes each result into a local Incus image, so a consumer launches a
bootstrapped host in seconds and knows exactly which run produced it.

That is also the whole of the trust argument, and it is why this spec cares
how an image is built and not only what it contains. An image is a state a
reader cannot inspect the provenance of after the fact: `bootstrap/open-13`
looks the same whether the state inside it came from `site.yml` or from a
shell script that set the same five files. The requirements below fix the
first and forbid the second, so that "this host is bootstrapped" stays a
claim about a playbook run rather than a claim about a snapshot somebody
took.

The subject below is **THE Image Publisher**: the `publish` and
`images-clean` commands of the `incus` package's command line, the two make
targets that invoke them, and the images they leave on the local Incus
daemon. Nothing here is a requirement on a fleet host. `INCUS-16` records
that no test in this repository imports the command line at all, and that
applies to these two commands as much as to the four unguarded ones — so
every `**Verified:**` line below is a reading of the implementation, and none
of them is the report of a run. Where a requirement is not upheld, or is
upheld by nothing the build does, the requirement is stated as intended and
the gap is recorded under it — and the two are labelled differently, because
a requirement the implementation breaks and one it happens not to break are
not in the same state.

## Scope

### In scope

- Publishing a bootstrapped machine as an image on the local Incus daemon,
  and the conditions under which it is published at all.
- The layers a published image is made of, and which of them the bootstrap
  playbook produced.
- The alias namespace the published images share, and what an individual
  alias says about the image it names.
- The set of variants built on each run, and the selection of the Debian
  version they are built from.
- Removing every image in that namespace again.
- What a published image carries that the build put there, and what a
  consumer therefore inherits by launching one.
- The fixed set of bootstrap variables every build supplies, and so which of
  the bootstrap's own requirements hold inside a published image and which do
  not.

### Out of scope

- Whether the two publishing commands are registered at all. That is
  `INCUS-11`: the command line adds them only where the working directory
  holds a `site.yml`, and that guard's subject, its consequences and the fact
  that nothing tests it are stated there. This spec assumes the commands
  exist and says what they do.
- The lifecycle of the machine a build runs on. Constructing and launching it
  is `INCUS-2`'s — including the swap from an `images:debian/…` image to the
  cached base image — bringing it to the point where it answers is
  `INCUS-12`'s, force-deleting it is `INCUS-13`'s, its throwaway keypair is
  `INCUS-7`'s and `INCUS-8`'s, and running a playbook against it is
  `INCUS-9`'s. `IMG-4` states only that the publisher asks for the deletion;
  `IMG-2` states only what the base image contributes to what is published.
- What the bootstrap does to a host. Every property a consumer may assume of
  a published image is some other spec's requirement about the bootstrap, and
  `IMG-13` cites those specs rather than restating them.
- Moving an image off the local daemon. Nothing in the implementation copies,
  exports or pushes an image anywhere — `grep -rn "image copy\|image
  export\|image push" incus/src/ Makefile` finds nothing — and
  `docs/multi-repo-strategy.md` describes the images as available
  locally. A registry, a signature and a retention policy are all absent, and
  none of them is specified here.
- The `images` and `images-clean` make targets as targets, and the `uv`
  environment they run in — `PRJ-19`'s and `PRJ-16`'s. This spec requires
  only that the command line they invoke behaves as stated.
- Fixing anything. Two of the requirements below are violated — `IMG-10` and
  `IMG-12`. A third, `IMG-11`, is unenforced and holds only by accident, and
  `IMG-4` records a failure path its mechanism does not reach. Each says so
  where it stands. Correcting any of them means adding a step to the build,
  changing a value the build supplies or moving a line of control flow, all
  of which are changes to behaviour, and this pass makes none.

## Security invariants

**Upholds:** none of its own. A published image's state is whatever the
bootstrap run left on the machine, so every invariant holds inside an image
exactly as far as the spec that owns it holds for the variables the build
supplied — and `IMG-13` is where those variables, and the requirements they
switch off, are written down.
**Relies on:** INV-5 — "THE Bootstrap SHALL deliver every secret to the host
only through Ansible Vault, never through the repository, a log, or a process
argument list." Publishing is the one path in this project that takes the
result of a bootstrap run and hands it to somebody else, so a secret the run
put on the machine stops being confined to the machine and becomes part of a
distributed artefact. `IMG-10` is that clause read from the image's side.
**Allowances claimed:** none.

Three of the secrets a build could leave behind are absent, and the reason in
each case is that the build never had them. **Three is a floor, not a closed
set:** the three below are the ones the brief named and the ones a reading of
the build turns up, found by listing every value the publisher passes
(`__main__.py`) and every credential `run_playbook` could
carry, and no fourth was found — but a secret this reading did not think to
look for would not appear here. The vault
password is never passed: `run_playbook` builds
`["ansible-playbook", "-i", <inventory>, <playbook>]` plus an optional
`-e @<file>` and an optional `--check` (`ansible.py`), and no vault
option appears on that path at all — `Makefile`'s `VAULT_ARGS` belongs to
`make bootstrap` and is not reached from here. The Tailscale pre-authentication
key is never minted, because `_PUBLISH_VARS` sets `tailscale_enabled` to
`False` (`__main__.py`) and both variants set it `False` again
(`__main__.py`), so `site.yml` skips the `tailscale` role
and `roles/tailscale/tasks/install.yml`'s `--authkey=` never runs. No
private key reaches the machine: the publisher passes
`_get_ssh_public_key_file(vm)`, which is the private key path
`.with_suffix(".pub")` (`ansible.py`), and the one place the toolkit
writes a key into a machine echoes `self.public_key` (`vm.py`); the
private half stays on the controller at mode `0600` and goes when the build
machine is destroyed (`INCUS-8`).

What the build does carry is a password. `__main__.py` holds a SHA-512
crypt hash with its plaintext spelled out in the comment above it, and
`roles/users/tasks/main.yml` sets it as `manual_user_password`, so it is
in `/etc/shadow` for `testuser` in both published images. That is INV-5's
"never through the repository" clause, breached on the one path that
distributes the result. It is recorded as a divergence under `IMG-10` rather
than claimed as an allowance, and the reason is that no true compensating
control exists for it: every control this project offers against a password
is in sshd — `PasswordAuthentication no` (`sshd_config.j2`),
`ChallengeResponseAuthentication no`, `PermitRootLogin no`,
`AllowGroups`, all unconditional — and INV-2's own rationale states
that the manual user's password "exists solely for local sudo escalation and
console login, paths sshd never consults". A control that bounds only the
paths the credential is not for bounds nothing, and claiming it would be
claiming more than it covers. The credential is not a small one either:
`roles/users/tasks/main.yml` grants `testuser` `ALL=(ALL:ALL) ALL`, so
any shell as `testuser` inside an image-launched machine is a shell away from
root.

## Requirements

### IMG-1 — A bootstrapped machine becomes an image

WHERE a bootstrap run against a build machine has completed successfully, THE
Image Publisher SHALL publish that machine as an image on the local Incus
daemon.

**Why:** this is the product. Everything else in this spec exists to say
which machine, under what name, and on what evidence — but without this step
the bootstrap run is a machine that gets deleted, and a consumer is back to
running the playbook itself. Publishing from the machine rather than from a
recipe is also what makes the image and the run the same object: there is no
second description of the state that could be right while the machine was
wrong.
**Verified:** `cmd_publish` (`__main__.py`) stops the machine and
then runs `incus publish <name> --alias=<alias>` with `check=True`
(`__main__.py`), so a failure to publish raises rather than being
reported as success. The stop is graceful first —
`incus stop <name> --timeout=60` — and falls back to `incus stop --force`
when that returns non-zero (`__main__.py`). Any image already
holding the target alias is deleted immediately beforehand
(`__main__.py`), which is what frees the alias for the new
image; that deletion is silent when no such image exists.

### IMG-2 — An image is a snapshot of a real bootstrap run

THE Image Publisher SHALL bring the machine it publishes to its bootstrapped
state by applying the project's own bootstrap playbook rather than any
substitute for it.

**Why:** an image is trusted for what it is claimed to be, and nobody
launching one re-derives how it was made. A build that reproduced the
bootstrapped state by any shortcut — a cached filesystem layer, a
hand-written script, a previous image patched forward — would give a
consumer a machine that is bootstrapped only for as long as the shortcut and
the playbook agree, and the day they stop agreeing is the day a purpose
repository's tests pass against a host its production counterpart no longer
resembles. Running the real playbook makes the image a verified state by
construction rather than by assertion.
**Verified:** the machine is bootstrapped by
`run_playbook(vm, playbook_path=Path("site.yml"), extra_vars=merged_vars,
cwd=Path.cwd())` (`__main__.py`), and `site.yml` is the playbook
`make bootstrap` runs. There is no second path to that state: no cached
filesystem layer, no configuration script and no image patched forward.
Nothing between that call and `incus publish` changes the machine's
configuration either — the steps in between are the return-code check, the
stop and the alias deletion (`__main__.py`).

**The playbook is not the whole image, and the difference is worth naming.**
Two things configure the machine before the playbook does, and both leave
state in the published image.

The first is the base layer. The build machine is not launched from upstream
Debian: `cmd_publish` asks for `images:debian/<version>`
(`__main__.py`), and `IncusVM.launch()` detects that prefix and
substitutes `ensure_base_image(version)` (`vm.py`), which is a locally
built `bootstrap/internal-base-<version>` image (`vm.py`). That base
image is upstream Debian plus `openssh-server` and `curl` (`vm.py`)
plus `sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config`
(`vm.py`).

The second is the readiness wait. `cmd_publish` calls `vm.wait_ready()`
(`__main__.py`) before the playbook run, and its fourth phase, `_setup_ssh`
(`vm.py`), installs `openssh-server` when `dpkg -s` reports it missing,
rewrites `PermitRootLogin` to `yes` again for an SSH user of `root` — which is
this build's, since nothing overrides `IncusVM`'s default (`vm.py`) —
creates `~/.ssh`, appends the ephemeral public key to root's `authorized_keys`,
`chown`s the directory, and restarts sshd. `IMG-12` records that the key it
writes there survives into the image.

So a published image is upstream Debian, then that base layer, then the
readiness wait's changes, then the playbook — and it carries `curl` and an
openssh-server that no requirement in this tree asks a bootstrapped host to
have. The two `PermitRootLogin yes` edits are both walked back:
`roles/ssh_hardening/templates/sshd_config.j2` writes `PermitRootLogin no`
unconditionally, with no Jinja guard on the line. This requirement is about
which playbook produces the bootstrapped state, and is met; what the layers
beneath it add is `IMG-10`'s and `IMG-12`'s to judge.

### IMG-3 — A failed bootstrap publishes nothing

WHERE a bootstrap run against a build machine returns a non-zero exit code,
THE Image Publisher SHALL NOT publish an image for that variant.

**Why:** the whole value of `IMG-2` is that an image is a *verified* state,
and a half-applied playbook is exactly the state that looks bootstrapped and
is not. An image published from a failed run would be worse than no image,
because the consumer's tests would pass on the parts that applied and the
missing hardening would surface as a production difference rather than a
build error. Separated from `IMG-1`, which says what happens on success and
would be satisfied by a publisher that also published on failure.
**Verified:** `cmd_publish` raises `RuntimeError` on a non-zero return code,
carrying the tail of the run's output for diagnosis
(`__main__.py`), before it reaches the stop, the alias deletion or
the publish. Because the raise propagates out of the loop over
`IMAGE_VARIANTS` (`__main__.py`), a failure on the first variant also
means the second is never built. The previously published image under that
alias survives, since `_delete_image` runs only after a successful run
(`__main__.py`).

### IMG-4 — The build machine does not outlive the build

THE Image Publisher SHALL destroy the machine it built an image from,
including when the build failed.

**Why:** a build machine is a fully bootstrapped host carrying a working
private key for itself, and it has no purpose once its image exists. One left
running after a failed build is a machine somebody has to find and remove by
hand, and it holds the same `testuser` credential the image does. The force
deletion itself is `INCUS-13`'s; what this requirement adds is that the
publisher always asks for it, which is the half a caller can get wrong.
**Verified:** `vm.destroy()` is called from a `finally` attached to the
per-variant `try` (`__main__.py`), so it runs on the success path, on
`IMG-3`'s `RuntimeError`, and on any exception raised by the readiness wait,
the playbook run, the stop, the alias deletion or the publish. `INCUS-8`
records that `destroy()` is also what removes the machine's ephemeral private
key from the controller.

**The launch is outside that `try`, and a launch failure leaks the machine.**
`auto_launch=True` means the machine is launched inside `IncusVM.__post_init__`
(`vm.py`), so the `IncusVM(...)` construction in `cmd_publish` is where the
launch happens, and it sits on the line above the `try:`, outside it.
`launch()` runs
`incus launch` with `check=True` (`vm.py`), and `ensure_base_image` can
fail before that. Either way the exception propagates out of the constructor
with `vm` unbound, the `finally` never executes, and nothing calls `destroy()` —
so an instance that reached the daemon before the failure is left running, and
the `SSHKeyPair` directory created at `vm.py` is left on the controller,
which is the gap `INCUS-8` describes. Read strictly, this requirement is not
violated by it — a launch that failed produced no machine an image was built
from — but the hazard its `**Why:**` names is present on that path all the
same, and a reader should not take the `finally` for a guarantee that covers
every failure. Recorded, not fixed: moving the construction inside the `try`
is a change to behaviour.

### IMG-5 — Published images share one alias namespace

THE Image Publisher SHALL give every image it publishes an alias beginning
with a single publishing prefix.

**Why:** the images are not registered anywhere — there is no manifest, no
lock file and no state directory — so the alias prefix is the only thing that
makes the set of published images a set at all. It is what lets a consumer
find them with `incus image list`, and it is what `IMG-9` deletes by. Without
it, removing this project's images from a daemon means knowing their names in
advance.
**Verified:** `IMAGE_ALIAS_PREFIX = "bootstrap/"` (`__main__.py`) is
prepended to every alias `cmd_publish` builds (`__main__.py`).

**The namespace is shared with the toolkit's internal cache.**
`BASE_IMAGE_PREFIX = "bootstrap/internal-base-"` (`constants.py`) starts
with the same prefix, so `ensure_base_image` stores its cached build inside
this namespace. That image is not a published image in the sense of this
spec — `incus/README.md` says it "is not intended for direct use by
other projects" — and the consequence for removal is recorded under `IMG-9`.

### IMG-6 — An alias names its variant

THE Image Publisher SHALL identify each image it publishes, in the image's
own alias, by the variant it was built with.

**Why:** the two variants differ in one thing a consumer has to choose
between — whether the SSH port is knock-gated — and that choice is the first
thing anyone launching an image makes. Putting it in the alias makes it a
fact about the name rather than a lookup in a document, and makes a test
fixture that names the wrong one obvious on the line where it is written.
**Verified:** `alias = f"{IMAGE_ALIAS_PREFIX}{variant}-{version}"`
(`__main__.py`), where `variant` is the key from `IMAGE_VARIANTS`. The
aliases `docs/multi-repo-strategy.md` documents to
consumers — `bootstrap/knocking-13` and `bootstrap/open-13` — carry the two
variant names.

### IMG-14 — An alias names the Debian version it was built from

THE Image Publisher SHALL identify each image it publishes, in the image's
own alias, by the Debian version it was built from.

**Why:** this is what lets images for two Debian releases coexist on one
daemon. Without it `IMG-8`'s selector would be self-defeating — each run for
a new release would overwrite the images for the old one under the same two
aliases, so a consumer could never have both, and a repository mid-migration
would have to rebuild every time it switched which release it was testing.
Split from `IMG-6`: the two halves of the alias answer different questions and
either could be dropped without the other.
**Verified:** the same f-string (`__main__.py`) interpolates `version`,
which is `args.debian` (`__main__.py`). The documented aliases
`bootstrap/knocking-13` and `bootstrap/open-13`
(`docs/multi-repo-strategy.md`) are that scheme with the default
version.

### IMG-7 — One image per variant, on every run

THE Image Publisher SHALL build one image for each variant it defines, on
every run.

**Why:** the variants exist because a purpose repository testing a service
behind port knocking and one testing a service on an open port need different
hosts, and both need the rest of the bootstrap to be identical between them.
Building the whole set on every run is what keeps that "identical" true: a
publisher that let a caller rebuild one variant alone would, the first time
somebody used it after a playbook change, leave two images on the daemon that
differ by more than the variant that names them.
**Verified:** `cmd_publish` loops over `IMAGE_VARIANTS` (`__main__.py`)
and takes no argument selecting a subset (`__main__.py`).
`IMAGE_VARIANTS` (`__main__.py`) has exactly two entries: `knocking`,
which sets `firewall_port_knocking_enabled` to `True`, and `open`, which sets
it to `False`; both set `tailscale_enabled` to `False`. Nothing is skipped
when an image already exists, so every run rebuilds both.

### IMG-8 — The Debian version is the caller's choice

THE Image Publisher SHALL take the Debian version it builds from an option
supplied on the command line.

**Why:** the images exist to be launched by other repositories, and those
repositories move between Debian releases on their own schedule. A version
fixed in the publisher would mean a consumer preparing for the next release
either waits for this repository or builds its own images, which is the
situation publishing exists to remove. `IMG-14` is what makes the choice
survive into the alias, so two versions can sit on one daemon.
**Verified:** `cmd_publish` reads `args.debian` (`__main__.py`) and uses
it both for the image it launches (`__main__.py`) and for the alias
(`__main__.py`). The `publish` subparser declares `--debian` with
`DEFAULT_DEBIAN_VERSION` as its default (`__main__.py`).

**The default is written twice and the two copies are independent.**
`Makefile` runs `uv run python -m incus publish --debian $(or
$(DEBIAN),13)`, so `make images` always passes an explicit version and the
literal `13` there is a second copy of `constants.py`'s
`DEFAULT_DEBIAN_VERSION`. Changing the constant would change
`python -m incus publish` and leave `make images` building Debian 13.

### IMG-9 — Every published image is removable in one command

THE Image Publisher SHALL offer a command that deletes every image on the
local daemon whose alias lies in the publishing namespace.

**Why:** each image is a full machine's worth of disk, every run writes two
more, and a developer who has bootstrapped a few Debian versions has no list
to work from — `IMG-5` explains why: nothing tracks them. One command that
clears the namespace is what keeps that from being a manual `incus image
list` and a sequence of deletions with the fingerprint pasted in.
**Verified:** `cmd_images_clean` (`__main__.py`) reads
`incus image list --format=json`, and for every image carrying an alias whose
name starts with `IMAGE_ALIAS_PREFIX` (`__main__.py`) deletes the image
by fingerprint with `check=True`, reporting the alias and a final count.

**It also deletes the toolkit's internal base image, and its help string does
not say so.** `BASE_IMAGE_PREFIX` (`constants.py`) begins with
`IMAGE_ALIAS_PREFIX` (`__main__.py`), so `bootstrap/internal-base-<version>`
matches the same `startswith` test and is deleted along with the published
images. The help string reads "Delete all bootstrap/* images"
(`__main__.py`), which is literally accurate and is why the effect is
easy to miss. The cost is not correctness but time: the next launch from an
`images:debian/…` image rebuilds the cache, which means launching a machine
and running `apt-get update && apt-get install openssh-server curl` over the
network (`vm.py`).

### IMG-10 — A published image carries no secret the build supplied

THE Image Publisher SHALL NOT leave, in an image it publishes, a secret that
the build passed to the machine.

**Why:** a secret on a machine is confined to that machine, and the whole
point of publishing is that the state stops being confined. Every copy of a
published image carries every credential that was in it, to every consumer,
for as long as the image exists — and unlike a host, an image cannot be
rotated, only rebuilt and redistributed. INV-5 already forbids a secret
reaching a host through the repository; this is the same rule stated where
the consequence is multiplied by the number of consumers.
**Verified:** measured by reading every step between the playbook run and
`incus publish` (`__main__.py`) and every value the build passes
(`__main__.py`). It holds for the vault password, the
Tailscale pre-authentication key and the ephemeral private key, for the
reasons set out under `## Security invariants`. It does not hold for the
manual user's password.

**This requirement is violated, at `__main__.py`.** The SHA-512 crypt
hash of `TestPassword123!` sits in the repository with its plaintext in the
comment above it, and `roles/users/tasks/main.yml` writes it to
`/etc/shadow` for `testuser` in `bootstrap/knocking-<version>` and
`bootstrap/open-<version>` alike. `roles/users/tasks/main.yml` gives
that account `ALL=(ALL:ALL) ALL`, so the credential is a root path on any
machine launched from either image. The network is covered —
`sshd_config.j2` refuses passwords outright — but the paths the credential
is actually for are not: `incus exec` reaches the machine through the Incus
agent as root without consulting sshd at all, and the VM console is not an
sshd path either. Nothing is changed here; removing the hash means changing
what the build passes, and no rotation is possible for images already
distributed.

**Nothing removes anything, as a matter of structure.** There is no scrubbing
step of any kind in the build: the sequence from the playbook to the publish
is the return-code check, the stop, the alias deletion and `incus publish`
(`__main__.py`). Whatever a run leaves on the machine is in the
image, and each of the three secrets above is absent because the build never
had it, not because anything took it away.

### IMG-11 — A published image carries no shell history from its build

THE Image Publisher SHALL NOT leave, in an image it publishes, a shell
history file written by its own build.

**Why:** a build's history is a transcript of how the machine was configured,
including any value typed rather than templated, and it is the one artefact
that turns a published image into a record of the controller that made it.
It is also the artefact most likely to be read by accident: a consumer's
first act on a new image is often to open a shell in it.
**Verified:** measured by reading the same build sequence as `IMG-10`. No
image was inspected, so this line establishes what the build does and does
not do, not what a built image contains.

**This requirement is unenforced, not violated, and the difference matters.**
Nothing in the build removes `~/.bash_history` or anything like it, so no
step of the publisher makes this true. It is very likely true anyway: every
command the build runs arrives through Ansible or through
`incus exec … -- sh -c`, and neither is an interactive login shell, so
nothing should be writing a history file in the first place. That is a
property of the transports the build happens to use, not a control the
publisher applies — it holds by accident, it is not checked anywhere, and a
build step that opened an interactive shell would break it with nothing
failing. This is why the requirement is written down rather than assumed:
`IMG-10` and `IMG-12` name content that is demonstrably in the image, and
this one names a guarantee that rests on nobody having had a reason to break
it yet.

### IMG-12 — A published image carries no host identity its consumers would share

THE Image Publisher SHALL NOT leave, in an image it publishes, host identity
material that every machine launched from that image would hold in common.

**Why:** an image is launched many times, by many consumers, and each launch
is supposed to be a distinct host. Identity material copied into the image is
identity material every one of those hosts presents as its own: a consumer
cannot tell two of its own test machines apart, host-key checking between
them means nothing, and anyone else holding the same image can present the
same identity. This is the one class of content that is harmless on the build
machine and harmful only because the machine was published.
**Verified:** no task, template or script regenerates
`/etc/ssh/ssh_host_*_key` or `/etc/machine-id`. Measured by searching
`roles/`, `site.yml`, `incus/src/` and `tests/` for `ssh_host_`,
`machine-id` and `machine_id`: on the content this spec is committed with,
that search returns exactly one hit, and it is prose — the module docstring
at `__main__.py` carrying this requirement's own citation. No executable
site matches, in a task, a template, a shell command or a Python call.

**This requirement is violated.** Neither key material nor the machine id is
regenerated at any point in the build, so both published images carry the SSH
host private keys and the `/etc/machine-id` of the machine they were built
on, and anyone holding an image holds those keys. The same structural cause as
`IMG-10`: there is no step in the build that removes or regenerates anything.

What follows for a *launched* machine is stated narrowly on purpose. The host
keys are ordinary files that nothing recreates, so every machine launched from
one image offers the same host key to an SSH client, and host-key verification
between two such machines distinguishes nothing. For `/etc/machine-id` this
spec claims only that the file is in the image: whether a launched instance
goes on to present it depends on Incus's instance setup and on systemd's
first-boot behaviour for that file, and neither was tested and neither is a
reading of this repository.

Root's `authorized_keys` is a related case that is *not* a violation of this
requirement, and the distinction is the point. `IncusVM._setup_ssh` appends
the build machine's ephemeral public key to root's `authorized_keys`
(`vm.py`), and `roles/users` writes keys only for the manual and
deploy accounts (`roles/users/tasks/main.yml`, both
`exclusive: false`), so nothing removes root's. The same public key is also
handed to both of those accounts (`__main__.py`). It is a public key,
not identity material, and its private half is destroyed with the build
machine by `IMG-4`, so it opens nothing; it is dead weight in the image
rather than a credential in it.

### IMG-13 — The variables an image was built with are fixed

THE Image Publisher SHALL build every image it publishes from one fixed set
of bootstrap variables.

**Why:** a consumer reasons about a published image by reading this
project's specs, and that only works if there is exactly one answer to "which
variables was it built with". A publisher that took its variables from an
inventory, an environment or a flag would produce images that are
indistinguishable by alias and different inside, and the consumer
documentation would have to describe a range instead of a state. `IMG-8`'s
Debian version is the single deliberate exception, and it is in the alias for
that reason.
**Verified:** `_PUBLISH_VARS` (`__main__.py`) is a module-level
dictionary of fourteen entries with no parameter, environment variable or
configuration hook that reaches it. Each build copies it, overwrites the two
SSH key file entries with the build machine's public key path
(`__main__.py`), and applies its variant's two entries
(`__main__.py`). `INCUS-1` deliberately excludes these values from its
own enumeration of this project's defaults fixed in a reusable package,
because they are read only by the guarded publishing command and belong here.

**What this means a consumer may assume, by requirement.** The bootstrap's
own specs are what hold inside an image; what follows names the ones the
variable set decides something about, and cites them rather than restating
them. **It is a floor, not a closed list** — see the paragraph after it for
what it leaves out.

sshd is hardened as `SSH-1`, `SSH-2`, `SSH-3` and `SSH-12` require — no
password from the network, no remote root, public keys only, access
restricted to the `ssh-users` group, and so `INV-2` and `INV-3` — and it
listens on port 2222 (`__main__.py`) rather than 22. The bootstrap creates
its two accounts, the manual user `testuser` and the automation user
`ansible` (`__main__.py`), as `USR-1` and `USR-4` require, deploys a
public key to each (`USR-10`) and makes both members of the SSH access group
(`USR-14`); `testuser` gets password-required sudo (`SUDO-2`) and `ansible`
gets passwordless sudo (`SUDO-3`), each through its own drop-in file. The
firewall is the default-deny ruleset `FW-3` and `FW-4` require, satisfying
`INV-4`, and every SSH rule names the port `FW-14` takes from the SSH spec.
The login and PAM policies hold at the four values `_PUBLISH_VARS` sets,
which are `LOGIN`'s and `PAM`'s to define.

**The two images differ here, and one citation applies to one of them only.**
`FW-13` — SSH accepted on every interface — is conditioned on
`firewall_tailscale_enabled` and `firewall_port_knocking_enabled` both being
false. The first is false in both images, since it defaults to
`tailscale_enabled` (`roles/firewall/defaults/main.yml`), which
`_PUBLISH_VARS` sets to `False`. The second is set directly per variant:
`True` for `knocking` (`__main__.py`) and `False` for `open`. So
`FW-13` holds of `bootstrap/open-<version>` alone.
`roles/firewall/templates/nftables.conf.j2` renders one of three SSH
branches (`if`, `elif`, `else`), and `bootstrap/knocking-<version>` takes the
middle one, the `elif` on `firewall_port_knocking_enabled`, whose SSH rule
accepts only from the knock-passed sets — the port-knocking behaviour
`KNOCK` owns, with the sequence `[7000, 8500, 9100]` (`__main__.py`), the
same literal `KNOCK-10` gives as this project's default, baked into a
distributed image where a consumer cannot change it without rebuilding.

**What the list above leaves out.** It covers the specs the fourteen
variables decide something about, and stops there. Six roles run
unconditionally in every build and are not named above at all:
`system_updates`, `networking`, `filesystem_hardening` and `system_config`
(`site.yml`), and `fail2ban` and `logging`. Whatever `UPD`, `NET`, `FS`,
`HOST`, `TIME`, `F2B` and `LOG`
require at their own defaults is inside both published images just as much as
anything above, and a consumer should read those specs too rather than
concluding from this paragraph that they do not apply.

**What a consumer may *not* assume.** Three roles do not run. `site.yml`
skips `tailscale` and `site.yml` skips `emergency_access`, both on
`tailscale_enabled` being `False`, so no `TS` requirement and no `EMRG`
requirement describes anything inside either image — the emergency access
script is in neither. `site.yml` gates `swap` on `zram_enabled` and
`disk_swap_size`, which the build sets neither of, so no `SWAP` requirement
describes either image either; the entry named `swap_enabled` in the variable
set is not what decides that, as the paragraph below records.

**Two of the fourteen entries are read by nothing.** Measured by searching
`roles/`, `site.yml` and `inventory/` for each of the fourteen names in turn:
twelve are named by at least one file there, and `target_hostname` and
`swap_enabled` are named by none. `target_hostname` is inert because the
hostname tasks read `system_hostname`
(`roles/system_config/tasks/hostname.yml`), which the build does not set, so
the published image's hostname is not the one this variable spells;
`swap_enabled` is inert because `site.yml` gates the `swap` role on
`zram_enabled` and `disk_swap_size`, and swap is absent from both images
because those two are unset rather than because this variable says so. Both
are recorded, not changed. The search covers only the literal variable names,
which is what an Ansible variable must be spelled as to be read at all.
