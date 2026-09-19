# Port Knocking

Port knocking hides the SSH port from network scanners. Instead of leaving SSH open to the internet, the firewall requires you to send a specific sequence of TCP packets to predetermined ports before it opens SSH for your IP address.

What this buys is removal from untargeted scanning. It is **not** authentication: the sequence travels in cleartext TCP headers, anyone who can watch the path can replay it, and the default sequence is public. Your SSH keys are still what protect the host. See `specs/port-knocking/` for the requirements behind everything below.

## When Is Port Knocking Active? (KNOCK-1)

Port knocking is active when:
- Tailscale VPN is **disabled** (or not configured)
- `port_knocking_enabled` is **true** (the default)

When Tailscale is enabled, SSH is already hidden behind the VPN and port knocking is not needed.

## Default Knock Sequence (KNOCK-10)

The default sequence is: **7000 → 8500 → 9100**

After a successful knock, SSH opens for your IP for **30 seconds** (KNOCK-7). Once your SSH connection is established, it stays alive regardless of the knock timeout — you do not need to re-knock for an existing session.

The default is published in this repository, so on a host anyone can identify it is worth setting your own sequence. The default is also in ascending order, which means a scanner sweeping ports upward completes it as a side effect; a non-monotonic sequence does not have that weakness.

## How to Knock

### Option 1: `knock` client (recommended)

Install the knock client:

```bash
# Debian/Ubuntu
sudo apt install knockd

# macOS
brew install knock

# Fedora
sudo dnf install knock
```

Knock and connect:

```bash
knock <host> 7000 8500 9100 && ssh user@<host>
```

### Option 2: Bash (no client needed)

Using bash built-in `/dev/tcp`:

```bash
for p in 7000 8500 9100; do
  echo >/dev/tcp/<host>/$p 2>/dev/null
  sleep 0.1
done
ssh user@<host>
```

### Option 3: Netcat

```bash
for p in 7000 8500 9100; do
  nc -z -w1 <host> $p 2>/dev/null
  sleep 0.1
done
ssh user@<host>
```

## Ansible Re-runs (KNOCK-11)

`make bootstrap` knocks for you. A separate play at the top of `site.yml` runs locally on the controller and sends the knock sequence to each host before the play that connects over SSH, so re-running the bootstrap against an already-bootstrapped server needs no extra steps. The knock play is skipped when Tailscale is enabled or port knocking is disabled.

**`make verify` does not.** `tests/verify_bootstrap.yml` is a separate playbook with no knock play of its own, so against a knock-gated host it fails as unreachable before it evaluates anything. Knock by hand first:

```bash
for p in 7000 8500 9100; do nc -z -w1 <host> $p 2>/dev/null; sleep 0.1; done
make verify
```

Running `make verify` within a minute of a `make bootstrap` may also succeed, because Ansible reuses the still-open SSH connection from that run — do not rely on it.

## Customizing the Sequence (KNOCK-10)

Edit your inventory variables:

```yaml
port_knocking_sequence:
  - 4321
  - 8765
  - 2468
```

The sequence must contain exactly 3 ports (KNOCK-2). On a knock-gated host the firewall role checks the length before it renders the ruleset, so a wrong-length sequence fails the run there — after the roles that run before the firewall, such as SSH hardening, have already been applied.

Set `port_knocking_sequence`, not `firewall_port_knocking_sequence`. The playbook's own knock play reads the unprefixed name, so overriding the role-level one moves the firewall rules without moving the knock the playbook sends.

You can also adjust timeouts:

```yaml
port_knocking_timeout: 30        # seconds SSH stays open after knock
port_knocking_stage_timeout: 5   # seconds allowed between knocks
```

## Disabling Port Knocking (KNOCK-1)

To allow SSH without knocking (not recommended for public-facing servers):

```yaml
port_knocking_enabled: false
```

## Troubleshooting

### Check if knock sets exist

```bash
sudo nft list sets
```

### Check if your IP passed the knock

```bash
sudo nft list set inet filter knock4_passed
sudo nft list set inet filter knock6_passed
```

If your IP appears in the set, SSH should be accessible.

### Common issues

- **Knock timeout** (KNOCK-7): You have 5 seconds between each knock port. If you're too slow, the stage entry expires and you must start the sequence again — re-knocking the same port does not buy you more time. Increase `port_knocking_stage_timeout` if needed.
- **Wrong port order**: The sequence must be sent in the exact order configured. Extra packets to unrelated ports in between are harmless; they neither advance nor reset your progress.
- **You just re-ran the playbook**: reloading the firewall empties the knock sets, so a knock you sent before the reload is gone. Existing SSH sessions are unaffected.
- **Firewall blocking knock ports**: Intermediate firewalls or NAT devices may block the knock packets. Use TCP (the default) which works through most firewalls.
- **IPv6 vs IPv4** (KNOCK-9): The knock sequence works identically over both protocols, but progress is tracked per address family. A knock sent over IPv4 opens SSH over IPv4 only, so connect over the same protocol you knocked on.
