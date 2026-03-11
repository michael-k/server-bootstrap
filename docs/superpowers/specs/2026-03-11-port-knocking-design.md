# Port Knocking Design

## Goal

Hide SSH from port scanners when Tailscale is disabled by requiring a correct TCP knock sequence before the firewall opens the SSH port. Supports both IPv4 and IPv6.

## When Active

Port knocking activates only when:
- `firewall_tailscale_enabled` is `false` **AND** `firewall_port_knocking_enabled` is `true`

When Tailscale is enabled, SSH is already hidden behind the VPN — knocking adds no value and is skipped entirely.

## Approach

Extend the existing `firewall` role with conditional port knocking logic in the NFTables template. No new role — port knocking is a firewall concern.

## How It Works

NFTables maintains six named sets (3 per address family) tracking knock progress per source IP:

1. Source IP hits port 1 of the sequence → added to `knock4_stage1` / `knock6_stage1` (5s timeout)
2. IP in stage1 hits port 2 → moved to `knock4_stage2` / `knock6_stage2` (5s timeout)
3. IP in stage2 hits port 3 → added to `knock4_passed` / `knock6_passed` (30s timeout)
4. SSH accept rule checks membership in `knock4_passed` / `knock6_passed`

A wrong port or timeout at any stage resets progress (IP expires from the set).

Once the TCP connection is established within the 30-second window, it stays alive as an established connection (matched by the `ct state established,related accept` rule at the top of the input chain) regardless of the knock timeout expiring. Users do not need to re-knock for existing sessions.

## Configurable Defaults

Added to `roles/firewall/defaults/main.yml`, following the existing `firewall_` prefix convention:

```yaml
# Port knocking configuration (active only when Tailscale is disabled)
firewall_port_knocking_enabled: "{{ port_knocking_enabled | default(true) }}"
firewall_port_knocking_sequence: "{{ port_knocking_sequence | default([7000, 8500, 9100]) }}"
firewall_port_knocking_timeout: "{{ port_knocking_timeout | default(30) }}"
firewall_port_knocking_stage_timeout: "{{ port_knocking_stage_timeout | default(5) }}"
```

This follows the existing pattern where firewall defaults reference optional top-level variables (e.g., `firewall_ssh_port: "{{ ssh_port | default(22) }}"`).

### Sequence Length Validation

A pre-task assertion validates that the knock sequence contains exactly 3 ports. The NFTables rules are hardcoded to 3 stages — this validation prevents template rendering errors from misconfigured sequences.

```yaml
- name: Pre-flight - Verify port knocking sequence length
  ansible.builtin.assert:
    that:
      - firewall_port_knocking_sequence | length == 3
    fail_msg: "Port knocking sequence must contain exactly 3 ports, got {{ firewall_port_knocking_sequence | length }}"
    success_msg: "Port knocking sequence has 3 ports"
  when: not (firewall_tailscale_enabled | bool) and (firewall_port_knocking_enabled | bool)
```

This assertion is added to the firewall role's `tasks/main.yml`, before the template deployment task.

## NFTables Rule Structure

Generated conditionally in `roles/firewall/templates/nftables.conf.j2` when port knocking is active (Tailscale disabled and `firewall_port_knocking_enabled` is true).

### Sets (6 total — 3 per address family)

Named sets are defined at the **table level** (inside `table inet filter {}` but outside any chain), as required by NFTables syntax:

```
{% if not (firewall_tailscale_enabled | bool) and (firewall_port_knocking_enabled | bool) %}
    # Port knocking sets — track knock sequence progress per source IP
{% for af, addr_type in [('4', 'ipv4_addr'), ('6', 'ipv6_addr')] %}
    set knock{{ af }}_stage1 { type {{ addr_type }}; flags timeout; timeout {{ firewall_port_knocking_stage_timeout }}s; }
    set knock{{ af }}_stage2 { type {{ addr_type }}; flags timeout; timeout {{ firewall_port_knocking_stage_timeout }}s; }
    set knock{{ af }}_passed { type {{ addr_type }}; flags timeout; timeout {{ firewall_port_knocking_timeout }}s; }
{% endfor %}
{% endif %}
```

### Rules (in input chain)

Generated with a Jinja2 loop over both address families:

```
{% for af, saddr in [('4', 'ip saddr'), ('6', 'ip6 saddr')] %}
        # {{ saddr | replace(' saddr', '') }} knock sequence
        tcp dport {{ firewall_port_knocking_sequence[0] }} add @knock{{ af }}_stage1 { {{ saddr }} }
        tcp dport {{ firewall_port_knocking_sequence[1] }} {{ saddr }} @knock{{ af }}_stage1 add @knock{{ af }}_stage2 { {{ saddr }} }
        tcp dport {{ firewall_port_knocking_sequence[2] }} {{ saddr }} @knock{{ af }}_stage2 add @knock{{ af }}_passed { {{ saddr }} }
{% endfor %}

        # Drop knock port packets after set processing (prevents leakage to later rules/logs)
        tcp dport { {{ firewall_port_knocking_sequence | join(', ') }} } drop

        # SSH access (only for IPs that completed knock)
        tcp dport {{ firewall_ssh_port }} ip saddr @knock4_passed accept
        tcp dport {{ firewall_ssh_port }} ip6 saddr @knock6_passed accept
```

The explicit `drop` after the knock rules ensures knock-port packets are silently consumed, even if logging or other accept rules are added later.

### Template Structure

The existing template has a two-way conditional for Tailscale vs open SSH. This becomes a three-way conditional. The sets are placed at the table level, the rules in the input chain:

```jinja2
table inet filter {
{% if not (firewall_tailscale_enabled | bool) and (firewall_port_knocking_enabled | bool) %}
    # Port knocking sets (must be at table level, not inside chain)
    [set definitions as above]
{% endif %}

    chain input {
        type filter hook input priority 0; policy drop;

        ct state established,related accept
        iif lo accept
        ip protocol icmp accept
        ip6 nexthdr icmpv6 accept

{% if firewall_tailscale_enabled | bool %}
        # Tailscale mode: SSH restricted to Tailscale interface
        iifname "{{ firewall_tailscale_interface }}" tcp dport {{ firewall_ssh_port }} accept
        udp dport {{ firewall_wireguard_port }} accept
{% elif firewall_port_knocking_enabled | bool %}
        # Port knocking mode: SSH only after correct knock sequence
        [knock rules and SSH accept as above]
{% else %}
        # Open mode: SSH from any interface
        tcp dport {{ firewall_ssh_port }} accept
{% endif %}
    }

    chain forward { ... }
    chain output { ... }
}
```

## Fail2ban Interaction

No changes needed to fail2ban configuration. When port knocking is active, brute-force attempts without a completed knock never reach SSHD (dropped by NFTables). If an attacker completes the knock and then brute-forces, fail2ban still works normally — it operates at the application layer via SSHD logs, independent of the firewall. The knock mechanism and fail2ban are complementary layers.

## Files Changed

```
roles/firewall/
├── defaults/main.yml              # Add firewall_port_knocking_* variables
├── tasks/main.yml                 # Add sequence length validation pre-task
└── templates/nftables.conf.j2     # Add conditional knock sets and rules

docs/
└── port-knocking.md               # Client instructions (new file)

tests/
├── verify_bootstrap.yml           # Add knock verification checks
└── property/
    └── test_firewall_properties.py # Add knock property tests
```

## Client Documentation

New file `docs/port-knocking.md` covering:

- What port knocking is and when it's active
- Installing a knock client (`knock` on Debian/Ubuntu: `apt install knockd`, macOS: `brew install knock`)
- One-liner: `knock <host> 7000 8500 9100 && ssh user@host`
- Bash fallback (no client needed): `for p in 7000 8500 9100; do echo >/dev/tcp/<host>/$p 2>/dev/null; sleep 0.1; done && ssh user@host`
- Alternative with `nc`: `for p in 7000 8500 9100; do nc -z -w1 <host> $p 2>/dev/null; sleep 0.1; done && ssh user@host`
- How to customize the sequence (edit `port_knocking_sequence` in inventory)
- Troubleshooting: checking NFTables sets (`nft list set inet filter knock4_passed`), verifying knock ports, timeout issues
- Note that existing SSH sessions survive knock timeout expiry (established connections are not affected)

## Verification

New conditional checks in `verify_bootstrap.yml` (when Tailscale disabled and port knocking enabled):

1. NFTables ruleset contains `knock4_stage1` and `knock6_stage1` sets
2. NFTables ruleset contains `knock4_passed` and `knock6_passed` sets
3. All knock sequence ports are present in the ruleset

## Property Tests

New tests added to `tests/property/test_firewall_properties.py`:

- Knock sets and rules appear in template when Tailscale disabled and `firewall_port_knocking_enabled` true
- Knock sets and rules do NOT appear when Tailscale enabled
- Knock sets and rules do NOT appear when `firewall_port_knocking_enabled` is false
- All sequence ports from default config appear in the template
- SSH accept rule references `knock4_passed` and `knock6_passed` when knocking enabled
- Both `ipv4_addr` and `ipv6_addr` set types present
- Set definitions appear at table level (outside chain blocks)
- Timeout values use the configured variables
- The unconditional SSH accept rule is NOT present when knocking is enabled
- Explicit `drop` rule for knock ports is present
