# SSH Hardening — Requirements

**Prefix:** `SSH`

## Purpose

This spec covers the one service that decides whether anybody can reach a
bootstrapped host at all. Every other access control in this project — sudo
restrictions, PAM lockout, the firewall, fail2ban — is applied to a session
that has already been admitted by sshd, so sshd's configuration is where the
question "who may log in, over which cryptography, on which address" is
actually settled. The role answers it by replacing `/etc/ssh/sshd_config`
outright with a single rendered template: authentication is public-key only,
root has no remote login path, the key exchange, cipher and MAC lists are
narrowed to algorithms that are not merely unbroken, with a hybrid
post-quantum key exchange among them, every forwarding and tunnelling
feature is off, login is limited to one named group, and the daemon binds to the tailnet addresses when
Tailscale is enabled and to every interface when it is not.

Without this spec a host would keep Debian's defaults — password logins,
CBC-era algorithms still negotiable, forwarding available to anyone who
authenticates, and sshd listening on every address on the public internet.
With this spec, and only with it, the narrow path the firewall and the
break-glass script are built around exists. It is also the most dangerous
spec in the tree to get wrong: a wrong `ListenAddress` does not fail, it
binds, and the operator discovers it by not being able to log in to fix it.

## Scope

### In scope

- The authentication policy sshd enforces: passwords refused, root refused,
  public keys accepted, empty passwords refused, and the keyboard-interactive
  path closed so PAM cannot reintroduce a password prompt over the network.
- The three algorithm lists — key exchange, cipher, MAC — their configurable
  variables and their default contents, including the hybrid post-quantum
  key exchange algorithm.
- The four features this spec switches off: X11 forwarding, TCP forwarding,
  agent forwarding and tunnelling.
- Group-based login restriction through `AllowGroups` and
  `ssh_access_group`.
- The listening port (`ssh_port`, default 22).
- The session limits: authentication attempts per connection, the
  unauthenticated grace period, and the keepalive probe interval and count.
- Restarting sshd when its configuration changes, and validating the
  candidate configuration with sshd's own parser before it is installed.
- The `ListenAddress` binding and the condition that chooses between the
  tailnet addresses and the all-interfaces fallback, including the
  `ssh_listen_address_ipv4` and `ssh_listen_address_ipv6` defaults used in
  the second case.
- The file the role deploys: its path, ownership and mode.

### Out of scope

- Producing the tailnet addresses this spec binds to, and the verification
  that they exist and work before it binds them — owned by `TS`, which
  publishes `tailscale_ipv4` and `tailscale_ipv6` and whose `TS-22` is what
  makes binding to them safe. This spec consumes the pair; it never queries
  the client.
- Creating the SSH access group and putting accounts into it — owned by
  `USR`. This spec names the group in `AllowGroups`; it does not create it,
  and a host whose group is empty or missing is one nobody can log in to,
  which is `USR`'s guarantee to make, not this spec's.
- Provisioning the public keys that the accepted public-key authentication
  actually checks against, and the `.ssh` directory and `authorized_keys`
  modes that make sshd willing to read them — owned by `USR`.
- Admitting or dropping packets on the SSH port, on the tailnet interface or
  anywhere else — owned by the firewall spec. sshd binding an address and
  the firewall admitting traffic to it are two independent restrictions, and
  this spec is only the first.
- The break-glass script that rewrites this spec's own `ListenAddress` lines
  on a live host to restore public reachability — owned by the
  emergency-access spec. It edits the file this spec deploys, which makes
  the two specs' interaction a failure mode worth naming, but the script and
  its gating belong there.
- Rate-limiting or banning repeated failed authentications — owned by the
  fail2ban spec. `SSH-14` limits attempts within one connection; nothing
  here limits how many connections an attacker may open.
- PAM's own account, session and lockout policy behind `UsePAM yes` — owned
  by `PAM` and `LOGIN`.
- Post-bootstrap confirmation that sshd is still configured and running as
  this spec requires — owned by `VRFY`.

## Security invariants

**Upholds:** INV-1, INV-2, INV-3
**Relies on:** INV-4, INV-8
**Allowances claimed:** none

This spec is where `INV-2` and `INV-3` are actually enforced. Every other
spec that mentions them describes a consequence; `SSH-1`, `SSH-3` and
`SSH-4` are the directives that make "no password at a network-facing
authenticator" true, and `SSH-2` is the whole of "root has no remote login
path". `INV-2` in particular is upheld by three requirements rather than
one, because a password can reach sshd by three routes — the password
method itself, an empty password accepted as a match, and the
keyboard-interactive method PAM drives — and closing only the first leaves
the invariant intact on paper and broken in practice.

