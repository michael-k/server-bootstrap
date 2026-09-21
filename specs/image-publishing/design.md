# Image publishing — Design

## Approach

Publishing is a loop over a table of variants, and each iteration is the same
eight steps: launch a machine, wait for it to answer, run `site.yml` against
it with a fixed variable set plus the variant's two overrides, raise if the
run returned non-zero, stop the machine, delete whatever image already holds
the target alias, `incus publish` the machine under that alias, and destroy
the machine in a `finally`. Only the last seven are inside the `try` that
`finally` belongs to — the launch happens in the `IncusVM` constructor, one
line above it, which `IMG-4` records. There is no build description and no
image definition file: the artefact is a snapshot of a machine that was
configured by the same playbook a fleet host is configured by, which is
`IMG-2`, and everything else follows from that choice.

Four layers make up a published image, and only the last is the bootstrap.
The command asks for `images:debian/<version>`, but `IncusVM.launch()`
recognises that prefix and substitutes a locally built
`bootstrap/internal-base-<version>` image, which is upstream Debian plus
`openssh-server`, `curl` and `PermitRootLogin yes` — the toolkit caches that
layer to avoid an `apt-get install` on every launch, which is the reason
`incus/README.md` gives for it. Then `wait_ready()` runs, and its
`_setup_ssh` phase configures sshd and installs the ephemeral public key in
root's `authorized_keys`. Only then does the playbook run. So the chain is
upstream Debian, then that base layer, then the readiness wait, then the
bootstrap. It matters for what the image contains: `curl` and an
openssh-server are in every published image without any requirement in this
tree asking for them, and the readiness wait's key is in a file the playbook
never touches. The two `PermitRootLogin yes` edits are both walked back by
the playbook, which writes `PermitRootLogin no` unconditionally. Saying "the
image is upstream Debian plus the bootstrap" would be shorter and wrong, and
`IMG-2` is scoped to the bootstrapped state for that reason.

Reuse of the toolkit is what makes the command small and is also where its
sharper edges come from. The build machine is an ordinary `IncusVM`, so
launch, readiness, the throwaway keypair and deletion are `INCUS-2`,
`INCUS-12`, `INCUS-7`, `INCUS-8` and `INCUS-13` rather than anything written
here, and the playbook runs through `INCUS-9`'s caller-driven
`run_playbook`. Three edges come with it. The readiness wait does not merely
wait: its `_setup_ssh` phase installs `openssh-server` when it is missing,
re-enables `PermitRootLogin`, appends the ephemeral public key to root's
`authorized_keys` and restarts sshd — so the machine is configured twice, once
before the playbook and once by it, and the key it writes is in a file the
playbook never touches and is published with the image (`IMG-2`, `IMG-12`).
The base-image cache lives under the same `bootstrap/` alias prefix the
published images use, which is why `images-clean` removes it too (`IMG-9`).
And because `auto_launch` puts the launch in the constructor, the launch sits
outside the `try` whose `finally` destroys the machine (`IMG-4`).

Nothing is removed from a machine before it becomes an image. There is no
scrubbing step, not for credentials, not for history, not for host identity,
and the three secrets a build could have leaked are absent only because the
build never held them: no vault option is ever passed to `ansible-playbook`,
Tailscale is disabled so no pre-authentication key is minted, and only the
public half of the ephemeral keypair ever leaves the controller. Three is a
floor there, as `requirements.md` records — no fourth was found, but the
search was a reading rather than an inspection of an image. What is
present is present for the same structural reason, and the three requirements
over that absence are in two different states, which is worth keeping
apart. `IMG-10` and `IMG-12` are violated: a password hash from the repository
and the build machine's host keys are demonstrably in both images. `IMG-11` is
unenforced rather than violated — nothing removes a shell history file, and
nothing writes one either, because every build command arrives over a
non-interactive transport, so the requirement holds by accident and no step of
the build makes it hold.

## Implementation map

| Path | Realises |
|---|---|
| `incus/src/incus/__main__.py` | IMG-1, IMG-2, IMG-3, IMG-4, IMG-5, IMG-6, IMG-7, IMG-8, IMG-9, IMG-10, IMG-11, IMG-12, IMG-13, IMG-14 |
| `Makefile` | IMG-8, IMG-9 |
| `docs/multi-repo-strategy.md` | IMG-2, IMG-6, IMG-7, IMG-12, IMG-13, IMG-14 |

