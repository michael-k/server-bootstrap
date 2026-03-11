# VPS Bootstrap Playbook

An Ansible playbook that prepares a fresh VPS for regular Ansible management. Executes once manually against a brand-new server using root credentials, establishing secure access patterns, hardening SSH configuration, and optionally configuring Tailscale VPN with firewall restrictions.

**⚠️ Important: This playbook is designed for initial setup only.** Run it once against a fresh VPS to establish secure access and hardened configuration.

## Prerequisites

- **Python 3.14+** and **uv** installed locally
- **SSH access to target VPS** as root (password or SSH key)
- **Fresh VPS running Debian 13+** (trixie or newer)
- **SSH key pairs** for manual and Ansible users

## Quick Start

```bash
# 1. Generate SSH keys
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_admin -C "admin@vps"
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_ansible -C "ansible@vps"

# 2. Copy and customize configuration
cp inventory/production.example inventory/production
cp inventory/group_vars/all.yml.example inventory/group_vars/all.yml
cp inventory/group_vars/vault.yml.example inventory/group_vars/vault.yml

# 3. Edit files with your VPS details and secrets
nano inventory/production
nano inventory/group_vars/all.yml
nano inventory/group_vars/vault.yml

# 4. Encrypt vault
uv run ansible-vault encrypt inventory/group_vars/vault.yml

# 5. Run bootstrap
make bootstrap
```

## Configuration

All configuration is done through inventory files. See the example files for detailed documentation:

- **[inventory/production.example](inventory/production.example)** - Host definitions and connection settings
- **[inventory/group_vars/all.yml.example](inventory/group_vars/all.yml.example)** - All configurable variables with descriptions and defaults
- **[inventory/group_vars/vault.yml.example](inventory/group_vars/vault.yml.example)** - Encrypted secrets (passwords, pre-auth keys)
- **[inventory/host_vars/vps-prod-01/vars.yml.example](inventory/host_vars/vps-prod-01/vars.yml.example)** - Host-specific configuration
- **[inventory/host_vars/vps-prod-01/vault.yml.example](inventory/host_vars/vps-prod-01/vault.yml.example)** - Host-specific secrets

### Ansible Vault

Encrypt secrets with Ansible Vault:

```bash
# Encrypt vault file
uv run ansible-vault encrypt inventory/group_vars/vault.yml

# Edit encrypted vault
uv run ansible-vault edit inventory/group_vars/vault.yml

# Change vault password
uv run ansible-vault rekey inventory/group_vars/vault.yml
```

Generate hashed passwords for users:

```bash
mkpasswd --method=sha-512
```

## Running the Playbook

```bash
# Initial bootstrap
make bootstrap

# Verify configuration
make verify

# Run tests
make test
```

The playbook will:
1. Update system packages
2. Create manual access and Ansible users with SSH keys
3. Harden SSH configuration (disable password auth, restrict algorithms)
4. Configure NFTables firewall with default-deny policy
5. Install and configure fail2ban for intrusion prevention
6. Configure journald for persistent logging
7. Set up time synchronization (chrony/timesyncd)
8. Configure swap (zram and/or disk, optional)
9. Install and configure Tailscale VPN (optional)
10. Deploy emergency access script (if Tailscale enabled)

After bootstrap, SSH as the manual user (root login is disabled):

```bash
ssh admin@your-vps-ip
```

## Emergency Access

If Tailscale is enabled and you lose VPN connectivity, use the emergency script via console access to make SSH available via the public internet:

```bash
# Unrestrict SSH (allow from all interfaces)
sudo /root/emergency-ssh-access.sh

# Restore restriction (Tailscale only)
sudo /root/emergency-ssh-access.sh --restore
```

See [docs/emergency-access.md](docs/emergency-access.md) for details.

## Testing

```bash
# Run all tests
make test

# Run specific test types
make test-unit          # Unit tests
make test-property      # Property-based tests with Hypothesis
make test-integration   # Integration tests

# Lint code
make python-lint        # Check Python code
make ansible-lint       # Check Ansible files
```

## Documentation

- **[docs/configuration.md](docs/configuration.md)** - Detailed configuration guide
- **[docs/emergency-access.md](docs/emergency-access.md)** - Emergency access procedures
- **[docs/troubleshooting.md](docs/troubleshooting.md)** - Common issues and solutions
- **[docs/advanced-usage.md](docs/advanced-usage.md)** - Multiple VPS, custom configurations

## Project Structure

```
.
├── ansible.cfg              # Ansible configuration
├── pyproject.toml           # Python dependencies
├── Makefile                 # Common operations
├── site.yml                 # Main bootstrap playbook
├── inventory/               # Inventory and variables
│   ├── production.example
│   ├── group_vars/
│   │   ├── all.yml.example
│   │   └── vault.yml.example
│   └── host_vars/
├── roles/                   # Ansible roles
│   ├── users/
│   ├── ssh_hardening/
│   ├── tailscale/
│   ├── firewall/
│   ├── emergency_access/
│   ├── fail2ban/
│   ├── logging/
│   ├── time_sync/
│   ├── swap/
│   └── system_updates/
├── tests/                   # Test suite
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── verify_bootstrap.yml
└── docs/                    # Additional documentation
```

## Security Considerations

- SSH hardened with modern cryptography (curve25519, chacha20-poly1305, AEAD ciphers)
- Password authentication disabled globally
- Root login disabled
- Default-deny firewall policy
- Fail2ban monitors and blocks brute-force attempts
- Optional SSH restriction to Tailscale VPN interface
- All secrets encrypted with Ansible Vault

## License

Provided as-is for bootstrapping VPS servers. Modify as needed for your environment.
