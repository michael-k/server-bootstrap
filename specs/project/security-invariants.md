# Security Invariants

These invariants bind every spec in the tree. `INV-1`, `INV-7` and
`INV-10` build an allowance into their own SHALL: an exposure, or a
privilege grant `INV-7` would otherwise forbid, is permitted when a row in
one of the registers below covers it. A spec that needs one upholds the
invariant by claiming that numbered allowance on its
`**Allowances claimed:**` line, naming the compensating control in the
row, and saying so in its `## Security invariants` section. For any other
invariant, a spec that cannot uphold it does not get to quietly narrow it:
it states which invariant it bends and claims an allowance with a
compensating control in the same way. `make spec-check` enforces the
pairing in both directions — an allowance with no claimant, or a claim
with no matching row, is a failure.

## Invariants

### INV-1 — No exposure without an explicit allowance

THE Bootstrap SHALL NOT leave anything reachable from a publicly routable
address unless an allowance in the public exposure register covers it.

**Why:** The firewall's input chain drops by default (`INV-4`), so a
packet from the internet gets in only where a rule accepts it, and a rule
can be listed. The public exposure register below is that list, and it is
where to look for the host's public surface: each row names what is open,
from where, under which condition, and what compensates for it. A
requirement that states an exposure is not enough on its own, because it
is read one requirement at a time, and a reviewer reading one requirement
cannot see the whole surface. A row in the register can be seen, and the
checker pairs every row with the requirement that claims it.

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
principals who authenticate to escalate, unless an allowance in the
non-exposure allowance register covers the grant, and leave an audit trail
of its use.

**Why:** Sudo is granted per named user through a dedicated sudoers drop-in
file rather than an open group, `su` is restricted to members of a named
group, and sudo's defaults require a pty and enrich its log entries so
escalation is both restricted to named principals and recorded. Asking the
principal to authenticate when it escalates means a key that reaches an
account does not, by that alone, make its holder root. A grant that skips
that step is listed in the non-exposure allowance register below, for the
same reason exposures are listed: a reviewer can see in one place which
accounts need no more than their SSH key to become root, and what stands
in for the missing step. That holds only for the grants the Bootstrap
writes. Grants the base image or cloud-init leave on the host are
neither removed nor registered, which is a known divergence recorded in
`specs/sudo-hardening/requirements.md`.

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

### INV-10 — No exposure to tailnet peers without an explicit allowance

THE Bootstrap SHALL NOT leave anything reachable from a tailnet peer unless
an allowance in the tailnet exposure register covers it.

**Why:** Being on the tailnet is not a reason to trust a peer. A peer is
another machine, which can be compromised, lent, or enrolled by someone
other than this host's operator, and the policy that decides which peers
may reach this host is configured on the tailnet's control server, outside
this repository. Reaching a service only over the tailnet is narrower than
reaching it from the internet, which is why these exposures have a register
of their own rather than a row among the public ones, but narrower is not
closed. The tailnet exposure register below lists each hole the same way
the public one does.

## Allowance registers

Every register's rows start with the same three columns, the ones
`make spec-check` reads: the allowance, the invariants it is claimed
under, and the requirements that claim it. In the two exposure registers
the remaining columns say what is open, to whom, when, and what
compensates for it. The non-exposure register's say what the allowance
permits, when, and what compensates for it.

**Completeness, and its method.** For the base ruleset, the two exposure
registers are complete by this method: every `accept` rule in the input chain of
`roles/firewall/templates/nftables.conf.j2`, plus the break-glass script's
edits. The established-and-related accept (`FW-6`) and the loopback
accept (`FW-7`) need no row, because neither admits a packet a remote
source can start: the first admits replies to traffic this host began, and
the second matches packets arriving on the loopback interface, which no
remote packet does. The method does not reach rules a purpose repository
adds through the drop-in directory, nor a program that loads rules into
the kernel of its own accord outside `/etc/nftables.conf`. Those are not
claimed to be listed here.

### Public exposure register

These are the holes that let traffic from a publicly routable address in.
The knock ports need no row. A packet a remote source sends to one of them
is recorded by the knock rules and then dropped (`KNOCK-8`), not accepted.

A purpose repository opens its own holes, because its services need them,
and this register does not list them. It documents each hole it opens in
registers of its own, with the same columns and the same split between
public and tailnet exposure (`PRJ-28`).