`INV-1` is upheld conditionally rather than absolutely, and the distinction
matters. `SSH-18`'s Tailscale branch removes sshd from every publicly
reachable address, which is `INV-1` in its strongest form. Its else-branch
deliberately binds `0.0.0.0` and `::`, which is exposure — but it is
exposure that a requirement explicitly states, which is exactly the shape
`INV-1` permits, and it is the branch that runs on a host with no VPN, where
the alternative is no access at all. That branch is also why this spec
relies on `INV-4`: on a Tailscale-disabled host, sshd's own binding narrows
nothing, and the only thing between the daemon and the internet is the
firewall's default-deny posture plus whichever SSH rule the firewall spec
opened.

The reliance on `INV-8` is the serious one. Binding sshd to a tailnet
address is irreversible from outside the host: if the address is wrong,
unassigned or unreachable, sshd starts, binds nothing usable, and the next
connection attempt fails with no diagnostic from a host nobody can log into.
`SSH-18` does not and cannot check any of that itself — `SSH-19`'s
validation parses the address, it does not bind it — so the whole safety
argument is that `TS-15` through `TS-21` have
already established the addresses are real and working, and `TS-22` requires
them to have finished before this spec's template is rendered. `INV-6` is
the last resort behind that, through the emergency-access spec's local
script.

## Requirements

### SSH-1 — Password authentication refused

THE Bootstrap SHALL configure sshd to refuse password authentication.

**Why:** a password is a secret that can be guessed, phished, reused from
another service, or typed into the wrong terminal, and sshd on a public
address is guessed at continuously by unattended scanners. Refusing the
method outright is what turns that traffic from a race between an attacker's
dictionary and the operator's password choice into something that cannot
succeed at all, and it is the clause of `INV-2` that everything else about
remote access in this project assumes. The manual account still has a
password (`USR-3`) because local sudo and console login need one; this
requirement is what keeps that password off the network.
**Verified:** the deployed configuration sets `PasswordAuthentication no`.
`test_password_authentication_disabled` renders the template and asserts the
directive appears in the output;
`test_property_5_ssh_daemon_hardening_configuration` asserts the same string
against the template file's text. Two checks ask a *running* sshd what it
resolved to rather than reading a file: the verification play's
`Verify SSH-1: SSHD password authentication is disabled`, which asserts
`passwordauthentication no` in `sshd -T` output, and the integration suite's
`sshd -T | grep passwordauthentication` on a bootstrapped host. Neither runs in `make test-unit` or `make test-property`
— the first needs a live target, the second needs Incus — so on an ordinary
developer machine this requirement is verified entirely by substring checks
against template text, which cannot tell whether a later line re-enables the
method.

### SSH-2 — Root login refused

THE Bootstrap SHALL configure sshd to refuse login as root by any method.

**Why:** root is the one account name every attacker already knows, and the
one whose compromise needs no further escalation. Refusing it at sshd is
`INV-3` in a single directive, and it is deliberately the unqualified form
rather than `prohibit-password`: a key-only root login would still be a
remote path to uid 0 that survives the loss of any one administrator's
workstation, and this project has two named accounts and a documented
escalation path (`SUDO`) precisely so that it does not need one. Note that
the bootstrap itself connects as root to do its work — this requirement is
what closes that door behind it.
**Verified:** the deployed configuration sets `PermitRootLogin no`.
`test_root_login_disabled` renders the template and asserts the directive;
`test_property_5_ssh_daemon_hardening_configuration` asserts it against the
template text; `tests/verify_bootstrap.yml` asserts `permitrootlogin no` in
`sshd -T` output on a live host, and the integration suite has a
`test_root_login_rejected` that attempts the login. Only the last two
establish anything about a running daemon.

### SSH-3 — Public-key authentication the only method offered

THE Bootstrap SHALL restrict sshd authentication to public keys, enabling
public-key authentication and leaving no other authentication method
enabled.

**Why:** `SSH-1` and `SSH-4` each close one door; this requirement is the
positive statement that exactly one remains open, which is what makes the
policy auditable rather than a list of things that happen to be off.
Enabling public keys is the trivial half. The half that is easy to miss is
keyboard-interactive authentication: it is a separate method from
`PasswordAuthentication`, it is driven by PAM, and on a stack that includes
`pam_unix` it prompts for — and accepts — the very password `SSH-1`
refused. Closing it is why `INV-2` says "never accepting a password at a
network-facing authenticator" rather than "disable password
authentication".
**Verified:** the deployed configuration sets `PubkeyAuthentication yes` and
`ChallengeResponseAuthentication no`, the latter being the directive
OpenSSH now treats as an alias for `KbdInteractiveAuthentication`.
`test_pubkey_authentication_enabled` and
`test_property_5_ssh_daemon_hardening_configuration` assert the first
directive. **Nothing in any suite asserts the second**, in the template or
on a live host — the keyboard-interactive half of this requirement has no
test coverage at all, and deleting that line would pass every check in this
repository. `design.md`'s `## Failure modes` records this.