Every row lists the IDs actually written into that file, checked by
extracting them from the file rather than by reading intent. The module is
the only place all fourteen appear, which is expected: `__main__.py` holds
both commands, both constants and the variable set, and three of the fourteen
are requirements the implementation does not meet or does not enforce, so
their citation is the record of the gap rather than of the mechanism.

`incus/src/incus/vm.py` and `incus/src/incus/constants.py` have no row even
though a published image's content depends on both. `ensure_base_image` and
the launch-time swap are `INCUS-2`'s, and `BASE_IMAGE_PREFIX` is one of
`INCUS-1`'s violation sites; this spec reads those two modules for evidence —
`IMG-2`'s account of the base layer and `IMG-9`'s of what `images-clean`
deletes both come from `vm.py` — but reading a file is not implementing a
requirement in it, and adding an `IMG` citation to either would claim the
toolkit implements something it does not know about.

The tests have no row for a simpler reason: there are none. `INCUS-16`
records that no module under `tests/` imports `incus.__main__` or any `cmd_*`
function, and that covers `cmd_publish` and `cmd_images_clean` exactly as it
covers the four unguarded commands. Every `**Verified:**` line in
`requirements.md` is therefore a reading of the implementation, and this spec
has no requirement whose evidence is a run.

## Key decisions

**The alias is `bootstrap/<variant>-<version>`, and nothing else records that
an image exists.** The scheme carries three things in one string, and each is
load-bearing. The `bootstrap/` prefix makes the images a set: there is no
manifest, no lock file and no state directory, so a prefix is the only thing
`images-clean` can select on and the only thing a consumer can list by
(`IMG-5`, `IMG-9`). The variant distinguishes two images that are otherwise
identical, so a consumer picks a knock-gated or a directly reachable host by
name rather than by reading a document (`IMG-6`). The version lets images for
two Debian releases coexist on one daemon (`IMG-14`), which `IMG-8`'s selector
would otherwise make impossible — a publisher that dropped the version from
the alias would have each run overwrite the other release's images. The two
halves are separate requirements because either could be dropped without the
other, and each would cost something different.

The cost is that the namespace is shared with the toolkit's internal
base-image cache, whose prefix is `bootstrap/internal-base-`, and no part of
the scheme separates "an image other projects should launch" from "an image
this toolkit built for itself". The two are told apart today only by a
sentence in `incus/README.md`. A separate prefix for the cache would fix it
and is a change to the toolkit's behaviour, so it is recorded under
`## Failure modes` and left.

**The image is built by running the real playbook, and the build is
deliberately slow because of it.** The alternative was available and would
have been faster: the state these images hold is a set of configuration files
and a handful of accounts, and a script that wrote them directly would
produce a machine that looks the same and builds in a fraction of the time.
It was not taken, and the reason is that an image is consumed by people who
cannot inspect how it was made. A shortcut is correct exactly as long as
somebody keeps it in step with the playbook, and the failure mode when it
drifts is silent in the worst possible way — a purpose repository's tests go
on passing against a host that no longer resembles what the bootstrap
produces, so the divergence is discovered in production rather than in CI.
Running `site.yml` makes the image a verified state by construction: there is
one description of a bootstrapped host, and the image is a snapshot of it
(`IMG-2`). `IMG-3` is the other half of the same decision — a partially
applied playbook is the one thing that would put an unverified state behind
a verified name, so a non-zero return code publishes nothing.

**Both variants are always built, and every run rebuilds both.** The command
takes no argument selecting a subset, and it skips nothing that already
exists. The reason is that the variants are meant to differ by exactly one
thing — whether the SSH port is knock-gated — and any mechanism for building
one alone is a mechanism for leaving the other behind across a playbook
change, at which point two images that are documented as differing in one
variable differ in whatever else moved. The cost is that a developer who
wants only `bootstrap/open-13` pays for two full bootstrap runs, and that
`make images` is never a cheap command.

