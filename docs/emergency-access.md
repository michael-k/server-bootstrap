# Emergency Access

When Tailscale is enabled, SSH access is restricted to the Tailscale interface only. If you lose Tailscale connectivity, you can use the emergency access script to temporarily allow SSH from all interfaces.

## When to Use

Use the emergency script when:
- Tailscale VPN is down or unreachable
- You need to access the server via the public interface
- You're troubleshooting Tailscale connectivity issues
- You need to perform maintenance that requires public SSH access

## Script Location

The script is deployed to `/root/emergency-ssh-access.sh` on the target VPS (only when `tailscale_enabled: true`).

## Unrestrict SSH Access

If you lose Tailscale connectivity and need public SSH access:

**Via console access (VPS provider's web console):**

```bash
# Log in as root via console
sudo /root/emergency-ssh-access.sh
```

This will:
1. Modify SSHD configuration to listen on all interfaces (0.0.0.0)
2. Update NFTables rules to allow SSH from all interfaces
3. Restart SSHD service
4. Reload NFTables rules

After running, you can SSH from any IP address.

## Restore Restricted Access

After fixing Tailscale connectivity, restore the restricted configuration:

```bash
sudo /root/emergency-ssh-access.sh --restore
```

This will:
1. Modify SSHD configuration to listen only on Tailscale interface
2. Update NFTables rules to restrict SSH to Tailscale interface
3. Restart SSHD service
4. Reload NFTables rules

## Script Behavior

**Idempotency:**
- Safe to run multiple times in either mode
- Running unrestrict twice has no additional effect
- Running restore twice has no additional effect

**Round-trip restoration:**
- Running unrestrict followed by restore returns to original state
- No manual configuration editing required

## Example Usage Scenario

```bash
# 1. Tailscale goes down, you lose SSH access
# 2. Log in via VPS provider's web console as root

# 3. Unrestrict SSH to allow public access
/root/emergency-ssh-access.sh

# 4. SSH in from your workstation
ssh admin@your-vps-public-ip

# 5. Fix Tailscale issue
sudo systemctl restart tailscale
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

**Best practices:**
- Only unrestrict when absolutely necessary
- Restore restrictions immediately after fixing Tailscale
- Monitor fail2ban logs during unrestricted period
- Consider using a non-standard SSH port for additional obscurity

## Troubleshooting

**Script not found:**
```bash
ls -la /root/emergency-ssh-access.sh
```
- Script is only deployed when `tailscale_enabled: true`
- Re-run bootstrap playbook if missing

**Script fails to execute:**
```bash
# Check permissions
ls -la /root/emergency-ssh-access.sh
# Should be: -rwx------ (700)

# Make executable if needed
chmod 700 /root/emergency-ssh-access.sh
```

**Changes don't take effect:**
```bash
# Manually restart services
systemctl restart sshd
nft -f /etc/nftables.conf

# Check service status
systemctl status sshd
systemctl status nftables
```