### SSH-4 — Empty passwords refused

THE Bootstrap SHALL configure sshd to refuse authentication with an empty
password.

**Why:** an account with no password set is not a theoretical artefact — it
is what a mistyped `useradd`, a half-finished provisioning script or a
locked account whose lock was written wrongly produces, and sshd's own
default is to refuse such logins precisely because the failure is silent
from the host's side. Stating it explicitly costs one line and removes the
possibility that a future change to the authentication block, or a Debian
default that drifts, turns an account this project never meant to be
loginable into one that is. It is the third of `INV-2`'s three routes.
**Verified:** the deployed configuration sets `PermitEmptyPasswords no`.
`test_empty_passwords_disabled` and
`test_property_5_ssh_daemon_hardening_configuration` assert the directive.
No test creates an account with an empty password and confirms the login is
refused. In practice `SSH-1` already makes this unreachable over the
network, so this requirement's value is as a guard against a future
weakening of `SSH-1`, not as an independently exercised control.

### SSH-5 — Key exchange restricted to the configured list, hybrid post-quantum included

THE Bootstrap SHALL restrict sshd's key exchange algorithms to the list in
`ssh_kex_algorithms`, whose default includes the hybrid post-quantum
algorithm `sntrup761x25519-sha512` and includes nothing weak: no SHA-1-based
exchange and no finite-field Diffie-Hellman group of 2048 bits or smaller.

**Why:** key exchange is the step that decides the session key, and it is
the one step whose failure is retroactive: an adversary who records a
session today and breaks its key exchange later reads that session's
traffic, without ever having touched the host. Debian's default list is
chosen for interoperability and still negotiates SHA-1-based exchanges and
small-group finite-field Diffie-Hellman, either of which makes the recording
worth keeping. Narrowing the list removes those. Including
`sntrup761x25519-sha512` goes one step further: it is a hybrid of
Streamlined NTRU Prime and X25519, so the session key is secure unless
*both* are broken, which is what makes a recording made today uninteresting
to an adversary betting on a future quantum computer. What the server
controls is the set, not the order: RFC 4253 §7.1 selects the first
algorithm on the client's list that the server also offers, so the client's
order decides the outcome and the order of `ssh_kex_algorithms` is not a
control. A session gets the post-quantum exchange when the client prefers
it, and every entry in the list is reachable by a client that prefers that
entry. That is why the requirement is stated as membership: the list must
hold the post-quantum algorithm, and it must hold nothing weak, because any
entry it holds is one a session can end up using. The two
`diffie-hellman-group16`/`group18` entries are kept as a compatibility floor
for clients too old for curve25519; they are finite-field, not elliptic
curve, and what keeps them acceptable is their 4096- and 8192-bit groups,
not their place in the list.
**Verified:** the defaults file lists the five algorithms, and the deployed
configuration renders them comma-joined onto one `KexAlgorithms` line.
`test_kex_algorithms_present` renders the template and asserts each of the
five strings appears; `test_kex_algorithms_comma_separated` asserts the
rendered `KexAlgorithms` line contains a comma;
`test_no_weak_kex_algorithms` asserts four excluded-algorithm substrings
are absent; `test_ssh_algorithm_restrictions_use_modern_standards` and
`test_property_5_ssh_daemon_hardening_configuration` assert list membership
against the defaults file. The verification play's
`Verify SSH-5: SSHD key exchange algorithms` asserts `kexalgorithms` and
`curve25519-sha256` in a live `sshd -T` output; it runs only against a real
target.

Two gaps. **No test asserts the post-quantum algorithm against the
defaults file at all**: the unit suite asserts it in the rendered
configuration, but the unit suite renders the template from `base_vars`, a
hand-written copy of the role defaults, so it confirms that the fixture's
list renders — deleting `sntrup761x25519-sha512` from
`roles/ssh_hardening/defaults/main.yml` changes no test result. Both
defaults-reading tests name only `curve25519` and the two finite-field
groups. **And `test_no_weak_kex_algorithms` is a denylist** of four specific
strings rather than an allowlist, so a fifth weak algorithm added to the
defaults would not be caught.

### SSH-6 — Ciphers restricted to authenticated-encryption constructions

THE Bootstrap SHALL restrict sshd's ciphers to the list in `ssh_ciphers`,
whose default contains only AEAD constructions.

