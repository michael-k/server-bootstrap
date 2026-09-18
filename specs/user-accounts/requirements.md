# User Accounts — Requirements

**Prefix:** `USR`

## Purpose

This spec covers the two accounts every bootstrapped host gets and the SSH
key material that reaches them: a manual access account for a human
administrator, an automation account the playbook itself logs in as, the
fixed uids both are pinned to, the `.ssh` directory and `authorized_keys`
file each one needs before sshd will honour a key, and the group membership
that is the only thing sshd's access list lets through. Between them these
accounts are the entire set of principals who can reach the host once the
run finishes: root's remote path is gone (INV-3) and passwords are not
accepted at any network authenticator (INV-2), so an account that does not
exist here, or a key that did not land here, is an account and a key that
cannot reach the host at all.

## Scope

### In scope

- The manual access account's existence, its fixed uid, its configurable
  name, and the password it is created with.
- The automation account's existence, its fixed uid, its configurable name,
  and the absence of any usable password on it.
- Each account's configurable login shell and configurable supplementary
  group memberships.
- Each account's `.ssh` directory, its ownership and its mode.
- Deploying each account's public key into its `authorized_keys` file, from
  a configurable key file path resolved on the Ansible controller.
- The mode of each `authorized_keys` file (`authorized_keys_mode`).
- Creating the SSH access group (`ssh_access_group`, `ssh-users`) and making
  both accounts members of it.
- The rule that an additional account is granted SSH access by joining that
  group, not by editing sshd's access configuration.

### Out of scope

- Every sudo and `su` concern: the per-account `sudoers.d` files, the sudo
  security defaults, the `wheel` group and the `pam_wheel` restriction on
  `su`. Owned by `SUDO`, which also installs the `sudo` package.
- `login.defs`, `securetty`, console TTY restriction and the shell idle
  timeout — owned by `LOGIN`. This spec decides which shell an account gets;
  what that shell then enforces is `LOGIN`'s.
- Account lockout (`faillock`) and resource limits (`limits.d`) — owned by
  `PAM`.
- sshd's own configuration: which authentication methods it accepts, that it
  denies root, and the `AllowGroups` directive that consults the group
  `USR-13` creates. Owned by `SSH`. This spec supplies the principals and the
  group; it does not configure the service that reads them.
- Pre-flight validation that the account names, the password variable and
  both key file paths are defined, and that the key files exist on the
  controller, owned by `PRJ-6` and `PRJ-7`.
- Where this role sits relative to the rest of the run, owned by `PRJ-12`.
- Independent, post-bootstrap confirmation that the accounts exist with their
  uids on a live host, owned by `VRFY`.
- Accounts created by repositories built on this bootstrap for their own
  purposes. This spec fixes the two bootstrap accounts and the group a
  purpose repo extends; it does not enumerate that repo's accounts.

## Security invariants

**Upholds:** INV-2, INV-5
**Relies on:** INV-3
**Allowances claimed:** none

INV-2 requires that no network-facing authenticator ever accepts a password.
Sshd's side of that is `SSH`'s; this spec holds the account side, which is
what makes the invariant true rather than merely configured. `USR-6` leaves
the automation account with a password field no password can satisfy, so
there is no credential to accept even if some future authenticator were
willing to ask for one. `USR-3`'s password on the manual account is the
deliberate exception, and it is an exception only because of where it is
used: local sudo escalation and console login, both paths sshd never
consults. The public keys `USR-10` deploys are the only credential either
account presents over the network.

INV-5 is upheld by `USR-3`, which takes the manual account's password from
Ansible Vault only. The users role's own usage example contradicts it, and
`USR-3` records that divergence.

This spec relies on INV-3 rather than upholding it. Removing root's remote
login path is `SSH`'s work, and it is what makes these two accounts load
bearing: with root unreachable, an operator's entire route onto the host runs
through the manual account's key, its `authorized_keys` file, and its
membership of the SSH access group. Every requirement below that looks like
housekeeping — a directory mode, a file mode, a group membership — is on that
single route, and INV-3 is what removes the fallback that would otherwise
make a mistake in one of them recoverable.

## Requirements

### USR-1 — Manual access account created with uid 1000

THE Bootstrap SHALL create the manual access account with uid 1000.

