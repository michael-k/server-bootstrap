# Emergency Access

When Tailscale is enabled, SSH access is restricted to the Tailscale interface only. If you lose Tailscale connectivity, you can use the emergency access script to temporarily allow SSH from all interfaces.

This is the break-glass path, and it deliberately makes a host less safe — it is registered as allowance `ALW-1` in the public exposure register of `specs/project/security-invariants.md`, against the "no exposure without an explicit allowance" invariant. See `specs/emergency-access/` for the requirements behind everything below.

## When to Use

Use the emergency script when:
- Tailscale VPN is down or unreachable
- You need to access the server via the public interface
- You're troubleshooting Tailscale connectivity issues
- You need to perform maintenance that requires public SSH access

## Script Location (EMRG-1, EMRG-2)

The script is deployed to `/root/emergency-ssh-access.sh` on the target VPS, owned by root with mode `0700`, and **only when `tailscale_enabled: true`**.

A host with no tailnet does not get the script, because there is no tailnet narrowing to undo. **On a port-knocking host this script does not exist and would not help if it did** — it edits the tailnet-only firewall rule, which a knock-gated host never renders. Recovery from a knock lockout is editing `/etc/nftables.conf` by hand at the console; see `docs/port-knocking.md`.

The bootstrap deploys the script and never runs it (EMRG-17). Nothing becomes reachable because a playbook ran.

## Unrestrict SSH Access (EMRG-3)

If you lose Tailscale connectivity and need public SSH access:

**Via console access (VPS provider's web console):**

```bash
# Log in as root via console
sudo /root/emergency-ssh-access.sh
```

This will:
1. Back up `/etc/ssh/sshd_config` and `/etc/nftables.conf` with a timestamp (EMRG-10)
2. Modify SSHD configuration to listen on all interfaces (`0.0.0.0` and `::`)
3. Update NFTables rules to allow SSH from all interfaces
4. Restart SSHD service (EMRG-6)
5. Reload NFTables rules (EMRG-7)

After running, you can SSH from any IP address.

The script needs root (EMRG-11) and makes no network call of its own (EMRG-12), so it works from a console on a host with no working network at all. If the sshd restart or the nftables reload fails, the script stops with a non-zero exit status rather than reporting success (EMRG-8) — read the last few lines, not just the last one.

## Restore Restricted Access (EMRG-4)

After fixing Tailscale connectivity, restore the restricted configuration:

```bash
sudo /root/emergency-ssh-access.sh --restore
```

This will:
1. Back up both files again (EMRG-10)
2. Modify SSHD configuration to listen only on the Tailscale addresses
3. Update NFTables rules to restrict SSH to the Tailscale interface
4. Restart SSHD service (EMRG-6)
5. Reload NFTables rules (EMRG-7)

Any other argument, or more than one, is refused with a usage message (EMRG-14). `--restore` is the only one the script accepts.

**Order matters: bring the tailnet back first.** The script was rendered with this host's Tailscale addresses baked in, and those addresses only exist while `tailscaled` is running. Running `--restore` while Tailscale is still down writes two `ListenAddress` lines the host cannot bind, so sshd refuses to start (`Cannot bind any address.`) and the script exits non-zero — leaving you with no running sshd and a `sshd_config` that no longer names the public addresses. Check first:

```bash
tailscale status
ip -brief addr show tailscale0
```

If you hit that, the firewall is still open (the script exits before the nftables reload), so restoring `/etc/ssh/sshd_config` from its `.backup.*` copy at the console and running `systemctl restart sshd` puts you back where you were.

## Script Behavior

**Idempotency (EMRG-9):**
- Safe to run multiple times in either mode
- Running unrestrict twice has no additional effect
- Running restore twice has no additional effect
- A run that makes no change also takes no backup

**Round-trip restoration (EMRG-5):**
- Running unrestrict followed by restore returns the host to the configuration it started with: the ruleset comes back byte for byte, and `sshd -T` reports what it reported before
- `/etc/ssh/sshd_config` is not restored byte for byte — the `ListenAddress` lines come back with the right values but move up next to `Port`, and the comment that introduced them is left behind. This is cosmetic; the running configuration is the same
- No manual configuration editing required

**The repair does not survive the next bootstrap run.** The script edits the two files `make bootstrap` renders from templates, so the next run puts the tailnet-only restriction back — both halves, silently, among all the other changes. If you have broken glass and the tailnet is still down, **do not run the playbook against that host** until you have fixed the tailnet or you will lock yourself out again. Re-running after the tailnet is working is the correct way to get back to the narrowed state.

**Existing fail2ban bans are dropped.** Reloading the ruleset flushes every table the kernel holds, fail2ban's included, and the unrestrict direction does that at the moment the SSH port becomes publicly reachable. Bans are re-established as fail2ban sees the offenders again.

## Example Usage Scenario

```bash
# 1. Tailscale goes down, you lose SSH access
# 2. Log in via VPS provider's web console as root

# 3. Unrestrict SSH to allow public access
/root/emergency-ssh-access.sh

# 4. SSH in from your workstation
ssh admin@your-vps-public-ip

# 5. Fix Tailscale issue
sudo systemctl restart tailscaled
sudo tailscale status

# 6. Restore SSH restriction
sudo /root/emergency-ssh-access.sh --restore

# 7. Verify SSH is restricted again
sudo sshd -T | grep listenaddress
# Should show: listenaddress 100.x.x.x (Tailscale IP)
```

## Security Considerations

**When SSH is unrestricted:**
- Your server is exposed to the public internet
- Fail2ban is still active and will ban brute-force attempts
- SSH is still hardened (key-only auth, no root login)
- Restore restrictions as soon as possible

Those last two are what make the allowance defensible rather than merely reversible: what is exposed on the public interface is a daemon that will complete an authentication only against a key it already holds — no password is ever accepted from the network, and root cannot log in by any method.

**Best practices:**
- Only unrestrict when absolutely necessary
- Restore restrictions immediately after fixing Tailscale
- Monitor fail2ban logs during unrestricted period
- Consider using a non-standard SSH port for additional obscurity
- Keep the timestamped backups the script leaves beside the files it edits (`/etc/ssh/sshd_config.backup.*` and `/etc/nftables.conf.backup.*`) — they hold the host's configuration as it was, which nothing else does
- To confirm *whether and when* the break-glass path was used, read the journal rather than the backups: each restart makes sshd log the addresses it bound, so `journalctl -u ssh --since '-7d' | grep 'Server listening'` distinguishes the two directions (`0.0.0.0`/`::` versus the Tailscale addresses). It will not tell you **who** ran the script — the script itself writes nothing to syslog

## Troubleshooting

**Script not found:**
```bash
ls -la /root/emergency-ssh-access.sh
```
- Script is only deployed when `tailscale_enabled: true` (EMRG-2)
- Re-run bootstrap playbook if missing

**Script fails to execute:**
```bash
# Check permissions
ls -la /root/emergency-ssh-access.sh
# Should be: -rwx------ (700)

# Make executable if needed
chmod 700 /root/emergency-ssh-access.sh
```

**Script reports "file not found":**
- The script refuses to act unless both `/etc/ssh/sshd_config` and `/etc/nftables.conf` are present (EMRG-13). Restore the missing one from a backup before retrying.

**Script says SUCCESS but SSH still refuses connections:**
- The script matches the firewall's SSH rule as literal text (EMRG-16), and `sed` does not complain when it matches nothing. Check whether the rule was actually rewritten:
```bash
grep 'dport' /etc/nftables.conf
nft list ruleset | grep -A2 'dport'
```
- If `/etc/nftables.conf` still carries an `iifname` qualifier on the SSH rule, the substitution found nothing and the script's success message was about the sshd half only.

**Changes don't take effect:**
```bash
# Manually restart services
systemctl restart sshd
nft -f /etc/nftables.conf

# Check service status
systemctl status sshd
systemctl status nftables
```