**Why:** an AEAD cipher authenticates the ciphertext as part of decrypting
it, so a modified packet is rejected before any of its plaintext is acted
on. The alternative sshd still supports — CBC-mode ciphers paired with a
separate MAC — decrypts first and checks afterwards, which is the structure
behind the Encrypt-and-MAC attacks on SSH, and the reason Debian's
interoperability-first default list is wider than this one. Restricting to
three AEAD constructions means the "decrypt, then discover it was forged"
window does not exist on this host at all.
**Verified:** the defaults file lists ChaCha20-Poly1305 and the two AES-GCM
ciphers, and the deployed configuration renders them comma-joined onto one
`Ciphers` line. `test_ciphers_are_aead_only` asserts each of the three
strings appears in the rendered output;
`test_ciphers_comma_separated` asserts the rendered `Ciphers` line contains
a comma; `test_no_cbc_ciphers` asserts three CBC substrings are absent;
`test_ssh_algorithm_restrictions_use_modern_standards` and
`test_property_5_ssh_daemon_hardening_configuration` assert membership
against the defaults file — the latter only that the string `ssh_ciphers:`
is present and that either `chacha20-poly1305` or `gcm` appears somewhere in
the file. The verification play's `Verify SSH-6: SSHD ciphers` asserts
`ciphers` and one of the two named AEAD ciphers in a live `sshd -T` output,
and runs only against a real target. Two weaknesses, both shared with `SSH-5`: the negative check
is a three-string denylist rather than an allowlist, so a fourth, non-AEAD
cipher added to the defaults is caught only if it is one of the three named
CBC ciphers; and the three positive assertions render the template from the
unit suite's `base_vars` fixture, a hand-written copy of the role defaults,
so they confirm the fixture's list rather than the deployed one.

### SSH-7 — MACs restricted to Encrypt-Then-MAC variants

THE Bootstrap SHALL restrict sshd's MAC algorithms to the list in
`ssh_macs`, whose default contains only Encrypt-Then-MAC variants.

**Why:** the MAC list only comes into play for ciphers that are not
themselves authenticated, which `SSH-6` has already excluded — so this
requirement is defence in depth rather than the primary control. It is worth
stating anyway, because the two requirements are configured independently
and a future relaxation of `SSH-6` would silently make this list load-bearing
again. Of the two constructions sshd offers, Encrypt-Then-MAC computes the
tag over the ciphertext, so a forged packet is rejected without the
implementation ever decrypting it; the `-etm@openssh.com` suffix is what
selects it.
**Verified:** the defaults file lists the two `-etm@openssh.com` variants,
and the deployed configuration renders them comma-joined onto one `MACs`
line. `test_macs_are_etm_only` asserts both strings appear in the rendered
output; `test_macs_comma_separated` asserts the rendered `MACs` line
contains a comma; `test_no_non_etm_macs` asserts `hmac-sha1`, `hmac-md5` and
a newline-anchored `hmac-sha2-512` are absent;
`test_ssh_algorithm_restrictions_use_modern_standards` and
`test_property_5_ssh_daemon_hardening_configuration` assert membership
against the defaults file, the latter needing only the substring `etm` to
appear anywhere in it. The verification play's `Verify SSH-7: SSHD MACs`
asserts `macs` and the substring `etm@openssh.com` in a live `sshd -T`
output, and runs only against a real target. Three weaknesses: the `hmac-sha2-512\n` check is
positional rather than semantic and would not catch a non-ETM MAC appearing
anywhere but at the end of a line; the negative checks are a denylist rather
than an allowlist; and the two positive assertions render the template from
the unit suite's `base_vars` fixture, a hand-written copy of the role
defaults, so they confirm the fixture's list rather than the deployed one.

### SSH-8 — X11 forwarding disabled

THE Bootstrap SHALL configure sshd to refuse X11 forwarding.

**Why:** X11 forwarding hands a remote display connection back across the
SSH channel, and the X protocol has no meaningful isolation between clients:
anything on the forwarded display can read keystrokes and screen contents
belonging to anything else on it. On a server with no graphical software at
all the feature has no legitimate use, so leaving it enabled is purely an
attack surface that a compromised client could turn back on the operator's
own workstation.
**Verified:** the deployed configuration sets `X11Forwarding no`.
`test_x11_forwarding_disabled` renders the template and asserts the
directive; `test_property_5_ssh_daemon_hardening_configuration` asserts it
against the template text; `tests/verify_bootstrap.yml` asserts
`x11forwarding no` in `sshd -T` output on a live host.

### SSH-9 — TCP forwarding disabled

THE Bootstrap SHALL configure sshd to refuse TCP port forwarding.