**Why:** uid 1000 is a contract with the repositories that build on this
bootstrap. They ship bind mounts, id mappings and file ownership that name
the administrator numerically rather than by name, because the name is
configurable and the number is not. If the account is created with whatever
uid the system next hands out — because a cloud image already consumed 1000
for its own default account, or because someone created the account by hand
before the run — nothing here fails: the account exists, logins work, sudo
works. The breakage is elsewhere and later, when a purpose repo's `chown`
lands on a uid nobody owns and the files it creates are unreadable by the
person it created them for, discovered whenever someone next tries to open
one.
**Verified:** the account is created from `manual_user_uid`, which the role's
defaults define as 1000; the unit suite parses the task and asserts the uid
is either the literal or that variable reference. Post-bootstrap verification
reads `getent passwd` on a live host and asserts the uid appears in the
entry, and the integration suite confirms the same on a real bootstrapped VM
— those are the only checks that observe an account rather than a task file.
The property suite's assertion is a substring search for `manual_user_uid`
anywhere in the role's task text, which would pass if the variable appeared
in an unrelated task.

### USR-2 — Manual access account name configurable

THE Bootstrap SHALL accept `manual_user_name` as a configurable variable
naming the manual access account.

**Why:** the account name is the half of the manual credential an attacker
can see. A key is unguessable; the name it belongs to is offered up by any
service that reports account names, and a fleet whose administrator is called
the same thing on every host hands out one half of every credential for free.
Configurability is what lets an operator choose otherwise — but the silent
part is the default. `manual_user_name` defaults to `admin`, which is
precisely the name an untargeted scan tries first, and a host left at the
default is indistinguishable, in the run's output, from one where the
operator considered the question and chose that name deliberately. Nothing
warns, because from the playbook's point of view nothing is wrong.
**Verified:** the account task names the account from `manual_user_name` and
the role's defaults define it as `admin`; the property suite asserts the
variable is referenced in the task file and defined in the defaults file. No
test substitutes a name and confirms the resulting account — the property
suite draws random usernames from a Hypothesis strategy but never feeds them
to anything, so every generated example runs the same substring checks
against the same unchanged file.

### USR-3 — Manual access account password supplied from the vault

THE Bootstrap SHALL set the manual access account's password from
`manual_user_password`, a value supplied from Ansible Vault only rather than
carried as a role default or passed at run time.

**Why:** this password is the manual operator's sudo credential and their
console fallback — the way back in when the network path is gone. INV-5
requires every secret to reach the host through Vault only, never through
the repository, a log or a process argument list. A role default would put
this fleet-wide credential in version control, and a value passed with
`ansible-playbook -e` sits in that process's argument list for the length of
the run. The silent failure is on the other side of
the variable: the account module writes the value into the shadow file as a
password *hash*, so a plaintext value — which is exactly what the defaults
file's own usage example shows — produces an account whose shadow entry is a
string no typed password can ever hash to. Every task succeeds, the account
exists, and the operator learns their password does not work at the moment
they need it: at the console, mid-incident, with remote root already gone
(INV-3). A correction on the next run does not help either, because the
password is written only when the account is created; a re-run leaves the
unusable entry exactly as it is.
**Verified:** the account task sets `password` from `manual_user_password`
with `update_password: on_create`, and the variable has no role default — it
is documented in the defaults file, and `PRJ-6` asserts it is defined before
the first change to the host. The unit suite
parses the task and asserts both the variable reference and the `on_create`
policy. Nothing checks that the supplied value is a hash rather than a
plaintext string, nothing exercises the account module, and the property
suite's assertion that the variable is "documented in defaults" is satisfied
by a comment, since the defaults file deliberately defines no value for it.

**The role's own documentation contradicts this requirement.** The usage
example in `roles/users/defaults/main.yml` supplies the password with
`ansible-playbook -e "manual_user_password=..."`, which bypasses the vault
and puts the value in a process argument list. The example inventory takes
the vault path. Nothing checks which channel a run used: the pre-flight
check asserts only that the variable is defined. The image publisher also
supplies the value outside the vault, which `IMG-10` records. Nothing is
changed here; see `design.md`'s `## Failure modes`.

### USR-4 — Automation account created with uid 1999

THE Bootstrap SHALL create the automation account with uid 1999.

