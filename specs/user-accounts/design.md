# User Accounts — Design

## Approach

The role is a single flat task file shared with three other specs, and this
spec owns ten of its tasks. Those ten fall into three groups that run in
order and depend on each other in that order.

First, each account is created by one declarative call to the account module,
which carries everything about the account's identity at once: its name, its
uid, its shell, its supplementary groups and its password (`USR-1` through
`USR-8`). The two calls differ in exactly two places — the uid, and what goes
into the password field: a variable with no role default for the manual
account (`USR-3`), a literal `!` for the automation account (`USR-6`).

Second, each account's SSH key material is installed in three steps, because
three different things have to be true before sshd will honour a key: the
`.ssh` directory has to exist with the right owner and mode (`USR-9`), the
key has to be in `authorized_keys` (`USR-10`, `USR-11`), and that file has to
have the right mode (`USR-12`). The key itself is read on the controller
through a file lookup, which is what lets `PRJ-7` check the same path before
the run changes anything.

Third, the SSH access group is created and both accounts are added to it
(`USR-13`, `USR-14`). This is deliberately last of the three: it is the step
that makes the preceding work reachable, and it is additive, so it neither
depends on nor disturbs the memberships `SUDO` grants further down the same
file. `USR-15` has no tasks — it is a rule about what a repository built on
this bootstrap may do, and the group `USR-13` creates is the mechanism it
directs them to.

## Implementation map

| Path | Realises |
|---|---|
| `roles/users/tasks/main.yml` | USR-1 … USR-14 |
| `roles/users/defaults/main.yml` | USR-1, USR-2, USR-3, USR-4, USR-5, USR-7, USR-8, USR-10, USR-11, USR-12 |
| `tests/unit/test_users.py` | USR-1, USR-3, USR-4, USR-6, USR-9, USR-10, USR-12 |
| `tests/property/test_user_properties.py` | USR-1, USR-2, USR-3, USR-4, USR-5, USR-6, USR-7, USR-9, USR-10, USR-11, USR-12 |
| `docs/multi-repo-strategy.md` | USR-15 |

`roles/users/tasks/main.yml` also carries `SUDO`'s, `LOGIN`'s and `PAM`'s
tasks, and `tests/unit/test_users.py` and
`tests/property/test_user_properties.py` also carry `SUDO`'s tests. This
spec's citations name only the tasks and tests listed above; the remaining
tasks in the file belong to those specs and are cited from them.

`USR-15` is the one requirement with no task behind it: it is a rule about
what a repository built on this bootstrap may do, and the place it is
realised is the document that tells such a repository how to integrate —
which is why `docs/multi-repo-strategy.md` appears in the map alongside the
role and its tests.

## Key decisions

**1000 and 1999 are a contract with purpose repositories, not a preference.**
The uids are pinned because the repositories built on this bootstrap address
these accounts numerically — a bind mount's ownership, a container id
mapping, a directory chowned so automation can write to it. Those references
are made in a different repository, reviewed at a different time, and they
cannot be made by name, because both names are configurable by design
(`USR-2`, `USR-5`). Pinning the numbers is what lets the names stay
configurable. 1000 is the first uid a Linux system hands out and is therefore
the obvious choice for the first human account; 1999 is deliberately far
above it, at the top of the range a purpose repo would ever allocate human
accounts from, so that years of added accounts never walk into it. The cost
is real and worth stating: a host that already has an account at 1000 — a
cloud image's own default user, most commonly — cannot be bootstrapped
without removing or renumbering it first, and the run will fail rather than
work around it.