**Why:** TCP forwarding turns any account admitted by `SSH-12` into a
general-purpose network relay: an authenticated user can tunnel to any
address the host can reach, which includes everything the firewall admits on
the loopback interface and everything on whatever private networks the host
is attached to. That is precisely the pivot an attacker wants after
compromising one credential, and it bypasses the firewall's input policy by
approaching from inside. Nothing this bootstrap deploys needs it.
**Verified:** the deployed configuration sets `AllowTcpForwarding no`.
`test_tcp_forwarding_disabled` renders the template and asserts the
directive; `test_property_5_ssh_daemon_hardening_configuration` asserts it
against the template text; `tests/verify_bootstrap.yml` asserts
`allowtcpforwarding no` in `sshd -T` output on a live host.

### SSH-10 — Agent forwarding disabled

THE Bootstrap SHALL configure sshd to refuse SSH agent forwarding.

**Why:** a forwarded agent socket lets the host ask the operator's own
workstation to sign with the operator's private keys, for as long as the
session lasts. Root on the host — or anyone who reaches the socket — can use
that to authenticate onward to every other machine those keys open,
converting a single compromised server into a foothold on the operator's
whole estate. The key material never leaves the workstation, which is
exactly what makes the exposure easy to underestimate.
**Verified:** the deployed configuration sets `AllowAgentForwarding no`.
`test_agent_forwarding_disabled` renders the template and asserts the
directive; `test_property_5_ssh_daemon_hardening_configuration` asserts it
against the template text; `tests/verify_bootstrap.yml` asserts
`allowagentforwarding no` in `sshd -T` output on a live host.

### SSH-11 — Tunnelling disabled

THE Bootstrap SHALL configure sshd to refuse `tun` device tunnelling.

**Why:** `PermitTunnel` is the heaviest of the forwarding features: it
allocates a kernel `tun` interface and carries arbitrary IP traffic over the
SSH connection, which is a VPN built out of a login session and entirely
invisible to the firewall's own interface-based rules. This project already
has a VPN with an access-controlled control plane (`TS`); a second,
unmanaged one available to any authenticated account is not a feature, it is
a hole.
**Verified:** the deployed configuration sets `PermitTunnel no`.
`test_tunneling_disabled` renders the template and asserts the directive;
`test_property_5_ssh_daemon_hardening_configuration` asserts it against the
template text; `tests/verify_bootstrap.yml` asserts `permittunnel no` in
`sshd -T` output on a live host.

### SSH-12 — Login restricted to members of the SSH access group

THE Bootstrap SHALL restrict sshd login to members of the group named by
`ssh_access_group` (default `ssh-users`).

**Why:** `SSH-2` removes one account from the set of possible logins; this
requirement inverts the question and names the only set that may. Every
service account a package installs, every system user with a shell it did
not need, and every future account created for an unrelated purpose is
excluded by default rather than by somebody remembering to exclude it —
which is the difference between a policy and a habit. The restriction is by
group rather than by listing usernames deliberately: a purpose-specific
deployment on top of this bootstrap grants SSH access by adding an account
to one group, with no edit to this role and no second place where the list
of permitted users could drift out of agreement with itself.
**Verified:** the deployed configuration sets `AllowGroups` to the value of
`ssh_access_group`, and the defaults file defines that variable as
`ssh-users`. `test_allow_groups_contains_ssh_access_group`,
`test_allow_groups_with_custom_group` and
`test_allow_groups_single_group_by_default` render the template and assert
on the rendered `AllowGroups` line, including with an overridden group name;
`test_property_6_ssh_access_restriction` asserts the directive, the variable
name and the defaults entry as substrings. The verification play's
`Verify SSH-12: SSHD AllowGroups is restricted` asserts `allowgroups` and
the configured group name in a live `sshd -T` output, and runs only against
a real target. Note that the three
unit assertions render from the unit suite's `base_vars` fixture, a
hand-written copy of the role defaults, so the two that use the default
group name confirm the fixture's value rather than the deployed one; only
`test_allow_groups_with_custom_group`, which overrides the variable, tests
the interpolation independently of it. Nothing in this spec's scope
confirms the group exists or has members — that is `USR-13` and `USR-14`,
which the findings for that spec record as having no test coverage of any
kind. The group name is also held as a literal in two roles independently;
see `design.md`'s `## Failure modes`.

### SSH-13 — Listening port configurable, default 22

THE Bootstrap SHALL accept `ssh_port` (default 22) as the port sshd listens
on, and configure sshd to listen on it.