**The image never leaves the local daemon.** `incus publish` writes into the
local image store, and nothing in the implementation copies, exports or
pushes an image anywhere; the design that introduced these commands put
remote registries out of scope, and `docs/multi-repo-strategy.md:203`
describes the images as available locally. That is what makes the current
build tolerable at all — an image containing a repository-known password
(`IMG-10`), shared host keys (`IMG-12`) and an unscrubbed filesystem is an
image whose blast radius is one developer's machine. It is a scope decision,
not a control: nothing in the code prevents an image from being exported, and
if publishing to a shared registry is ever wanted, `IMG-10` and `IMG-12` have
to be met first rather than documented.

## Failure modes

- **There is no scrubbing step, so the image is whatever the run left.**
  `IMG-10`, `IMG-11` and `IMG-12` are three faces of one structural absence:
  between the playbook and `incus publish` the command checks a return code,
  stops the machine, frees the alias and publishes. Nothing inspects the
  filesystem. The consequence is that each of those three requirements holds
  only where the build never created the thing in the first place. `IMG-10`
  and `IMG-12` name things it did create, so both are violated; `IMG-11` names
  one it does not create, so that one holds — but by accident of the
  transports the build uses, not by anything the publisher does. None of the
  three can be fixed by correcting a line.

- **A password from the repository is in both images, and its plaintext is in
  the comment above it.** `IMG-10` states the requirement and the violation.
  The part worth carrying forward is that the account holding it has
  unrestricted sudo, and that the controls this project has against a
  password are all in sshd, while the paths the password is for — the console
  and `incus exec` — consult sshd not at all. The images being local-only
  bounds the damage; it does not address it, and it is a property of how the
  images are used rather than of what is in them.

- **Every machine launched from an image offers the same host key.**
  `IMG-12`: the SSH host private keys and `/etc/machine-id` are published with
  the image and nothing in the build regenerates either, so host-key
  verification between a consumer's own test machines distinguishes nothing
  and anyone holding the image holds those keys. The requirement scopes the
  `/etc/machine-id` half narrowly — the file is in the image, and whether a
  launched instance goes on to present it is Incus and systemd behaviour this
  spec did not test.

- **A launch that fails leaks the machine and its key.** `IMG-4`: the
  `finally` that destroys the build machine hangs off a `try` that opens one
  line after the `IncusVM` is constructed, and `auto_launch=True` means the
  launch happens inside that constructor. An exception there leaves the name
  unbound, so nothing calls `destroy()` — an instance that reached the daemon
  stays, and the throwaway keypair directory stays on the controller.
  `INCUS-8` records the same shape for callers of the class generally.

- **`make images-clean` deletes the toolkit's base-image cache as well.**
  `IMG-9` records it. `BASE_IMAGE_PREFIX` begins with `IMAGE_ALIAS_PREFIX`,
  so the `startswith` test that selects published images selects the cache
  too, and the command's help string — "Delete all bootstrap/* images" — is
  literally accurate, which is exactly why the effect is easy to miss. The
  next launch from an upstream image rebuilds the cache, which means a VM
  launch and an `apt-get install` over the network.

- **The Debian default exists twice and only one copy is the constant.**
  `IMG-8` records it: `make images` passes `--debian $(or $(DEBIAN),13)`, so
  the literal in the Makefile, not `DEFAULT_DEBIAN_VERSION`, is what decides
  what `make images` builds. Changing the constant moves
  `python -m incus publish` and leaves the make target where it was.

- **Two of the build's fourteen variables are read by nothing.** `IMG-13`
  records the measurement. `target_hostname` does not set the image's
  hostname, because the hostname tasks read `system_hostname`; `swap_enabled`
  does not disable swap, because the `swap` role is gated on `zram_enabled`
  and `disk_swap_size`. Neither is harmful and both are misleading in the
  same way: a reader checking what a published image was built with reads two
  values that had no effect.

- **Nothing exercises either command.** `INCUS-16` establishes it for the
  command line as a whole, and these two commands are inside the `site.yml`
  guard, so they are even further from anything a test reaches. Every claim
  in this spec is a reading. The practical consequence is that the first
  report of a broken build is a developer running `make images` by hand,
  after a playbook change has already landed.