**SSH access is a group, not a list of accounts.** sshd consults exactly one
group (`USR-13`), and everything that follows from being allowed to log in
follows from membership of it (`USR-14`, `USR-15`). The alternative — naming
each permitted account in sshd's configuration — would put the access
decision in a file that this repository owns and a purpose repo would have to
edit, which means every downstream repository needs write access to the one
directive that decides whether anyone can reach the host, and a mistake in
that edit is unrecoverable in the usual case where it is the only access
path. Group membership moves the decision to a place that is additive by
construction: adding an account cannot remove another. It also keeps sshd's
configuration identical on every host regardless of how many accounts the
purpose repo adds, so the hardened configuration `SSH` deploys is the same
file everywhere and can be reasoned about once.

The seam this creates is that the group's name is shared between two roles
and defined in only one of them. `ssh_access_group` is defined in the
sshd-hardening role's defaults and consumed here with an inline fallback to
the same literal. That works, and it is the reason this spec states the
default in `USR-13` rather than deferring to `SSH`, but it means the two
spellings of `ssh-users` are kept in agreement by nothing but coincidence.
Recorded under Failure modes.

**The automation account's password is locked, not absent.** The account
module offers no "create without a password field" mode that means what one
might hope; what it offers is a value written into the shadow file. Leaving
the field unset produces whatever the underlying `useradd` defaults to, and
setting it empty produces an empty field — which is not "no password" but
"no password required", accepted outright by PAM stacks at `su` and at the
console. Writing `!` produces a field that no hash function can ever produce,
so every authenticator that compares a hash fails the comparison, whatever
its policy on empty fields happens to be. The distinction matters here more
than on an ordinary account because this is the account `SUDO` grants
passwordless escalation to: an authentication path onto it is an
authentication path to root. `!` is chosen over `*` because it is what
`passwd -l` writes, so an operator reading the shadow file sees a state the
system's own tooling produces and understands.

**The manual account's password is written once, at creation.** The account
task sets `update_password: on_create`, so a changed `manual_user_password`
is not applied to an existing account on a re-run. This is a deliberate
trade: without it, every run would rewrite the password field, which on a
host where an operator has since changed their own password at the console
would silently revert it to whatever the inventory or vault still holds. The
cost is the mirror image, and it is the more dangerous half — see Failure
modes.

**Ownership and mode are set as separate tasks from the deployment.** The
key deployment (`USR-10`) and the permission fix (`USR-12`) are two tasks
rather than one because the module that installs the key manages the file's
content, not its mode on every run. Splitting them means the mode is
re-asserted unconditionally on each run rather than only on the run that
created the file, which is what makes `INV-9` true of these files: no re-run
can leave an `authorized_keys` more readable than an earlier run left it.
`USR-9`'s directory task is unconditional for the same reason.

## Failure modes

- **The role's usage example supplies the manual account's password outside
  the vault.** `USR-3` and INV-5 require the password to come from Ansible
  Vault only. The example in the users role's defaults file passes it with
  `ansible-playbook -e`, so an operator who follows it puts the value in the
  controller's process table and in their shell history, and nothing in the
  run notices. The example inventory's vault path is unaffected.
- **A plaintext `manual_user_password` produces an account that cannot
  authenticate, and the run reports success.** The account module writes the
  variable's value into the shadow file as a hash. The defaults file's own
  usage example passes a plaintext string, so an operator following the
  documentation in front of them creates an account whose shadow entry no
  typed password can match. Nothing validates the shape of the value; the
  pre-flight check asserts only that it is defined. The failure appears at
  the console, during whatever incident made the console necessary.
- **`update_password: on_create` means a wrong password cannot be fixed by
  re-running.** Following directly from the previous item: having created the
  account with an unusable password, changing the variable and running again
  changes nothing at all, and the run reports ok rather than changed. The
  repair is outside this playbook — `passwd` at the console, or removing the
  account — and nothing in the run's output suggests it.
- **The SSH access group's name is duplicated across two roles with no check
  that they agree.** `ssh_access_group` is defined in the sshd-hardening
  role's defaults, and this role falls back to a hardcoded `ssh-users` when
  it is not set. An operator who overrides the name expecting it to apply to
  both gets whichever behaviour the variable's visibility at that point
  produces; an operator who changes the literal in one role and not the other
  gets a group created under one name and an access list gating on the other.
  sshd starts cleanly either way and refuses every login.