**Why:** the default exists because 22 is what every client, every firewall
rule and every runbook assumes, and moving it is not a security control —
a scanner finds a service on port 2222 as readily as on 22. The variable
exists because the deployments that consume this bootstrap sometimes have no
choice: a provider's own management agent already on 22, a NAT mapping, or a
test harness running several hosts behind one address. Making the port one
named variable rather than a literal is what keeps the firewall rule, the
break-glass script and sshd itself from disagreeing about it — all three
derive from this one value.
**Verified:** the defaults file defines `ssh_port: 22` and the deployed
configuration renders `Port` from the variable. `test_ssh_port_rendered`
asserts `Port 22` in the default rendering; `test_custom_ssh_port` renders
with `ssh_port` overridden to 2222 and asserts both that the new port
appears and that the old one does not;
`test_property_7_ssh_port_configuration` asserts the `Port` directive, the
`{{ ssh_port }}` interpolation and the `ssh_port: 22` default as substrings.
The verification play's
`Verify SSH-13: SSHD is listening on configured port only` asserts the
configured port in a live `sshd -T` output, and the integration suite
bootstraps with
`ssh_port: 2222` and then connects on that port — the only end-to-end
evidence that the directive takes effect, and it runs only under Incus.
`test_ssh_port_rendered`'s `Port 22` comes from the unit suite's
`base_vars` fixture, a hand-written copy of the role defaults, so it
confirms the fixture rather than the deployed default; the property suite's
`ssh_port: 22` assertion against the defaults file is what covers that.
Nothing verifies that the firewall's
`firewall_ssh_port` and the break-glass script's
`emergency_access_ssh_port` resolve to the same value as this one, although
both are written to derive from it.

### SSH-14 — Authentication attempts per connection limited

THE Bootstrap SHALL limit the authentication attempts sshd permits within
one connection to `ssh_max_auth_tries` (default 3).

**Why:** a client that offers keys from an agent burns one attempt per key,
so a low limit is mostly a curb on automated probing rather than on
legitimate use — but the reason it matters here is subtler than
rate-limiting. sshd counts partial and failed attempts alike, and an
attacker who can keep one connection open indefinitely gets an unlimited
number of guesses that never appear as new connections, which is what makes
a connection-count-based defence like fail2ban blind to them. Capping the
attempts is what forces each guess to cost a new connection, and therefore
what makes `F2B`'s counting meaningful at all.
**Verified:** the defaults file defines `ssh_max_auth_tries: 3` and the
deployed configuration renders `MaxAuthTries` from the variable.
`test_max_auth_tries` asserts `MaxAuthTries 3` in the default rendering and
`test_custom_session_values` asserts an overridden value renders;
`test_property_8_ssh_session_security_configuration` asserts the directive
and the variable interpolation as substrings, and additionally parses the
defaults file to assert the value is at most 6, which checks the real
default's value rather than a string's presence. `test_max_auth_tries`'s
`MaxAuthTries 3` comes from the unit suite's `base_vars` fixture, a hand-written copy of the role
defaults, so it confirms the fixture's value rather than the deployed one.
No test confirms a fourth attempt is actually refused by a running daemon,
and nothing anywhere checks `MaxAuthTries` in a live `sshd -T` output.

### SSH-15 — Unauthenticated connections time out

THE Bootstrap SHALL disconnect a client that has not authenticated within
`ssh_login_grace_time` (default 30s).

**Why:** every connection that has not yet authenticated holds a slot in
sshd's pre-authentication concurrency limit, and that pre-authentication
code path is the part of sshd an unauthenticated attacker can reach — the
part where SSH's remote-code-execution bugs have historically lived. A long
grace period lets a small number of clients hold those slots open
indefinitely, which is a denial of service against the operator's own
ability to log in and fix it, and lengthens the window for any
pre-authentication bug. Thirty seconds is comfortably more than an
interactive key-based login needs and far less than an idle attacker wants.
**Verified:** the defaults file defines `ssh_login_grace_time: "30s"` and
the deployed configuration renders `LoginGraceTime` from the variable.
`test_login_grace_time` asserts `LoginGraceTime 30s` in the default
rendering and `test_custom_session_values` asserts an overridden value
renders; `test_property_8_ssh_session_security_configuration` asserts the
directive, the variable interpolation and the presence of the defaults entry
as substrings. Unlike `SSH-14`, nothing asserts the default is actually
short — the property test checks only that the key exists, so a default of
`600m` would pass, and `test_login_grace_time`'s `LoginGraceTime 30s` comes
from the unit suite's `base_vars` fixture, a hand-written copy of the role
defaults, so it confirms the fixture's value rather than the deployed one.
Between them, no test in this repository reads the actual default. No test
opens a connection and waits, and nothing checks the resolved value in a
live `sshd -T` output.

### SSH-16 — Idle sessions closed by keepalive probes

THE Bootstrap SHALL configure sshd to probe an idle client every
`ssh_client_alive_interval` seconds (default 300) and to disconnect it after
`ssh_client_alive_count_max` unanswered probes (default 2).