| Allowance | Invariants | Claimed by | What is open | From where | Condition | Compensating control |
|---|---|---|---|---|---|---|
| ALW-1 | INV-1 | EMRG-3 | SSH on `firewall_ssh_port`, and sshd bound to `0.0.0.0` and `::` | Any address, on every interface. Tailnet peers reach nothing through it that `ALW-6` does not already admit | The break-glass script, deployed where `emergency_access_enabled` is true (`EMRG-2`), was run with no arguments, and neither `--restore` nor a bootstrap run that re-renders the ruleset (`FW-16`) has reversed it since | Requires an existing root session on the host; is never invoked by the bootstrap itself; is reversible with `--restore`, which returns the host to the configuration it started from; adds no network-reachable interface of its own; and leaves a timestamped copy of both files it edits |
| ALW-2 | INV-1 | FW-12 | UDP on `firewall_wireguard_port` | Any address, on every interface | `firewall_tailscale_enabled` is true | WireGuard does not answer a packet it cannot authenticate, so the port offers nothing to a sender without a key |
| ALW-3 | INV-1 | KNOCK-9 | SSH on `firewall_ssh_port` | Any address, on every interface, once that source has completed the knock sequence and while it is still within the passed-set timeout (`KNOCK-7`), and only over the address family it knocked with | `firewall_tailscale_enabled` is false and `firewall_port_knocking_enabled` is true | The knock sequence keeps the port closed to a source that has not sent it (`KNOCK-4` to `KNOCK-7`). The sequence is not authentication. Behind it, sshd accepts public keys only (`INV-2`) and gives root no remote login (`INV-3`) |
| ALW-4 | INV-1 | FW-13 | SSH on `firewall_ssh_port` | Any address, on every interface | `firewall_tailscale_enabled` and `firewall_port_knocking_enabled` are both false | sshd accepts public keys only (`INV-2`) and gives root no remote login (`INV-3`) |
| ALW-5 | INV-1 | FW-8, FW-9 | ICMPv4 and ICMPv6, every type | Any address, on every interface | Always | None in the ruleset: no rule narrows the types or limits the rate. The exposure is accepted because path MTU discovery, and IPv6 neighbour discovery and router advertisement, depend on it, as the **Why:** of `FW-8` and of `FW-9` state |

### Tailnet exposure register

These are the holes open to peers on the tailnet. On every row, which
peers may send is decided by the tailnet's own policy, which lives on the
control server (for example headscale's ACLs or grants). This repository
does not manage that policy, so no row claims it as a control.

The split between the two exposure registers assumes that `firewall_tailscale_enabled`
tracks whether the host is enrolled, which it does by default: it defaults
to `tailscale_enabled`. An inventory that sets it false on an enrolled host
makes the knock-gated SSH, open SSH and ICMP accepts match the tailnet
interface too, and this register does not cover that configuration.

| Allowance | Invariants | Claimed by | What is open | From where | Condition | Compensating control |
|---|---|---|---|---|---|---|
| ALW-6 | INV-10 | FW-10 | SSH on `firewall_ssh_port` | Packets arriving on `firewall_tailscale_interface`, from any peer the tailnet's policy permits | `firewall_tailscale_enabled` is true | sshd accepts public keys only (`INV-2`) and gives root no remote login (`INV-3`) |
| ALW-7 | INV-10 | FW-8, FW-9 | ICMPv4 and ICMPv6, every type | Packets arriving on `firewall_tailscale_interface`, from any peer the tailnet's policy permits | `firewall_tailscale_enabled` is true | None in the ruleset. The exposure is accepted for the reasons `ALW-5` gives |
| ALW-8 | INV-10 | FW-12 | UDP on `firewall_wireguard_port` | Packets arriving on `firewall_tailscale_interface`, from any peer the tailnet's policy permits. The rule does not name an interface, so the tailnet interface is among the ones it matches | `firewall_tailscale_enabled` is true | WireGuard does not answer a packet it cannot authenticate |

### Non-exposure allowance register

These allowances open nothing to the network. Each covers a grant that an
invariant's own SHALL admits when a row here covers it, so a spec that
claims one upholds that invariant, as a spec claiming an exposure row
upholds `INV-1` or `INV-10`.

For the privilege grants the Bootstrap writes, this register is complete
by this method: every file `roles/users/tasks/main.yml` writes under
`/etc/sudoers.d/`, and its `su` restriction. The manual account's grant
requires a password (`SUDO-2`), the `00-sudo-security` file sets defaults
and grants nothing (`SUDO-4`), and the `su` restriction adds
`pam_wheel`'s group check to Debian's `su` PAM stack, ahead of that
stack's password prompt, and removes nothing from it (`SUDO-13`).

The method does not reach grants the Bootstrap did not write: those the
base image ships in `/etc/sudoers` or `/etc/sudoers.d/`, including any file
cloud-init writes there for a provider's default user. `INV-7` still
covers them. The Bootstrap neither removes them nor registers them here,
and that is a known divergence from `INV-7`, which
`specs/sudo-hardening/requirements.md` records.

| Allowance | Invariants | Claimed by | What it permits | Condition | Compensating control |
|---|---|---|---|---|---|
| ALW-9 | INV-7 | SUDO-3 | `deploy_user_name` runs any command as any user through sudo without authenticating to escalate (`NOPASSWD:ALL`) | Always | The grant names one principal, in a drop-in file of its own, `/etc/sudoers.d/` followed by the account's name (`SUDO-3`). The account has no password that could be guessed or phished (`USR-6`), and sshd admits it by public key only (`INV-2`), so the key that reaches the account is the credential the grant rests on. sudo logs each use to syslog's AUTH facility, which journald keeps, with the year and the host on each entry (`SUDO-8`) |

Rows are added by the spec that needs one, not by this file. The checker
fails if a row here names no claiming requirement, or if a requirement
claims an allowance that has no row here.