**Why:** 1999 is the same kind of contract as `USR-1`'s 1000, chosen to sit
far above the range a system hands out for human accounts so that a purpose
repo, or a later administrator, can add accounts for years without ever
colliding with it. A drifting uid here is worse than a drifting uid on a
human account, because automation is granted access by number in exactly the
places where it matters most — a directory chowned to 1999, a socket
restricted to it, an id mapping in a container. If the number moves, those
grants do not fail; they succeed, pointing at whichever principal now holds
1999. The grant still works, and now it works for someone else.
**Verified:** the account is created from `deploy_user_uid`, which the role's
defaults define as 1999; the unit suite parses the task and asserts the uid
is either the literal or that variable reference, post-bootstrap verification
reads `getent passwd` on a live host, and the integration suite confirms the
uid on a real bootstrapped VM. The property suite's assertion is the same
whole-file substring search described under `USR-1`.

### USR-5 — Automation account name configurable

THE Bootstrap SHALL accept `deploy_user_name` as a configurable variable
naming the automation account.

**Why:** the name has to be configurable because it is a coordination point
rather than a local choice: the controller's inventory, any purpose repo that
grants this account access to something, and the account on the host all have
to agree on one string. Fixing it in the role would mean a fleet that already
runs automation under a different name could not be bootstrapped without
patching the role. The silent failure is the same shape as `USR-2`'s and
lands harder: the default is `ansible`, an account name that announces
exactly what it is for and what it holds — this is the account with
passwordless sudo — to anyone who can enumerate accounts.
**Verified:** the account task names the account from `deploy_user_name` and
the role's defaults define it as `ansible`; the property suite asserts the
variable is referenced in the task file and defined in the defaults file. As
with `USR-2`, no test substitutes a name and observes the resulting account.

### USR-6 — Automation account has no usable password

THE Bootstrap SHALL create the automation account with a password field that
no password can satisfy.

**Why:** this is the account the playbook itself logs in as, and `SUDO` gives
it passwordless escalation — so anything that can authenticate as it owns the
host outright. Its key is the only credential it should ever present, and the
password field is where a second one could appear without anyone deciding to
add it. The silent failure is the difference between an invalid hash and an
empty one: an empty password field is not "no password", it is "no password
required", and PAM stacks will happily let `su - ansible` from any local
account, or a console login, straight through. Nothing about the host looks
different — the account is there, the key works, the run reported success —
and the extra way in exists only for whoever thinks to try it. Writing a
value no hash function can produce closes that without relying on any
authenticator's interpretation of an empty string.
**Verified:** the account task sets `password` to the literal `!`; the unit
suite parses the task and asserts exactly that value, and the property suite
asserts the same literal appears in the role's task text. No test inspects
the shadow file on a live host, and nothing attempts a password
authentication against the account and observes it refused — the lock is
verified as a module parameter, not as an outcome.

### USR-7 — Login shell configurable for each account

THE Bootstrap SHALL accept each bootstrap account's login shell as a
configurable variable, defaulting to `/bin/bash`.