**Why:** the two settings are one control and are specified together because
neither is meaningful alone — an interval with no count never disconnects,
and a count with no interval never probes. Their purpose is not idleness as
such but the sessions that are *already gone*: a closed laptop, a dropped
VPN, a killed terminal. Those leave an authenticated session attached to the
host with no one at the other end, which keeps the operator's authenticated
context alive on a machine they are no longer watching, and accumulates over
a long-lived host until the session limit is the thing refusing new logins.
Probing detects the absence; the count decides how much packet loss to
forgive before acting on it.
**Verified:** the defaults file defines `ssh_client_alive_interval: 300` and
`ssh_client_alive_count_max: 2`, and the deployed configuration renders both
directives from those variables. `test_client_alive_interval` and
`test_client_alive_count_max` assert the rendered values, and
`test_custom_session_values` asserts overridden values render;
`test_property_8_ssh_session_security_configuration` asserts both
directives, both variable interpolations and both defaults entries as
substrings. As with `SSH-15`, no assertion constrains the values: the
property suite checks only that both keys exist in the defaults file, and
the two unit assertions render `300` and `2` from `base_vars`, a
hand-written copy of the role defaults, so they confirm the fixture rather
than the deployed values. No test establishes that a silent client is
actually disconnected, and nothing checks either resolved value in a live
`sshd -T` output.

### SSH-17 — sshd restarted when its configuration changes

WHEN sshd's configuration file changes, THE Bootstrap SHALL restart sshd.

**Why:** sshd reads its configuration at startup, so a deployed file that
the running daemon has not read is a host that reports itself hardened and
is not. The failure is silent in the worst direction: the run reports
`changed`, the file on disk says exactly what this spec requires, and the
daemon accepting connections is still the one that was running before —
until some unrelated reboot months later applies the change at a moment
nobody is watching. Coupling the restart to the file's change, rather than
restarting unconditionally, is also what keeps a re-run on an unchanged host
from interrupting anything.
**Verified:** the template deployment task notifies a handler that restarts
`sshd`, and the handler is defined in the role.
`test_ssh_hardening_role_has_handler_for_service_restart` asserts the
handler exists, uses a service-management module and uses
`state: restarted`; `test_ssh_hardening_tasks_notify_handler_on_config_change`
asserts the task file contains `notify:` and mentions sshd;
`test_property_9_service_restart_on_configuration_change` walks this role
along with several others and asserts that a role deploying a template
notifies a handler, that the handler uses a service module and a
restarted-or-reloaded state, and — its one structural check — that every
notified handler name is actually defined in `handlers/main.yml`. Note that
the handler does not run at the end of this role: it runs at the next
handler flush after it, which the logging role forces as its last task, so
the restart happens after the firewall, emergency-access, fail2ban and
logging roles and before `swap`. `design.md`'s `## Failure modes` records
what that means when the new configuration is one sshd cannot bind.

### SSH-18 — Listen addresses bound to the tailnet when enrolled, to all interfaces otherwise

THE Bootstrap SHALL bind sshd to `tailscale_ipv4` and `tailscale_ipv6` and
to no other address when Tailscale is enabled and both addresses are
available, and to `ssh_listen_address_ipv4` and `ssh_listen_address_ipv6`
(defaults `0.0.0.0` and `::`) otherwise.

**Why:** this is the requirement the rest of this spec exists to make safe,
and the one that can strand an operator. Binding to the tailnet addresses
removes sshd from every publicly reachable address on the host, so the
service is not merely filtered but absent — a scan finds nothing, and an
attacker who later finds a way through the firewall finds no listener behind
it. That is `INV-1` in its strongest available form, and it is what makes
the tailnet the single controlled way in. The two branches are one
requirement rather than two because they are one decision with one failure
mode between them: the else-branch is not an independent policy but the
constitutive statement of what "not narrowed" means, and separating them
would allow a future change to satisfy each half while leaving a host in
neither state. The guard on both facts being *defined* is load-bearing in
its own right — a half-published pair, or a truthy-looking
`tailscale_enabled` on a host where the role never ran, must fall back to
the open branch rather than render an empty `ListenAddress`, because an
empty one is a configuration sshd will happily accept and nobody can reach.
**Verified:** the deployed configuration selects between the two address
pairs on `tailscale_enabled` and both Tailscale facts being defined, and the
defaults file supplies `0.0.0.0` and `::` for the second branch.
`test_listen_all_interfaces_when_tailscale_disabled` renders the template
with Tailscale off and asserts both open addresses appear;
`test_listen_tailscale_only_when_enabled` renders it with Tailscale on and
two tailnet addresses and asserts both appear *and* that neither open
address does;
`test_tailscale_ip_reflected_in_listen_address` repeats it with different
addresses. `test_property_12_ssh_interface_restriction_with_safety_check`
asserts the conditional, the IPv4 interpolation and the `is defined` guard
as substrings, and then asserts against `TS`'s own verification task file
rather than this role.
`test_property_13_ssh_interface_configuration_based_on_vpn_status` walks the
template's lines and asserts the else-branch specifically contains an
all-interfaces `ListenAddress`, which is the only placement-aware assertion
in this spec.
`test_ssh_interface_restriction_based_on_tailscale_status` and
`test_ssh_interface_restriction_variable_propagation` add substring checks
on the same construction. The verification play's
`Verify SSH-18: SSH is restricted to Tailscale interface`, which runs only
when Tailscale is enabled, asserts that a live `sshd -T` reports a
`listenaddress` and does *not* report `listenaddress 0.0.0.0`. That is the
only check anywhere that reads what a running daemon resolved — but note
what it reads: `sshd -T` prints the configuration sshd parsed, not the
sockets it holds, and it would print exactly the same thing on a host where
the daemon subsequently failed to bind the address. Resolution and binding
are separate facts, and only the first is checked here.

