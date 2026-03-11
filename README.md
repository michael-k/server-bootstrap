# VPS Bootstrap Playbook

An Ansible playbook that prepares a fresh VPS for regular Ansible management. This playbook executes once manually against a brand-new server using root credentials, establishing secure access patterns, hardening SSH configuration, and optionally configuring Tailscale VPN with firewall restrictions.

**⚠️ Important: This playbook is designed for initial setup only.** Run it once against a fresh VPS to establish secure access and hardened configuration. After bootstrap, use regular Ansible playbooks for ongoing management.

## Prerequisites

Before running this playbook, ensure you have:

1. **Python 3.14 or higher** installed on your local machine, optionally via uv
2. **uv** package manager installed ([installation instructions](https://github.com/astral-sh/uv))
3. **SSH access to the target VPS** as root (password or SSH key)
4. **Fresh VPS running Debian stable** (tested on Debian 13)
5. **SSH key pairs generated** for manual and Ansible users (see below)

### Installing uv

See https://docs.astral.sh/uv/getting-started/installation/.

## Generating SSH Key Pairs

You need two SSH key pairs: one for manual access and one for Ansible automation.

```bash
# Generate manual access user key
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_admin -C "admin@vps"

# Generate Ansible user key
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_ansible -C "ansible@vps"
```

Keep the private keys secure on your local machine. The public keys (`.pub` files) will be deployed to the VPS by the playbook.

## Configuration

### Required Variables

Create an inventory file at `inventory/hosts.yml`:

```yaml
all:
  hosts:
    my-vps:
      ansible_host: 192.0.2.100
      ansible_user: root
      ansible_ssh_pass: "{{ vault_root_password }}"  # Or use SSH key
  
  vars:
    # User configuration
    manual_user_name: "admin"
    manual_user_password: "{{ vault_manual_user_password }}"
    manual_user_ssh_key_file: "~/.ssh/id_ed25519_admin.pub"
    
    ansible_user_name: "ansible"
    ansible_user_ssh_key_file: "~/.ssh/id_ed25519_ansible.pub"
    
    # SSH configuration
    ssh_port: 22
    ssh_max_auth_tries: 3
    ssh_login_grace_time: "30s"
    ssh_client_alive_interval: 300
    ssh_client_alive_count_max: 2
    
    # Tailscale configuration (optional)
    tailscale_enabled: false
    # tailscale_control_server: "https://headscale.example.com"
    # tailscale_pre_auth_key: "{{ vault_tailscale_pre_auth_key }}"
    
    # Fail2ban configuration
    fail2ban_max_retry: 5
    fail2ban_ban_time: "10m"
    fail2ban_find_time: "10m"
    
    # Logging configuration
    journald_max_disk_usage: "500M"
    journald_max_retention_time: "1month"
    
    # Time synchronization
    time_sync_service: "chrony"
    ntp_servers:
      - "0.debian.pool.ntp.org"
      - "1.debian.pool.ntp.org"
      - "2.debian.pool.ntp.org"
      - "3.debian.pool.ntp.org"
    
    # Swap configuration (optional)
    zram_enabled: false
    # zram_size: "50%"  # Percentage of RAM or absolute size (e.g., "2G")
    disk_swap_size: ""  # e.g., "2G" or empty to disable
    
    # Hostname configuration (optional)
    system_hostname: ""  # Leave empty to skip hostname configuration
```

### Secrets Management with Ansible Vault

Sensitive data should be stored in encrypted Vault files. The playbook uses a two-tier vault structure:

#### 1. Group-Level Vault (Shared Secrets)

Create `inventory/group_vars/vault.yml` for secrets shared across all hosts:

```yaml
# Shared secrets - same on all servers
vault_manual_user_password: "$6$rounds=656000$..."  # Use mkpasswd --method=sha-512
```

```bash
# Create from template
cp inventory/group_vars/vault.yml.example inventory/group_vars/vault.yml

# Edit with your secrets
nano inventory/group_vars/vault.yml

# Encrypt the file
uv run ansible-vault encrypt inventory/group_vars/vault.yml
```

#### 2. Host-Level Vault (Per-Host Secrets)

Create `inventory/host_vars/<hostname>/vault.yml` for secrets unique to each host:

```yaml
# Per-host secrets - different for each server
vault_root_password: "your-root-password"
vault_tailscale_pre_auth_key: "tskey-auth-xxxxx"  # If using Tailscale
```

```bash
# Create directory and vault for each host
mkdir -p inventory/host_vars/vps-prod-01
cp inventory/host_vars/vault.yml.example inventory/host_vars/vps-prod-01/vault.yml

# Edit with host-specific secrets
nano inventory/host_vars/vps-prod-01/vault.yml

# Encrypt the file
uv run ansible-vault encrypt inventory/host_vars/vps-prod-01/vault.yml
```

#### Editing Encrypted Vaults

```bash
# Edit group-level vault
uv run ansible-vault edit inventory/group_vars/vault.yml

# Edit host-level vault
uv run ansible-vault edit inventory/host_vars/vps-prod-01/vault.yml
```

#### Why Two Vault Files?

- **Group vault**: Credentials that should be the same on all servers (e.g., admin user password)
- **Host vault**: Credentials unique to each server (e.g., root password, Tailscale pre-auth keys)

This structure prevents accidentally reusing secrets that should be unique per host.

### Variable Documentation

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `manual_user_name` | Yes | - | Username for manual access (human administrator) |
| `manual_user_password` | Yes | - | Hashed password for manual user (from vault) |
| `manual_user_ssh_key_file` | Yes | - | Path to manual user's public SSH key |
| `ansible_user_name` | Yes | - | Username for Ansible automation |
| `ansible_user_ssh_key_file` | Yes | - | Path to Ansible user's public SSH key |
| `ssh_port` | No | 22 | SSH listening port |
| `ssh_max_auth_tries` | No | 3 | Maximum authentication attempts |
| `ssh_login_grace_time` | No | "30s" | Time allowed for authentication |
| `ssh_client_alive_interval` | No | 300 | Seconds between keepalive messages |
| `ssh_client_alive_count_max` | No | 2 | Keepalive messages before disconnect |
| `tailscale_enabled` | No | false | Enable Tailscale VPN integration |
| `tailscale_control_server` | Conditional | - | Headscale control server URL (required if Tailscale enabled) |
| `tailscale_pre_auth_key` | Conditional | - | Pre-authentication key from vault (required if Tailscale enabled) |
| `fail2ban_max_retry` | No | 5 | Failed attempts before ban |
| `fail2ban_ban_time` | No | "10m" | Ban duration |
| `fail2ban_find_time` | No | "10m" | Time window for counting failures |
| `journald_max_disk_usage` | No | "500M" | Maximum journal disk usage |
| `journald_max_retention_time` | No | "1month" | Maximum log retention |
| `time_sync_service` | No | "chrony" | Time sync service (chrony or timesyncd) |
| `ntp_servers` | No | Debian pool | List of NTP servers |
| `zram_enabled` | No | false | Enable zram compressed swap |
| `zram_size` | Conditional | - | Zram size as percentage or absolute (required if zram enabled) |
| `disk_swap_size` | No | "" | Disk swap size (e.g., "2G", empty to disable) |
| `system_hostname` | No | "" | System hostname (empty to skip) |

## Running the Playbook

### Initial Bootstrap

Run the playbook against your fresh VPS:

```bash
make bootstrap
```

Or directly with uv:

```bash
uv run ansible-playbook -i inventory/hosts.yml playbook.yml --ask-vault-pass
```

The playbook will:
1. Update system packages
2. Create manual access and Ansible users
3. Harden SSH configuration
4. Configure firewall (NFTables)
5. Install and configure fail2ban
6. Configure system logging
7. Set up time synchronization
8. Configure swap (if enabled)
9. Optionally install and configure Tailscale VPN

### Verification

After bootstrap, verify the configuration:

```bash
make verify
```

This runs a comprehensive test suite that checks all 44 configuration aspects defined in the requirements.

## Running the Test Suite

The project includes comprehensive tests to verify playbook functionality:

### Run All Tests

```bash
make test
```

### Run Specific Test Categories

```bash
# Unit tests only
make test-unit

# Property-based tests only
make test-property

# Integration tests only
make test-integration
```

### Test Organization

```
tests/
├── unit/              # Specific configuration examples and edge cases
├── property/          # Property-based tests with randomized inputs
├── integration/       # Full bootstrap execution tests
└── verify_bootstrap.yml  # Post-bootstrap verification playbook
```

## Emergency Access

If you enable Tailscale and SSH becomes restricted to the VPN interface, an emergency script is deployed to `/root/emergency-ssh-access.sh` on the target VPS.

### Unrestrict SSH Access

If you lose Tailscale connectivity and need to access SSH via the public interface:

```bash
# On the VPS (via console access)
sudo /root/emergency-ssh-access.sh
```

This temporarily allows SSH access from all interfaces.

### Restore Restricted Access

After fixing Tailscale connectivity, restore the restricted configuration:

```bash
# On the VPS
sudo /root/emergency-ssh-access.sh --restore
```

## Project Structure

```
.
├── ansible.cfg              # Ansible configuration
├── pyproject.toml           # Python dependencies
├── Makefile                 # Common operations
├── README.md                # This file
├── playbook.yml             # Main bootstrap playbook
├── inventory/               # Inventory and variables
│   ├── hosts.yml            # Host definitions and variables
│   └── vault.yml            # Encrypted secrets
├── roles/                   # Ansible roles
│   ├── users/               # User account management
│   ├── ssh_hardening/       # SSH daemon configuration
│   ├── tailscale/           # VPN installation
│   ├── firewall/            # NFTables configuration
│   ├── emergency_access/    # Emergency script deployment
│   ├── fail2ban/            # Intrusion prevention
│   ├── logging/             # Journald configuration
│   ├── time_sync/           # NTP configuration
│   ├── swap/                # Swap management
│   └── system_updates/      # Package updates
└── tests/                   # Test suite
    ├── unit/                # Unit tests
    ├── property/            # Property-based tests
    ├── integration/         # Integration tests
    └── verify_bootstrap.yml # Verification playbook
```

## Security Considerations

### SSH Hardening

The playbook implements comprehensive SSH hardening:
- Disables password authentication globally
- Disables root login
- Restricts to modern cryptographic algorithms
- Disables X11, TCP, and agent forwarding
- Configures session timeouts
- Restricts access to specific users

### Firewall Configuration

NFTables is configured with:
- Default-deny policy
- Stateful connection tracking
- IPv4 and IPv6 support
- Optional SSH restriction to Tailscale interface

### Intrusion Prevention

Fail2ban monitors SSH logs and automatically bans IPs with repeated failed login attempts.

### Secrets Management

All sensitive data (passwords, pre-auth keys) must be stored in Ansible Vault encrypted files.

## Troubleshooting

### Playbook Fails During Execution

Check the Ansible log at `./ansible.log` for detailed error messages.

### Cannot Connect After Bootstrap

1. Verify you're using the correct SSH key for the manual user
2. Check if Tailscale is enabled and you're connecting through the VPN
3. Use the emergency script via console access if needed

### Tailscale Connectivity Issues

The playbook verifies Tailscale connectivity before restricting SSH. If this check fails, the playbook will abort with an error message.

### Test Failures

Run tests with verbose output:

```bash
uv run pytest tests/ -v
```

## License

This project is provided as-is for bootstrapping VPS servers. Modify as needed for your environment.

## Contributing

This playbook is designed for initial VPS setup. For ongoing management, create separate Ansible playbooks that use the established user accounts and access patterns.