- **`USR-13` and `USR-14` have no test coverage whatsoever.** Neither the
  unit suite nor the property suite loads, names or asserts anything about
  the group-creation task or the membership task, and post-bootstrap
  verification checks group membership only for `wheel`. The two requirements
  on which every login depends are the two with the least evidence behind
  them: a regression that removed either task would pass the entire test
  suite.
- **The property suite generates values it never uses.** Every test in
  `tests/property/test_user_properties.py` draws usernames, uids, shells and
  file modes from Hypothesis strategies and then asserts substrings against
  the unmodified text of the role's task and defaults files. The generated
  values reach no template, no module and no assertion — they only cause the
  same file-level substring checks to run a hundred times. Several of those
  checks are additionally weakened by an `or` whose second disjunct is
  trivially true (`"manual_user_shell" in tasks_content or "shell:" in
  tasks_content`), so they cannot fail for the reason their message states.
  This is recorded, not repaired: the plan this spec was written under
  changes comments and citations only.
- **No test asserts ownership anywhere in this spec's scope.** `USR-9`'s
  directory owner and group, and the owner and group of each
  `authorized_keys` file, are checked only by assertions that the strings
  `owner:` and `group:` occur somewhere in the task file. A task that owned
  either path to root would pass every test in both suites.
- **A section comment in the role file labels this spec's group tasks as sudo
  hardening.** The `# Sudo Hardening` block comment sits immediately above
  the SSH access group tasks, which are `USR-13`'s and `USR-14`'s, not
  `SUDO`'s. It is a misplaced comment rather than a behavioural divergence,
  and correcting the boundary it implies is `SUDO`'s to do when that spec is
  written; it is recorded here so the mislabelling is not mistaken for an
  ownership claim.

## Interactions

**What this spec assumes of others:**

- `PRJ-2` — every task here creates accounts, writes into other accounts'
  home directories and creates a group, all of which need root.
- `PRJ-6` — the account names, the manual account's password variable and
  both key file paths are asserted present before the first change, so a
  missing one aborts the run rather than producing an account named nothing
  or an account with no key.
- `PRJ-7` — both public key files are stat'ed on the controller before the
  first change. This is what `USR-11` exists to make possible: because the
  key path is resolved controller-side, its absence is knowable while the
  host is still untouched, rather than after the accounts exist and sshd has
  been hardened.
- `PRJ-12` — the fixed order that puts this role before `SSH`'s, so the
  accounts, their keys and the access group all exist before sshd is
  configured to consult them.
- `INV-3`, and therefore `SSH` — root has no remote login path, which is what
  makes these two accounts the only route onto the host and every requirement
  here load bearing.

**What others may assume of this spec:**

- `SSH` — the group named by `ssh_access_group` exists and contains both
  bootstrap accounts before sshd's access list is deployed. `SSH` owns that
  list and the directive that reads the group; this spec owns the group and
  its members. `SSH` also owns the variable's only actual definition, which
  is the seam recorded under Failure modes.
- `SUDO` — both accounts exist, with the uids and names this spec fixes,
  before any `sudoers.d` file naming them is written, and the supplementary
  group memberships this spec applies are appended rather than replaced, so
  the `wheel` membership `SUDO` grants later in the same role is not undone
  by a re-run of the account tasks.
- `LOGIN` — each account has an explicitly chosen login shell (`USR-7`),
  which is what determines whether the profile-based idle timeout `LOGIN`
  deploys is read at all.
- `PRJ` — purpose repositories built on this bootstrap may rely on uid 1000
  and uid 1999 as fixed, and are directed by `USR-15` to grant further SSH
  access by adding accounts to the SSH access group rather than by editing
  sshd's configuration.
- `VRFY` — post-bootstrap verification independently confirms both accounts
  exist with their uids on the running host.