The two unit assertions for the disabled branch take `0.0.0.0` and `::`
from `base_vars`, a hand-written copy of the role defaults, so they confirm
the fixture's values rather than the deployed ones; the enabled-branch
assertions override the facts in the test body, so they are independent of
the fixture.

What none of them establishes is that the addresses bound are addresses the
host actually has. `SSH-19`'s validation parses `ListenAddress` without
attempting to bind it, so an unusable address passes validation and passes
every test here. What happens at the restart depends on how many addresses
are unbindable: sshd treats a bind failure as fatal only if *every*
configured address fails, so a host that can bind one of the pair starts
normally and serves one family — the run reports success and nothing
notices. `design.md`'s `## Failure modes` sets out both cases. The whole
protection against that is `TS-22` and the checks before it, which are
outside this spec. The integration suite's tailnet tests are the only place
a real bound address is confirmed, and they run only under Incus.

### SSH-19 — Candidate configuration parsed by sshd before it is installed

THE Bootstrap SHALL validate a candidate sshd configuration with sshd's own
parser before installing it, and SHALL leave the existing configuration in
place if the candidate does not parse.

**Why:** every other requirement in this spec is a directive in one file
that replaces sshd's entire configuration, and the file is written by a
template with sixteen interpolations. A rendering mistake — an undefined
variable, a list that joins to nothing, a value that is not of the type the
directive takes — produces a file sshd refuses to load, and sshd refuses by
exiting rather than by falling back. Without this check the sequence is:
Ansible writes the broken file, reports success, `SSH-17` restarts the
daemon at the logging role's handler flush, and the daemon does not come
back. Running
sshd's own parser over the candidate first turns that into an ordinary task
failure with the previous, working configuration untouched and the host as
reachable as it was — which is `INV-6`'s recoverability expressed as a
precondition rather than as a recovery. Using sshd's own parser, rather than
a schema this project maintains, is the point: it is the same code that will
read the file for real, so it cannot disagree with it.
**Verified:** the deployment task passes `validate: /usr/sbin/sshd -t -f %s`
to `ansible.builtin.template`, which renders the candidate to a temporary
file, runs the command, and installs the file only on a zero exit status.
`test_ssh_configuration_validation_prevents_lockout` asserts the `validate:`
key, the `/usr/sbin/sshd` path, the `-t` flag and the `%s` placeholder are
all present in the task file;
`test_property_7_ssh_port_configuration` asserts `validate:` and `sshd`; and
`test_property_12_ssh_interface_restriction_with_safety_check` asserts
`validate:` and the literal `/usr/sbin/sshd -t`. All three are substring
checks against the task file's text — no test renders a deliberately broken
template and confirms the task fails, so nothing establishes that the hook
actually fires.

What this check does **not** catch is the failure this spec is most exposed
to. `sshd -t` parses; it does not bind. A configuration naming a
syntactically valid `ListenAddress` that is assigned to no interface on this
host exits zero and is installed, and the daemon then either dies at restart
or comes up serving fewer addresses than intended, depending on whether any
of its configured addresses bound at all. Either way this is `SSH-18`'s
lockout, and it is why that requirement's safety rests on `TS-22` and the
Tailscale checks before it rather than on this one.
The same holds for any directive that is well-formed but wrong: a `Port` no
firewall admits, an `AllowGroups` naming a group that does not exist. This
requirement covers well-formedness only, and is written that way
deliberately rather than claiming more.
