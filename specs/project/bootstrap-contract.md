# Bootstrap Contract

This is the machine state a purpose-specific repository (headscale,
nameserver, mailserver, and so on) may build on after a successful bootstrap
run.

Purpose repositories are **not coupled** to this bootstrap's code. They do
not import, depend on, or reference its roles, and nothing here names one.
The contract is the **machine state**, not the code that produces it.

This file carries no requirement IDs of its own. It is a view over the rest
of the tree: every line below is a guarantee stated as a citation of the
requirements that produce it, never as a restatement of them. A change to
any cited requirement is a change to this contract, and the place to make it
is that requirement's spec. Where a guarantee has no requirement behind it,
the line says so rather than naming the nearest plausible ID.

**Values are deliberately absent.** A line names the variable that holds a
value, not the value itself: a timeout, a mode, a limit or a port number
reproduced here would be a second place for it to be wrong, and the whole
point of the citation form is that there is only one. Read the cited
requirement for the number. Values are kept where a consumer cannot act on the
line without them, and where a requirement governs a kept value the line cites
it. A citation is not a promise that the requirement's SHALL names the value:
some fix only the behaviour. The owned-file list works that distinction
through for the paths it carries. Among them: the platform floor, the two
uids, the SSH access group's default name, the absolute paths a purpose
repository must either avoid or write to, and the names of the
mechanisms those lines turn on — the `wheel` and `systemd-journal` groups,
`/etc/hosts`'s `127.0.1.1` entry, the zram compressor.

`specs/**` is not scanned for citations: `tests/spec_check.py` excludes the
spec tree deliberately, because a cross-reference between specs is not
evidence that anything implements a requirement. The citations below
therefore count towards nothing in `make spec-check` — they are here to be
read, and to break visibly when the requirement they name changes.

## Operating system

- Debian 13 or newer, and the run refuses to start against anything older — PRJ-4
- Every available package upgrade applied, by the strategy `apt_upgrade_type`
  names, against a package index refresh bounded by
  `apt_update_cache_valid_time` — UPD-1, UPD-2
- Removal of orphaned dependencies and of unfetchable cached package files is
  configurable — UPD-3, UPD-4. That both **happen by default** is **not fixed
  by any requirement**: each SHALL makes only the behaviour configurable, and
  the enabling values are role defaults
- A reboot the upgrade made necessary is reported, never performed by the
  run — UPD-6, PRJ-10
- Where `system_hostname` is set: the running hostname, `/etc/hostname` and
  `/etc/hosts`'s `127.0.1.1` entry all agree with it. Where it is not set,
  all three are left as the provider delivered them — HOST-1, HOST-2, HOST-3, HOST-4

## Time synchronization

- Exactly one NTP client — chrony or systemd-timesyncd — installed,
  configured, enabled at boot and started; the candidate not selected is
  stopped and disabled — TIME-1, TIME-2, TIME-4, TIME-5
- Its server list comes from `ntp_servers`, defaulting to the Debian NTP
  pool — TIME-3
- Which of the two is the default is **not fixed by any requirement**;
  `time_sync_service` selects one and the specs state no default for it
- A started service is not yet a synchronized one. **`TIME-6` is pending** —
  specified, not yet implemented — so a run reports success on a host whose
  clock never moved toward correct

## Logging

- journald stores logs persistently on disk, in a `/var/log/journal` owned by
  root and the `systemd-journal` group, set up so that group can read the
  journal without it becoming world-readable and so files journald creates
  inside stay in that group — LOG-1, LOG-5
- Retention bounded by `journald_max_retention_time` and disk use by
  `journald_max_disk_usage` — LOG-3, LOG-2
- A change to journald's configuration restarts journald inside the same
  run, so the live daemon enforces what the run deployed — LOG-4

## User accounts

- Manual account: uid 1000, named by `manual_user_name`, password from
  `manual_user_password` supplied from the vault — USR-1, USR-2, USR-3
- Automation account: uid 1999, named by `deploy_user_name`, with a password
  field no password can satisfy — USR-4, USR-5, USR-6
- Each account's login shell and its supplementary group memberships are both
  configurable — USR-7, USR-8
- Each account has a `.ssh` directory it owns, mode-restricted to itself, and
  an `authorized_keys` deployed from a key file read on the controller, at the
  mode `authorized_keys_mode` gives — USR-9, USR-10, USR-11, USR-12
