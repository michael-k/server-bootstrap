# Security Invariants

These invariants bind every spec in the tree. A feature that cannot uphold
one does not get to quietly narrow it: the feature's `requirements.md`
states which invariant it bends in its `## Security invariants` section,
claims a numbered allowance from the register below, and names a
compensating control. `make spec-check` enforces the pairing in both
directions — an allowance with no claimant, or a claim with no matching
row, is a failure.

## Invariants

### INV-1 — No exposure without an explicit allowance

THE Bootstrap SHALL NOT leave a service reachable on a publicly reachable
address unless a requirement explicitly allows it.

**Why:** The firewall's input chain defaults to drop and accepts only
loopback traffic, established/related connections, ICMP, and SSH — and each
SSH path (Tailscale-restricted, port-knock-gated, or open) is opened by a
rule that names the requirement authorizing it. Anything beyond that reaches
the host only through the purpose-specific drop-in directory a spec owns.

### INV-2 — Public-key-only remote authentication

THE Bootstrap SHALL restrict remote authentication to public keys, never
accepting a password at a network-facing authenticator.

**Why:** sshd disables password authentication, empty passwords, and
challenge-response authentication, leaving public-key authentication as the
only way in over the network. The manual user's password exists solely for
local sudo escalation and console login, paths sshd never consults.

### INV-3 — No remote root

THE Bootstrap SHALL leave root with no remote login path.

**Why:** sshd denies root login outright, which disables every remote login
method for root, password or key alike. Administrators reach root only by
escalating from the manual or Ansible user.

### INV-4 — Default-deny dual-stack firewall

THE Bootstrap SHALL default the firewall's input and forward chains to
drop, for IPv4 and IPv6 alike.

**Why:** The firewall defines a single dual-stack table rather than
separate IPv4 and IPv6 tables, so one `policy drop` on the input chain and
one on the forward chain govern both address families identically — there
is no separate, looser IPv6 path to diverge from the IPv4 one.

### INV-5 — Vault-only secrets

THE Bootstrap SHALL deliver every secret to the host only through Ansible
Vault, never through the repository, a log, or a process argument list.

**Why:** The example inventory indirects credentials through `vault_*`
variables meant to live only in an encrypted vault file, never in the
repository itself.

### INV-6 — Console-recoverable narrowing

THE Bootstrap SHALL make every mechanism that narrows access recoverable
using console access alone.

**Why:** Every access-narrowing mechanism is a plain configuration file a
root console session can edit directly, and the emergency access script
that flips SSH between Tailscale-only and public reachability edits those
same files and restarts the affected services locally, making no network
call of its own.

### INV-7 — Named, audited privilege escalation

THE Bootstrap SHALL restrict privilege escalation to explicitly named
principals and leave an audit trail of its use.

**Why:** Sudo is granted per named user through a dedicated sudoers drop-in
file rather than an open group, `su` is restricted to members of a named
group, and sudo's defaults require a pty and enrich its log entries so
escalation is both restricted to named principals and recorded.

### INV-8 — Verify before narrowing

THE Bootstrap SHALL NOT narrow access before verifying the replacement path
works.

**Why:** The Tailscale role checks its interface, its addresses, and end
to end connectivity — failing the whole run if any check fails — and runs
before the role that restricts sshd to the Tailscale-only listen addresses,
so a failed Tailscale connection can never leave a host with no way in.

### INV-9 — Re-runs never weaken

THE Bootstrap SHALL NOT let a re-run weaken state a previous run
established.

**Why:** The playbook deploys the hardened files it manages declaratively,
so they converge to the same state on every run, and it adds to the group
memberships it manages without removing from them. That is what keeps a
re-run from relaxing a restriction an earlier run put in place.

## Allowance register

| Allowance | Invariants | Claimed by | Compensating control |
|---|---|---|---|
| ALW-1 | INV-1 | EMRG-3 | Requires an existing root session on the host; is never invoked by the bootstrap itself; is reversible with `--restore`, which returns the host to the configuration it started from; adds no network-reachable interface of its own; and leaves a timestamped copy of both files it edits |

Rows are added by the spec that needs one, not by this file. The checker
fails if a row here names no claiming requirement, or if a requirement
claims an allowance that has no row here.
