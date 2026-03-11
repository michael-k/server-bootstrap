# Troubleshooting

## Cannot Connect to VPS After Bootstrap

**Symptom:** SSH connection refused or times out after running bootstrap.

**Solutions:**

1. **Using wrong SSH key:**
   ```bash
   # Verify you're using the correct key
   ssh -i ~/.ssh/id_ed25519_admin admin@your-vps-ip
   ```

2. **Connecting as root (now disabled):**
   ```bash
   # Use the manual access user, not root
   ssh admin@your-vps-ip  # Correct
   ssh root@your-vps-ip   # Wrong - root login is disabled
   ```

3. **Tailscale enabled but not connected:**
   ```bash
   # If Tailscale is enabled, connect through the VPN
   tailscale status
   ssh admin@100.x.x.x  # Use Tailscale IP
   
   # Or use emergency script via console access
   ```

4. **Firewall blocking connection:**
   ```bash
   # Via console access, check NFTables rules
   sudo nft list ruleset
   
   # Temporarily disable firewall for testing
   sudo systemctl stop nftables
   ```

## Playbook Fails During Execution

**Check the Ansible log:**
```bash
cat ansible.log
```

**Run with verbose output:**
```bash
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass -vvv
```

**Common errors:**

**"Authentication failure":**
```bash
# Check root credentials in inventory
# Test manually
ssh root@your-vps-ip
```

**"Vault password incorrect":**
```bash
# Re-encrypt vault with correct password
uv run ansible-vault decrypt inventory/group_vars/vault.yml
uv run ansible-vault encrypt inventory/group_vars/vault.yml
```

**"Host unreachable":**
```bash
# Check VPS IP address
ping your-vps-ip

# Check SSH port
nc -zv your-vps-ip 22
```

## Tailscale Connectivity Issues

**Check Tailscale service status:**
```bash
# Via console access
sudo systemctl status tailscale
sudo tailscale status
```

**Verify Headscale control server:**
```bash
# Test connectivity
curl -I https://headscale.example.com
```

**Check pre-auth key:**
```bash
# Generate new key from Headscale
headscale preauthkeys create --user your-user --reusable=false --expiration 24h

# Update vault with new key
uv run ansible-vault edit inventory/host_vars/your-vps/vault.yml
```

**Playbook aborts before SSH restriction:**
- This is intentional - the playbook verifies Tailscale connectivity before restricting SSH
- Fix Tailscale issue and re-run playbook
- Or disable Tailscale: `tailscale_enabled: false`

## Test Failures

**Run tests with verbose output:**
```bash
uv run pytest tests/ -v
```

**Run specific failing test:**
```bash
uv run pytest tests/unit/test_ssh_hardening.py::test_specific_test -v
```

**Check test environment:**
```bash
# Ensure dependencies are installed
uv sync

# Check Python version
python3 --version  # Should be 3.14+
```

## Vault Issues

**Forgot vault password:**
```bash
# If you have an unencrypted backup, re-encrypt with new password
cp vault.yml.backup inventory/group_vars/vault.yml
uv run ansible-vault encrypt inventory/group_vars/vault.yml
```

**Vault file corrupted:**
```bash
# Check if file is actually encrypted
head inventory/group_vars/vault.yml
# Should start with: $ANSIBLE_VAULT;1.1;AES256

# If not encrypted, encrypt it
uv run ansible-vault encrypt inventory/group_vars/vault.yml
```

## SSH Key Issues

**Verify key permissions:**
```bash
# Private key should be 600
chmod 600 ~/.ssh/id_ed25519_admin

# Public key should be 644
chmod 644 ~/.ssh/id_ed25519_admin.pub
```

**Verify key is loaded:**
```bash
# Add key to SSH agent
ssh-add ~/.ssh/id_ed25519_admin

# List loaded keys
ssh-add -l
```

**Test key manually:**
```bash
# Test SSH with specific key
ssh -i ~/.ssh/id_ed25519_admin -v admin@your-vps-ip
```

**Verify public key was deployed:**
```bash
# Via console access
sudo cat /home/admin/.ssh/authorized_keys
```

## Idempotency Issues

**Check what's changing:**
```bash
# Run in check mode to see what would change
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --check --diff
```

**Force idempotency:**
```bash
# Run twice - second run should show no changes
make bootstrap
make bootstrap  # Should show mostly "ok", few "changed"
```

## Getting Help

If you encounter issues not covered here:

1. **Check Ansible logs:** `cat ansible.log`
2. **Run with maximum verbosity:** `uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass -vvvv`
3. **Verify prerequisites:** Python 3.14+, uv installed, SSH access as root
4. **Test individual roles:** `uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --tags users`