- Both accounts are members of the SSH access group named by
  `ssh_access_group` (default `ssh-users`), which is what sshd consults — USR-13, USR-14, SSH-12
- Manual account: sudo through its own `sudoers.d` file, password
  required. Automation account: the same, without a password — SUDO-2, SUDO-3
- Root has no remote login path at all — SSH-2, INV-3
- `su` is restricted to members of `wheel`, and the manual account is a
  member — SUDO-11, SUDO-12, SUDO-13
- The two accounts' **default names** are **not fixed by any requirement**:
  `USR-2` and `USR-5` make the names configurable and state no default

## Login hardening

- Shell idle timeout from `login_policy_tmout`, exported so child shells
  inherit it and marked `readonly` — advisory, not enforcement — LOGIN-5, LOGIN-6
- Root console login restricted to an explicit list of virtual and serial
  TTYs, excluding pseudo-terminals, enforced by `pam_securetty` in
  `/etc/pam.d/login` — LOGIN-3, LOGIN-4
- Hardened `/etc/login.defs`: a tightened default umask, a console retry limit
  from `login_policy_retries`, a console login timeout from
  `login_policy_timeout`, successful console logins logged, and Debian's other
  shipped defaults left in place — LOGIN-1, LOGIN-2, LOGIN-7, LOGIN-8, LOGIN-9
- faillock: an account is locked after `pam_faillock_deny` failures within
  `pam_faillock_fail_interval`, and unlocked after
  `pam_faillock_unlock_time`; root is not exempt, and a successful
  authentication resets the counter — PAM-1, PAM-2, PAM-3, PAM-4, PAM-5, PAM-17
- The lockout check runs both ahead of and behind `pam_unix`, as two
  `pam-auth-update` profiles, and `common-auth` is rebuilt whenever either
  changes — PAM-6, PAM-7, PAM-9
- Hard resource limits for every PAM-authenticated session: a process ceiling
  and an open-file-descriptor ceiling, each set separately for root
  (`pam_limits_nproc`, `pam_limits_nproc_root`, `pam_limits_nofile`,
  `pam_limits_nofile_root`), and core dumps disabled outright. Every directive
  is a hard limit, never a soft one — PAM-10, PAM-11, PAM-12, PAM-13, PAM-14, PAM-15, PAM-16
- Sudo hardening, all from one `visudo`-validated drop-in: environment
  reset, fixed command search path, a credential cache timeout from
  `sudo_timestamp_timeout`, log entries carrying year and host, a
  sudo-allocated pty, and a controlling terminal required for interactive use
  with the automation account exempted — SUDO-4, SUDO-5, SUDO-6, SUDO-7, SUDO-8, SUDO-9, SUDO-10

## SSH

- Public keys are the only authentication method offered; passwords, empty
  passwords and root login are all refused — SSH-1, SSH-2, SSH-3, SSH-4, INV-2, INV-3
- Listening port from `ssh_port` — SSH-13
- At most `ssh_max_auth_tries` authentication attempts per connection, and a
  client that has not authenticated within `ssh_login_grace_time` is
  disconnected — SSH-14, SSH-15
- An idle client is probed every `ssh_client_alive_interval` seconds and
  disconnected after `ssh_client_alive_count_max` unanswered probes — SSH-16
- X11 forwarding, TCP port forwarding, agent forwarding and `tun`
  tunnelling are all refused — SSH-8, SSH-9, SSH-10, SSH-11
- Login is restricted to members of `ssh_access_group` (default
  `ssh-users`) — SSH-12
- Key exchange, ciphers and MACs are restricted to the configured lists,
  whose defaults include the hybrid post-quantum key exchange and no weak
  one, only AEAD ciphers, and only Encrypt-Then-MAC MACs — SSH-5, SSH-6, SSH-7
- Where Tailscale is enabled and both tailnet addresses are available, sshd
  binds to those two addresses and no other; otherwise to
  `ssh_listen_address_ipv4` and `ssh_listen_address_ipv6`, which default to
  every interface — SSH-18
- A candidate configuration is parsed by sshd itself before it is installed,
  and sshd is restarted when the installed file changes — SSH-17, SSH-19