## Interactions

- `INCUS` — the boundary is drawn by `INCUS-11` and stated in
  `__main__.py`'s module docstring: that spec owns whether `publish` and
  `images-clean` are registered, this one owns what they do. Everything the
  build machine is, is the toolkit's: `INCUS-2` launches it and performs the
  swap from `images:debian/…` to the cached base image, `INCUS-12` brings it
  to the point where it answers, `INCUS-7` and `INCUS-8` give it and then
  remove its throwaway keypair, `INCUS-13` force-deletes it, and `INCUS-9`
  runs the playbook the publisher names. Three facts cross the line in the
  other direction and each is read off the toolkit rather than assumed.
  `INCUS-12`'s readiness wait appends the ephemeral public key to root's
  `authorized_keys`, and no bootstrap task touches root's, so that key is in
  every published image — inert, since `INCUS-8` destroys its private half
  with the machine, but present. The base image `INCUS-2`'s launch substitutes
  is the second of `IMG-2`'s four layers, and is why a published image
  carries `curl`; `INCUS-12`'s readiness wait is the third.
  And `INCUS-1`'s finding about `IMAGE_PREFIX` and `DEFAULT_DEBIAN_VERSION`
  is a finding about values this spec depends on: they decide which upstream
  stream a build follows. What this spec may not assume is that anything here
  is tested — `INCUS-16` measured that nothing imports the command line, and
  that is the evidence basis for every requirement above.

- `PRJ` — the `images` and `images-clean` make targets are `PRJ-19`'s, and
  the `uv` environment they run in is `PRJ-16`'s. The one place the two specs
  press on each other is the Debian default: `IMG-8` requires that the
  version come from the command line, and `Makefile` satisfies it by
  always passing one — which is also what makes the literal there a second
  copy of the constant. `specs/incus-tooling/design.md` already records that
  `run_playbook`'s `ansible-playbook` is the managed one here only because
  `make images` enters the environment through `uv run`; the same holds for
  this spec's playbook run, which is the same call site.

- The consuming repositories — what a published image promises is not this
  spec's to state, and `IMG-13` is careful to cite rather than restate. The
  requirements the fourteen variables decide something about are `SSH-1`,
  `SSH-2`, `SSH-3` and `SSH-12` for sshd; `USR-1`, `USR-4`, `USR-10` and
  `USR-14` for the two accounts, with `SUDO-2` and `SUDO-3` for their sudo
  grants; `FW-3`, `FW-4` and `FW-14` for the firewall, plus `FW-13` for
  `bootstrap/open-<version>` **only** — the `knocking` image sets
  `firewall_port_knocking_enabled` true, which is one of the two flags
  `FW-13` requires to be false, so that image takes the template's
  knock branch instead and its SSH rule is `KNOCK`'s, with `KNOCK-10` the
  source of its sequence. `LOGIN` and `PAM` hold at the four policy values
  the build passes.

  **That list is a floor and `IMG-13` says so.** Six roles run unconditionally
  in every build and appear nowhere in it — `system_updates`, `networking`,
  `filesystem_hardening`, `system_config`, `fail2ban` and `logging` — so
  `UPD`, `NET`, `FS`, `HOST`, `TIME`, `F2B` and `LOG` describe state inside
  both images too, at their own defaults. What a consumer may *not* assume is
  narrower and is closed: `TS`, `EMRG` and `SWAP` describe nothing in either
  image, because `site.yml` skips all three
  roles for the values this build supplies.

- `KNOCK` — the relationship is one-way and narrow. `KNOCK-10` says the
  sequence is an inventory decision precisely because a sequence that is the
  same on every host is one an attacker reads out of a public repository, and
  `bootstrap/knocking-<version>` is built with that requirement's own default
  written into the publisher (`IMG-13`). The image is therefore the one
  artefact in this project where the knock sequence is not an inventory
  decision at all: it is fixed at build time, identical for every consumer,
  and changeable only by rebuilding. `KNOCK` may not assume otherwise of a
  machine launched from this image, and this spec does not claim the sequence
  tracks `KNOCK-10`'s default — today it is a copy of it, which is the same
  shape `INCUS-1` records for the toolkit's own fallback.
