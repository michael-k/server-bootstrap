# Project — Design

## Approach

The bootstrap is a single Ansible entry point containing two plays.

The first play runs on the controller, not on the target. Its only job is to
knock on the firewall's port sequence so the second play can open an SSH
connection at all. It gathers no facts and makes no connection to the host; it
is skipped when Tailscale is enabled, because then SSH is reached over the VPN
instead. Its requirements belong to `KNOCK`, not here — what belongs here is
that it is a separate play, so a knock failure is reported before any
configuration is attempted.

The second play is the bootstrap proper, and it has three phases:

1. **Pre-tasks — validate, change nothing.** The platform floor, the required
   user configuration, the existence of both public key files on the controller,
   and the Tailscale configuration when Tailscale is enabled. Then a summary of
   what is about to be applied. A failure here leaves the host untouched
   (`PRJ-5`).
2. **Roles — compose the machine state.** Each role owns one capability and one
   spec. The play contributes the order (`PRJ-12`) and nothing else: no role
   knows where it sits in the sequence, so the ordering constraints live in this
   one list.
3. **Post-tasks — report, change nothing.** Whether a reboot is pending, and a
   summary of the access paths and restrictions now in force.

Around the entry point sits the repository contract: dependencies declared once
in the Python project metadata, resolved by `uv`, and every operation exposed as
a make target so the documented command and the run command are the same
command.

## Implementation map

| Path | Realises |
|---|---|
| `site.yml` | PRJ-1, PRJ-2, PRJ-3, PRJ-4, PRJ-5, PRJ-6, PRJ-7, PRJ-8, PRJ-9, PRJ-10, PRJ-11, PRJ-12, PRJ-13, PRJ-15 |
| `ansible.cfg` | PRJ-2, PRJ-3 |
| `inventory/` | PRJ-6, PRJ-7, PRJ-8, PRJ-15 |
| `Makefile` | PRJ-15, PRJ-16, PRJ-19 |
| `pyproject.toml` | PRJ-17, PRJ-18 |
| `README.md` | PRJ-4, PRJ-15, PRJ-16, PRJ-17, PRJ-18, PRJ-19, PRJ-20, PRJ-21, PRJ-22, PRJ-23, PRJ-24, PRJ-26, PRJ-27 |

The platform floor (`PRJ-4`) is asserted in `site.yml` and stated in
`README.md`. `PRJ-14` is cited only from the integration suite, and
`PRJ-25` is pending.

## Key decisions

**The order of the roles is a decision, not an accident.** It is recorded here
because `PRJ-12` states that prerequisites come first without saying what they
are, and a reader changing the list needs to know which moves are safe.

- **Package updates run first.** An update can replace sshd, nftables, systemd
  or the kernel. Running it after the hardening would overwrite freshly written
  configuration with a package's own version, or restart a service under a
  configuration the run has not finished writing. Running it first means the
  host's outstanding security patches are in place before the run gives it its
  new access paths, every later role configures the versions the host will keep,
  and the reboot notice at the end of the run has a single cause to point at.
- **Tailscale runs before SSH hardening.** The hardened sshd configuration binds
  its listen addresses to the host's Tailscale addresses, which are facts that
  exist only after enrollment has succeeded. Rendered before enrollment, the
  template would produce an sshd that listens nowhere. Tailscale's own role
  fails the run if the interface, the addresses or end-to-end connectivity are
  missing, so this ordering is also what makes INV-8 hold: the replacement path
  is proven before the old one is narrowed.
- **Accounts run before SSH hardening.** The hardened configuration restricts
  logins to a group; the accounts and that group have to exist first, or the
  restriction admits nobody.
- **The firewall runs after the services it admits.** Its rules are derived from
  the SSH port and the Tailscale interface, so the values it reads must already
  be settled.
- **Swap and logging run last.** Neither is a prerequisite for anything else,
  and neither affects reachability, so they sit where a failure costs least.

**The knock is a separate play, not a pre-task.** It runs with a local
connection because its whole purpose is to make the SSH connection possible;
a pre-task would already be inside a play that has connected.

**Privilege escalation is declared once, on the play.** Per-task escalation
would put the privilege boundary in a dozen files and make an accidental
unprivileged task look like a configuration bug (`PRJ-2`).

**Pre-flight checks are assertions and stats, never fixes.** A check that
repaired what it found would defeat `PRJ-5`: the point is that the host is
untouched when validation fails, and that includes not "helpfully" creating a
missing key file.

**Check mode is a requirement, not a side effect** (`PRJ-14`). It constrains
every role: a task that cannot run in check mode, or that reports a change
unconditionally, is a defect in that role even though the symptom only appears
at this level.

## Failure modes

- **A pre-flight assertion fails.** The run stops before the first role, and the
  host is exactly as it was. This is the designed outcome for every input
  problem: wrong platform, missing variable, missing key file, Tailscale enabled
  without credentials.
- **The knock fails or the host is unreachable.** The second play never
  connects, so nothing is changed. The failure names the connection, which is
  the honest diagnosis — the host may be down, the knock sequence may be wrong,
  or a previous run may have narrowed SSH to a VPN this controller is not on.
- **The vault password is wrong or missing.** Variable resolution fails before
  any task runs, and no secret is applied in a partial state.
- **A role fails partway through.** The host is left in a partial state, and the
  run is re-run after the cause is fixed rather than rolled back; `PRJ-13` is
  what makes that safe. The ordering in `PRJ-12` bounds the damage: a failure
  before SSH hardening leaves the original access path intact, and a failure
  after it leaves the new one already in place.
- **A reboot is pending and never taken.** The run reports it (`PRJ-10`) but
  does not act. The host keeps running the superseded kernel or libraries until
  its owner restarts it.

## Interactions

This spec is the one every feature spec assumes. Feature specs cite `PRJ`
requirements by ID; this section names the other specs by prefix, because their
requirement IDs are assigned by those specs.

**What this spec assumes of others:**

- `TS` — enrollment either succeeds or fails the run, so that `PRJ-12`'s
  ordering is enough to satisfy INV-8.
- `UPD` — package updates converge, and expose the reboot-required state that
  `PRJ-10` reports.
- Every feature spec — its role is idempotent and check-mode clean, which is
  what `PRJ-13`, `PRJ-25` and `PRJ-14` assert at the level of the whole run.

**What others may assume of this spec:**

- The platform is Debian 13 or newer (`PRJ-4`), so no role needs its own version
  guard or a compatibility branch for an older release.
- The manual and deploy account names, the manual account's password and both
  public key file paths are defined, non-empty and — for the key files —
  present on the controller (`PRJ-6`, `PRJ-7`). `USR` therefore does not
  re-validate them.
- Tailscale's control server and pre-authentication key are present whenever
  Tailscale is enabled (`PRJ-8`).
- Facts are gathered (`PRJ-3`) and every task runs as root (`PRJ-2`).
- Secrets arrive from the vault (`PRJ-15`), so no spec needs a second mechanism
  for supplying one.
- `KNOCK` owns the knock play that shares this entry point; `VRFY` owns the
  separate verification playbook that runs after a bootstrap; `TEST` owns the
  suites that assert `PRJ-13` and `PRJ-14` hold, and the assertion `PRJ-25` is
  still waiting on.
