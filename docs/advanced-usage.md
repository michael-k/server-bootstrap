# Advanced Usage

## Vault Password Files

For automation or convenience, store the vault password in a file:

```bash
# Create password file
echo "your-vault-password" > .vault-pass
chmod 600 .vault-pass

# Add to .gitignore
echo ".vault-pass" >> .gitignore

# Use with playbook
uv run ansible-playbook -i inventory/production site.yml --vault-password-file .vault-pass
```

**⚠️ Security Warning:** Never commit `.vault-pass` to version control!

## Multiple Vault Passwords

Use different vault passwords for different environments:

```bash
# Development vault
echo "dev-vault-password" > .vault-pass-dev

# Production vault
echo "prod-vault-password" > .vault-pass-prod

# Use with playbook
uv run ansible-playbook -i inventory/production site.yml --vault-password-file .vault-pass-prod
```

## Check Mode (Dry Run)

Preview changes without applying them:

```bash
# See what would change
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --check

# See what would change with diff
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --check --diff
```

## Limiting Execution

Run playbook on specific hosts or groups:

```bash
# Single host
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --limit web-01

# Multiple hosts
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --limit web-01,web-02

# Group
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --limit webservers

# Pattern matching
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --limit 'web-*'
```

## Verbose Output

Increase verbosity for debugging:

```bash
# Level 1: Basic info
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass -v

# Level 2: More details
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass -vv

# Level 3: Debug info
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass -vvv

# Level 4: Connection debugging
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass -vvvv
```

## Syntax Checking

Verify playbook syntax before running:

```bash
uv run ansible-playbook --syntax-check site.yml
```

## Maintenance

### Regular Updates

Run bootstrap periodically to apply system updates:

```bash
# Every 1-2 weeks
make bootstrap
```

This will:
- Install security updates
- Update package lists
- Maintain current configuration
- Report if reboot is required

### Rotating SSH Keys

```bash
# Generate new keys
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_admin_new -C "admin@vps"

# Update inventory
nano inventory/group_vars/all.yml
# Change: manual_user_ssh_key_file: "~/.ssh/id_ed25519_admin_new.pub"

# Re-run bootstrap
make bootstrap

# Test new key
ssh -i ~/.ssh/id_ed25519_admin_new admin@your-vps-ip

# Remove old key from server
ssh admin@your-vps-ip
nano ~/.ssh/authorized_keys  # Remove old key
```

### Rotating Vault Passwords

```bash
# Change vault password
uv run ansible-vault rekey inventory/group_vars/vault.yml

# Update password in password manager
```

### Rotating Tailscale Pre-Auth Keys

```bash
# Generate new key from Headscale
headscale preauthkeys create --user your-user --reusable=false --expiration 24h

# Update host vault
uv run ansible-vault edit inventory/host_vars/your-vps/vault.yml

# Re-run bootstrap
make bootstrap
```

## Monitoring

Check system health regularly:

```bash
# SSH into server
ssh admin@your-vps-ip

# Check fail2ban status
sudo fail2ban-client status sshd

# Check firewall rules
sudo nft list ruleset

# Check Tailscale status
sudo tailscale status

# Check system logs
sudo journalctl -xe

# Check swap usage
sudo swapon --show

# Check time sync
timedatectl status
```

## Backup and Recovery

**Backup configuration:**

```bash
# Backup inventory and vaults
tar -czf vps-config-backup-$(date +%Y%m%d).tar.gz inventory/

# Store securely (encrypted, off-site)
```

**Recovery:**

```bash
# Restore from backup
tar -xzf vps-config-backup-20260311.tar.gz

# Re-run bootstrap
make bootstrap
```

## Best Practices

### Security

1. Use strong passwords - Generate with `pwgen -s 32` or password manager
2. Rotate credentials regularly - Update vault passwords and SSH keys periodically
3. Limit vault access - Only authorized personnel should have vault passwords
4. Use unique pre-auth keys - Never reuse Tailscale keys across servers
5. Monitor fail2ban logs - Check for attack patterns: `sudo journalctl -u fail2ban`
6. Keep systems updated - Re-run bootstrap periodically to apply updates
7. Restrict SSH to VPN - Enable Tailscale for production servers
8. Backup vault files - Store encrypted vaults and passwords separately

### Operations

1. Test in staging first - Always test configuration changes on non-production servers
2. Use version control - Commit inventory and playbook changes to git
3. Document changes - Add comments explaining non-obvious configuration choices
4. Monitor services - Set up monitoring for SSH, Tailscale, fail2ban, etc.
5. Plan for emergencies - Know how to use emergency script and console access
6. Verify after bootstrap - Always run `make verify` after bootstrap
7. Keep backups - Take VPS snapshots before running bootstrap
8. Use check mode - Test changes with `--check` flag before applying