- sshd is enabled and running when the run succeeds, where the base image
  ships it that way — SSH-20

## Firewall (nftables)

- `nftables` is the packet filter, expressed as one dual-stack `inet` table
  with no separate IPv4-only or IPv6-only table; the service is enabled at
  boot, started, and reloaded when and only when the ruleset changes — FW-1, FW-2, FW-17, FW-18, FW-19, INV-4
- Input and forward chains default to `drop`, the output chain to
  `accept` — FW-3, FW-4, FW-5, INV-4
- Loopback traffic, established and related connections, ICMPv4 and ICMPv6
  are accepted — FW-6, FW-7, FW-8, FW-9
- Inbound SSH reaches the host by exactly one of three paths, always on the
  port `firewall_ssh_port` names (default: the SSH spec's `ssh_port`) — FW-14
  - **Tailnet only**, where Tailscale is enabled: accepted only on packets
    arriving on `firewall_tailscale_interface` — FW-10, FW-11
  - **Knock-gated**, where Tailscale is disabled and knocking enabled (its
    own default): a three-port TCP sequence, taken from
    `firewall_port_knocking_sequence`, advances a source through per-family
    stage-1, stage-2 and passed sets
    whose only reset is their timeout, and SSH is accepted only for a source
    in its own family's passed set — KNOCK-1, KNOCK-2, KNOCK-3, KNOCK-4, KNOCK-5, KNOCK-6, KNOCK-7, KNOCK-9, KNOCK-10
  - **Open**, where both are disabled: accepted on every interface — FW-13
- The WireGuard port named by `firewall_wireguard_port` is accepted on every
  interface where Tailscale is enabled, and is not opened where it is
  disabled. The port number itself is a role default the requirement does
  not fix — FW-12
- The deployed ruleset replaces what is loaded, from `/etc/nftables.conf`,
  root-owned — FW-15, FW-16

## Intrusion prevention (fail2ban)

- fail2ban is installed from the distribution's own package repository,
  enabled at boot, running when a run completes, and restarted when and only
  when its jail configuration changes — F2B-1, F2B-13, F2B-14, F2B-15
- The SSH jail is active by default, watches TCP on the port `ssh_port`
  names, takes its evidence from the systemd journal rather than a log file,
  and matches it with the distribution's own `sshd` filter in its aggressive
  mode — F2B-4, F2B-5, F2B-6, F2B-7, F2B-8
- A source is banned after `fail2ban_max_retry` matched failures within
  `fail2ban_find_time`, and the ban lasts `fail2ban_ban_time` — F2B-9, F2B-10
- Bans are enforced through the nftables action `fail2ban_banaction`
  names — F2B-11
- This project's jail policy lives in `/etc/fail2ban/jail.local` alone. That
  file is read *after* `jail.d/*.conf`, so its `[DEFAULT]` section — the
  backend among them — governs every jail that does not pin its own settings,
  including a purpose repository's. The SSH jail's own counters are pinned in
  its section, so no `[DEFAULT]` from any file fail2ban reads can change
  them — F2B-3, F2B-7, F2B-12

## Filesystem hardening

- `/tmp`, `/var/tmp` and `/dev/shm` are all mounted `noexec`, `nosuid`,
  `nodev`, with `/var/tmp` bind-mounted onto `/tmp` — so an executable
  cannot be run from any of the three — FS-1, FS-2, FS-3
- Delivered as systemd mount units and drop-in overrides, never as
  `/etc/fstab` entries, and `/tmp` and `/dev/shm` are remounted in the same
  run rather than at the next reboot — FS-4, FS-5
- Where a changed unit is already active and needs a manual restart or a
  reboot, the operator is told. **`FS-6` is pending** — specified, not yet
  implemented — so a run does not yet make that report

## Tailscale VPN

- Enrolment is opt-in and off by default; a host with it disabled has
  nothing Tailscale-related installed, configured or verified — TS-1, TS-2
- The node registers against `tailscale_control_server` with a pre-auth key
  held in the vault, and registration is skipped on a host already
  registered — TS-6, TS-7, TS-9
- The interface is named by `tailscale_interface` — TS-14 — and it exists on a
  host where the run completed, because the run fails if it does not appear —
  TS-15, TS-16. Its IPv4 and IPv6 addresses are published as facts — TS-17, TS-18
- Routes advertised by other tailnet nodes are accepted; the host's own DNS
  configuration is left untouched — TS-10, TS-11
- The run fails, naming lockout, if the interface does not appear, if the
  backend does not reach `Running`, if either address is missing, or if
  traffic does not pass over the interface — and every one of those checks
  completes before any role narrows SSH to the tailnet — TS-15, TS-16, TS-19, TS-20, TS-21, TS-22, INV-8
- A break-glass script is deployed to `emergency_access_script_path`,
  root-owned and root-only, only where a tailnet was joined, and is never
  executed by a run — EMRG-1, EMRG-2, EMRG-17

## Swap

- zram is off by default. Where it is enabled, `zram-tools` is installed and
  the device is created at the configured size, compressed with lz4,
  formatted as swap, activated, re-established on boot, and given the
  priority `zram_swap_priority` names — SWAP-1, SWAP-2, SWAP-3, SWAP-4, SWAP-5, SWAP-6, SWAP-7, SWAP-8, SWAP-9
- Disk swap is unset by default. Where `disk_swap_size` is set, `/swapfile`
  is created at that size, readable only by root, formatted as swap,
  activated, and recorded in `/etc/fstab` — SWAP-10, SWAP-11, SWAP-12, SWAP-13, SWAP-14, SWAP-15
- Where both are configured, zram gets the higher priority. Where neither
  is, swap configuration is skipped entirely — SWAP-16, SWAP-17
- The **numeric** priorities are **not fixed by any requirement**: `SWAP-9`
  makes zram's configurable, `SWAP-16` fixes only the ordering between the
  two, and nothing states a priority for `/swapfile`

## Ansible connection model

- The run brings a fresh Debian host, reachable only as root over SSH, to its
  full configured state in one pass, performing every configuration task with
  root privilege — PRJ-1, PRJ-2
- A purpose-specific playbook connects as the automation account and
  escalates with `become: true` and no `become_password` — SUDO-3
- It authenticates with the key deployed to that account's
  `authorized_keys`; passwords are refused, so the playbook runner must hold
  the matching private key — USR-10, SSH-1, SSH-3
- Where Tailscale is enabled, the target answers SSH only on its tailnet
  addresses, so that is the only address a playbook can reach it on — SSH-18, FW-10

## Bootstrap-owned files

Each entry below names what the bootstrap manages: a whole file, one line of
a file, a file's removal, or a directory's existence, ownership or mode. An
edit from outside this bootstrap to what an entry names is lost when the
bootstrap next re-asserts it, so a purpose repository must not make one.
What an entry does not name is not managed: other lines of a line-edited file
are left alone, and so are files a purpose repository adds to a directory
this list names. `## Extension points` says which directories are meant for
that.

**A path in this list is not necessarily a path the specs fix.** For seventeen
of them the requirement beside the path fixes the behaviour while the path
itself is where the implementation puts it, so it could move without a spec
change:

- `/etc/systemd/journald.conf`, `/etc/chrony/chrony.conf`,
  `/etc/systemd/timesyncd.conf`, `/etc/profile.d/shell-timeout.sh` and
  `/etc/default/zramswap` — no SHALL mentions any of them
- `/etc/sudoers.d/00-sudo-security`, `/etc/sudoers.d/<manual_user_name>` and
  `/etc/sudoers.d/<deploy_user_name>` — `SUDO-2`, `SUDO-3` and `SUDO-4` fix
  only that each is "a `sudoers.d` file"; the directory is fixed, the filenames
  are not
- `/usr/share/pam-configs/faillock-preauth` and
  `/usr/share/pam-configs/faillock-authfail` — `PAM-6` and `PAM-7` fix the
  *profile names*, not the directory they live in; `PAM-8` names no path at all
  for `/usr/share/pam-configs/faillock`
- `/etc/systemd/system/tmp.mount`, `tmp.mount.d/hardening.conf`,
  `dev-shm.mount.d/hardening.conf` and `var-tmp.mount` — `FS-1` to `FS-4` fix
  the mount points and that the
  mechanism is a systemd unit or drop-in, never a file path, though systemd's
  own naming rules leave little room for these to differ
- `/etc/apt/sources.list.d/tailscale.list` — no `TS` requirement mentions it;
  the filename follows from how the repository is added
- `/etc/pam.d/su` — `SUDO-13` fixes `pam_wheel`, and the path appears only in
  its `**Verified:**` prose

`/etc/ssh/sshd_config` is a case of its own: no `SSH` requirement names it, and
the only SHALLs in the tree that do are `EMRG-5`, `EMRG-10` and `EMRG-13` —
they name it as the file the break-glass script backs up, refuses to run
without, and must leave sshd resolving the same way across a round trip. So the
path is fixed, but by the spec that reads the file rather than by the one that
writes it.

Every other path in the list is named in the SHALL of a requirement cited
beside it. That split was measured by extracting every backquoted absolute path
from the SHALL paragraph of all 22 `requirements.md` files and comparing the
result against this list; the extraction is exhaustive over the SHALL text as
written, since no SHALL in the tree contains an unquoted absolute path. It
would still miss a requirement that fixed a path without writing it out.

Rewritten from a template or copied on every run:

- `/etc/nftables.conf` — FW-16
- `/etc/ssh/sshd_config` — SSH-17, SSH-19
- `/etc/fail2ban/jail.local` — F2B-3
- `/etc/systemd/journald.conf` — LOG-1, LOG-2, LOG-3, LOG-4
- `/etc/hostname`, where `system_hostname` is set — HOST-2, HOST-4
- `/etc/chrony/chrony.conf` or `/etc/systemd/timesyncd.conf`, whichever
  service was selected — TIME-1, TIME-3
- `/etc/login.defs` — LOGIN-1
- `/etc/securetty` — LOGIN-4
- `/etc/sudoers.d/00-sudo-security` — SUDO-4
- `/etc/sudoers.d/<manual_user_name>` — SUDO-2
- `/etc/sudoers.d/<deploy_user_name>` — SUDO-3
- `/etc/profile.d/shell-timeout.sh` — LOGIN-5, LOGIN-6
- `/etc/security/faillock.conf` — PAM-1
- `/etc/security/limits.d/50-hardening.conf` — PAM-16
- `/usr/share/pam-configs/faillock-preauth` and
  `/usr/share/pam-configs/faillock-authfail` — PAM-6, PAM-7
- `/etc/systemd/system/tmp.mount`, or `tmp.mount.d/hardening.conf` where a
  `tmp.mount` unit already exists — FS-1, FS-4
- `/etc/systemd/system/dev-shm.mount.d/hardening.conf` — FS-3, FS-4
- `/etc/systemd/system/var-tmp.mount` — FS-2, FS-4
- `/usr/share/keyrings/tailscale-archive-keyring.gpg`, only where Tailscale is
  enabled — TS-4
- `/etc/apt/sources.list.d/tailscale.list`, only where Tailscale is enabled —
  TS-3, TS-4, TS-5
- `/root/emergency-ssh-access.sh`, the default for
  `emergency_access_script_path`, only where a tailnet was joined — EMRG-1, EMRG-2
- `/etc/netplan/50-cloud-init.yaml`, only where `static_ipv6_address` is
  set — NET-2, NET-5; untouched where it is not — NET-1
- `/etc/default/zramswap`, only where zram is enabled — SWAP-4, SWAP-5, SWAP-9

Edited in place, created or removed on every run:

- `/etc/hosts` — its `127.0.1.1` line, where `system_hostname` is set — HOST-3, HOST-4
- `/etc/pam.d/login` — its `pam_securetty` line — LOGIN-3
- `/etc/pam.d/su` — its `pam_wheel` line — SUDO-13
- `/etc/pam.d/common-auth` — rebuilt by `pam-auth-update` whenever a
  faillock profile changes — PAM-9
- `/usr/share/pam-configs/faillock` — **removed**, not written: it is the
  superseded single-profile deployment — PAM-8
- `/var/log/journal` — LOG-5
- `/etc/nftables.d` — created, never emptied — FW-20
- `/etc/fail2ban` — its ownership and mode — F2B-2
- `/swapfile` and `/etc/fstab`'s swap entry, only where `disk_swap_size` is
  set — SWAP-11, SWAP-12, SWAP-15

## What purpose repositories must not do

- **Grant SSH access by editing sshd's access configuration.** Access is
  granted by adding the account to the SSH access group, never by rewriting
  or shadowing `AllowGroups` — USR-15, SSH-12
- **Modify what the list above manages** — the whole file, the named line,
  or the directory's existence, ownership or mode, as each entry says. The
  bootstrap re-asserts it, so the edit is silently lost — the citation beside
  each path is the requirement that does it. The rule does not reach other
  lines of a line-edited file, or files added to a directory the list names
- **Import, reference or depend on this bootstrap's roles or their
  internals**, and **do not duplicate what it already does** — no
  requirement states either. Both are consequences of the preamble: the
  contract is the machine state, so anything reached by naming this
  repository's code is outside it

## Extension points

These are the designated places where a purpose repository integrates with a
bootstrapped host. Where a re-run could disturb the integration, the line says
what stops it and cites the requirement — or says plainly that no requirement
states it, as the first line does; the last three lines are integration points
that a re-run has nothing to disturb, except as the `apt packages` line itself
states.

- **The `ssh-users` group** — add an account to the group named by
  `ssh_access_group` and sshd lets it in — USR-13, USR-14, USR-15, SSH-12.
  That a re-run does not remove a member added elsewhere is **not stated by
  any requirement**: `USR-14` obliges the bootstrap to add its own two
  accounts and says nothing about anyone else's membership. Non-removal is an
  implementation property, recorded in `USR-14`'s `**Verified:**` prose but
  not required anywhere
- **`/etc/sudoers.d/<name>`** — drop a sudoers file for a service account.
  The bootstrap writes only `00-sudo-security` and one file per bootstrap
  account; no requirement has it remove or purge anything else in the
  directory — SUDO-2, SUDO-3, SUDO-4
- **`/etc/nftables.d/*.nft`** — the directory exists and is included at the
  end of the deployed ruleset, so a drop-in's rules are appended after
  everything the firewall spec renders and only the input chain's `drop`
  policy comes after them; a re-run neither deletes the file nor needs to
  know about it. Files must use `add rule` syntax, because the include is
  read inside the same transaction as the ruleset's own flush and the table
  already exists. A rule accepting one of the knock ports is never reached
  on a knock-gated host — FW-20, FW-21, FW-15, KNOCK-8. Every hole a
  drop-in opens must be documented in the purpose repository's own exposure
  registers, with the columns and the public/tailnet split of
  `specs/project/security-invariants.md`'s exposure registers — PRJ-28
- **`/etc/fail2ban/jail.d/*.conf`** — the bootstrap's own jail policy is
  confined to `jail.local`, and the SSH jail's counters are pinned at jail
  level against any `[DEFAULT]` a drop-in sets — F2B-3, F2B-12. Confinement to
  one file is not isolation, though: `jail.local` is read *after*
  `jail.d/*.conf`, so its `[DEFAULT]` section governs any drop-in jail that
  does not pin its own values. A jail that reads a log file must set
  `backend` explicitly, or it inherits `systemd` and reads the journal
  instead — F2B-7. The same applies to `bantime`, `findtime`, `maxretry` and
  both ban actions. That fail2ban reads the directory at all is the package's
  behaviour, not a bootstrap requirement
- **systemd units** — a new service's output goes to the journal, which is
  persistent and bounded by the retention this contract already states — LOG-1, LOG-2, LOG-3
- **apt packages** — install what you need. A re-run upgrades installed
  packages by `apt_upgrade_type`'s strategy, and removes packages left with
  no remaining dependents, which `apt_autoremove` controls — UPD-2, UPD-3
- **The automation account** — use it for Ansible-driven configuration, as
  the connection model above describes — USR-4, USR-5, SUDO-3
- **The tailnet interface** — assume it exists where `tailscale_enabled` was
  set, because a run that left it absent failed — TS-15, TS-16 — and assume it
  does not where the flag was unset — TS-1, TS-2. Its name is
  `tailscale_interface` — TS-14

"Survives a bootstrap re-run" is a property of each extension point
individually, as cited above. `PRJ-13` and `PRJ-25` do **not** produce it:
they state that a re-run completes without error and reports no changes,
which is about the bootstrap's own state, not about preserving a purpose
repository's. `PRJ-25` is in any case pending. `INV-9` is likewise narrower
than the column it would seem to justify — it says a re-run never *weakens*
what an earlier run established, not that it preserves what another
repository added.