**Why:** an unset shell is not an absent shell — the account module falls
back to whatever the system's account defaults name, which on a stock image
is a shell an operator did not choose and may not have tested against. The
silent part is what else rides on that choice. The idle timeout `LOGIN`
deploys is a profile snippet, and a login shell that does not read the
profile directory simply never applies it: the account keeps its session
open indefinitely, the timeout file is present and correct on disk, and
nothing anywhere connects the two. Setting the shell explicitly, from a
variable with a stated default, is what makes that dependency a decision
instead of an inherited accident.
**Verified:** both account tasks set `shell` from their account's shell
variable, and the role's defaults define both as `/bin/bash`. The property
suite's assertion is `"manual_user_shell" in tasks_content or "shell:" in
tasks_content`, whose second disjunct is true of any task file that sets a
shell at all — so the assertion cannot fail for the reason its message
gives. Nothing asserts either default value, and no test creates an account
with a non-default shell.

### USR-8 — Supplementary group memberships configurable for each account

THE Bootstrap SHALL accept each bootstrap account's supplementary group
memberships as a configurable variable, defaulting to none.

**Why:** a repository built on this bootstrap needs to put these accounts
into groups this repository knows nothing about, and this variable is where
that happens. The silent failure is not in whether memberships can be added
but in how they are applied: the account module *replaces* an account's
supplementary groups unless told to append, and this variable defaults to
the empty list. A run that replaced rather than appended would strip every
membership granted outside it — including the SSH access group of `USR-14`
and the `wheel` membership `SUDO` grants, both of which are added by later
tasks in this same role. Nothing would report that: the accounts would still
exist, the keys would still be in place, and the host would simply stop
accepting logins at the next bootstrap re-run rather than at the run that
caused it.
**Verified:** both account tasks pass their account's groups variable with
`append: true`, and the role's defaults define both as the empty list. No
test asserts the append flag, either default, or that a membership granted
by a later task survives a re-run; the property suite's sweep over
configurable variables does not include either groups variable.

### USR-9 — `.ssh` directory created for each account

THE Bootstrap SHALL create each bootstrap account's `.ssh` directory owned by
that account, with mode `0700`.

**Why:** sshd refuses to honour an `authorized_keys` file that sits under a
directory other users can write, and the refusal is invisible from the
client: the key is simply not treated as valid and the login falls through to
whatever else is permitted, which after this bootstrap is nothing. The
operator sees `Permission denied (publickey)` with a correct key correctly
installed, and the actual reason is recorded only in the host's own sshd log
— which they cannot read, because they cannot log in. Creating the directory
here, with its owner and mode stated, also means it exists correctly before
the key is written into it, rather than inheriting whatever mode whichever
tool happened to create it first left behind.
**Verified:** the role creates each `.ssh` directory with the account as both
owner and group and mode `0700`; the unit suite parses each of the two tasks
and asserts the mode, and the property suite asserts the literal `mode:
"0700"` appears somewhere in the role's task text. No test asserts the owner
or group of either directory — every ownership assertion in the two suites
is a check that the strings `owner:` and `group:` appear in the file at all,
not that either names the account.

### USR-10 — Public key deployed to each account's `authorized_keys`

THE Bootstrap SHALL deploy each bootstrap account's public key into that
account's `authorized_keys` file from the key file path configured for that
account.

**Why:** with passwords refused at the network (INV-2) and root unreachable
(INV-3), these two files are the host's entire remote access surface. The
silent failure is not that a task fails but that every task succeeds while
the wrong key is installed: the configured path pointed at a key the operator
no longer holds, or at the wrong one of several, and the file lookup read it,
and the entry was written, and the run reported success. Nothing on the host
can distinguish a valid key from a valid key belonging to someone else, so
the result is a correctly bootstrapped, correctly hardened host that nobody
can log into — learned at the first login attempt, after the run has already
removed the access path it was replacing.
**Verified:** both deployments use the authorized-key module with `state:
present` and `exclusive: false`, reading the key through a file lookup on the
path each account's key-file variable names; the role's defaults define both
paths. The unit suite parses each task and asserts the state and the
non-exclusive flag; the property suite asserts the module appears at least
twice and that both key-file variables are referenced. No test reads a key
file and confirms the resulting `authorized_keys` content, and nothing can
verify the deployed key is one the operator actually holds — that is not
knowable from the host.

### USR-11 — Public key files read on the controller

THE Bootstrap SHALL read each account's public key file from the Ansible
controller rather than from the target host.

**Why:** resolving the path on the controller is what makes it knowable
before the run touches the host at all, which is the whole basis of `PRJ-7`'s
pre-flight check: it can stat both files and abort while the host is still
exactly as it was. Resolved on the target instead, a missing or misspelled
path would surface midway through the run — after the accounts exist and,
given the play's fixed order, potentially after sshd has been hardened and
root's remote path removed, which is the worst possible moment to discover
that no key was installed. The quieter version of the same mistake is the `~`
in both default paths: a tilde expands against whichever machine resolves it,
so a path that silently resolved against the target's root home would find no
key, or find a different one, with nothing in the run's output naming the
machine it looked on.
**Verified:** both deployments obtain the key through a file lookup, which
Ansible evaluates on the controller, and `PRJ-7`'s pre-flight checks stat the
same two paths with execution delegated to the controller before the first
change to the host. The property suite's assertion is a substring check for
`lookup('file'` in the role's task text. Nothing asserts that the pre-flight
check and the deployment resolve the same path, and no test exercises a path
that exists on one machine and not the other.

### USR-12 — `authorized_keys` mode configurable, default `0600`

THE Bootstrap SHALL set each bootstrap account's `authorized_keys` file to
the mode given by `authorized_keys_mode`, defaulting to `0600`.

**Why:** a group- or world-*writable* `authorized_keys` is refused by sshd
the same silent way `USR-9`'s directory is. A merely *readable* one is worse,
because it is not refused at all: everything works, and the file tells every
local account on the host which keys open which account — a shopping list for
anyone who has already got a foothold as an unprivileged user. Re-asserting
the mode declaratively on every run, rather than accepting whatever the key
deployment created, is also what stops a mode loosened by hand from
surviving indefinitely (INV-9); the loosening itself produces no error, no
log line and no change in behaviour.
**Verified:** both permission tasks set the mode from `authorized_keys_mode`,
and the role's defaults define it as `0600`; the unit suite parses both tasks
and asserts the mode is that variable reference — not a resolved value — and
the property suite asserts the literal default appears in the defaults file.
No test renders the variable, and no test observes the mode of either file on
a live host: what is checked is that a variable is referenced and that a
default exists, not that any file ends up with mode `0600`.

### USR-13 — SSH access group created

THE Bootstrap SHALL create the group named by `ssh_access_group`, defaulting
to `ssh-users`.

**Why:** sshd is configured to admit only members of this group, so the
group's existence is a precondition for anyone reaching the host at all —
including the operator, and including the automation account that would
otherwise be used to repair the mistake. A missing or differently-named group
does not make sshd fail: it starts, reports a valid configuration, and
refuses every connection, because the access list names a group that has no
members or does not exist. The name itself is the quiet part. This role
falls back to a hardcoded literal when the variable is unset, while the
variable's only actual definition lives with sshd's own configuration, so a
fleet that overrides the name in one place and not the other creates one
group and gates on another, with nothing anywhere comparing the two.
**Verified:** the role creates the group with the group module, naming it
from `ssh_access_group` with an inline fallback to `ssh-users`. There is no
test of this task of any kind — neither the unit nor the property suite
references it — and the role's own defaults file does not define
`ssh_access_group` at all. Post-bootstrap verification checks only that the
rendered sshd configuration names the same string; nothing confirms the group
exists on the host.

### USR-14 — Both accounts are members of the SSH access group

THE Bootstrap SHALL add both bootstrap accounts to the SSH access group.

**Why:** this membership is what actually grants SSH access; everything else
this spec does is a precondition for it. It is also the last of those steps,
which is what makes its absence so hard to see: the accounts exist, the keys
are installed, the directories and files have the right modes, and every task
before it reported changed or ok. A host missing this one membership looks
completely bootstrapped and accepts nobody, because sshd rejects the
connection on the access list before it ever considers the key — so the
client is told `Permission denied (publickey)`, pointing the operator at
exactly the wrong thing, and they will go and check the key first.
**Verified:** a single task loops over both account names and adds each to
the group with `append: true`, so memberships granted elsewhere survive. Like
`USR-13`, this task has no test coverage at all: neither suite references the
task, the group or the membership, and post-bootstrap verification checks an
account's group membership only for the `wheel` group, which belongs to
`SUDO`.

### USR-15 — Further SSH access granted by group membership

THE Bootstrap SHALL grant SSH access to any additional account only through
membership of the SSH access group.

**Why:** sshd's access list is a single directive, and the only way to add an
account to it other than by joining the group is to rewrite that directive or
to shadow it from a configuration drop-in. Both are edits a repository built
on this bootstrap can make successfully: sshd starts, the configuration
validates, and the run reports success. What happens next is decided by
include order rather than by intent — either the bootstrap accounts are
replaced outright, or a second rule exists whose precedence over the first
nobody chose — and the resulting loss of access is discovered by whoever next
tries to log in, plausibly the operator holding the console credential this
bootstrap deliberately made the only fallback. Group membership cannot fail
that way: it is additive, so granting access to one account cannot remove it
from another.
**Verified:** the integration guidance for repositories built on this
bootstrap names the SSH access group as the designated way to grant an
account access, and lists it as surviving a bootstrap re-run. That document is
where this requirement is realised, because its audience — the repository
doing the granting — is outside this one. Nothing here can enforce it: no
task, test or check detects a downstream repository that edits sshd's access
configuration instead, and the mechanism it directs them to is `USR-13`'s
group and `USR-14`'s membership.
