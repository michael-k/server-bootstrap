# Port Knocking

Port knocking hides the SSH port from network scanners. Instead of leaving SSH open to the internet, the firewall requires you to send a specific sequence of TCP packets to predetermined ports before it opens SSH for your IP address.

## When Is Port Knocking Active?

Port knocking is active when:
- Tailscale VPN is **disabled** (or not configured)
- `port_knocking_enabled` is **true** (the default)

When Tailscale is enabled, SSH is already hidden behind the VPN and port knocking is not needed.

## Default Knock Sequence

The default sequence is: **7000 → 8500 → 9100**

After a successful knock, SSH opens for your IP for **30 seconds**. Once your SSH connection is established, it stays alive regardless of the knock timeout — you do not need to re-knock for an existing session.

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

## Customizing the Sequence

Edit your inventory variables:

```yaml
port_knocking_sequence:
  - 4321
  - 8765
  - 2468
```

The sequence must contain exactly 3 ports.

You can also adjust timeouts:

```yaml
port_knocking_timeout: 30        # seconds SSH stays open after knock
port_knocking_stage_timeout: 5   # seconds between knocks before reset
```

## Disabling Port Knocking

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

- **Knock timeout**: You have 5 seconds between each knock port. If you're too slow, the sequence resets. Increase `port_knocking_stage_timeout` if needed.
- **Wrong port order**: The sequence must be sent in the exact order configured.
- **Firewall blocking knock ports**: Intermediate firewalls or NAT devices may block the knock packets. Use TCP (the default) which works through most firewalls.
- **IPv6 vs IPv4**: The knock sequence works identically over both protocols. Make sure you're connecting over the same protocol you knocked on.
