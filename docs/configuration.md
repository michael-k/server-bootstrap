# Configuration Guide

This guide provides detailed configuration instructions beyond what's in the example files.

## Configuration File Structure

```
inventory/
├── production                    # Inventory file (host definitions)
├── group_vars/
│   ├── all.yml                   # Variables for all hosts
│   └── vault.yml                 # Encrypted shared secrets
└── host_vars/
    └── <hostname>/
        ├── vars.yml              # Host-specific configuration (optional)
        └── vault.yml             # Host-specific secrets (optional, encrypted)
```

## Variable Precedence

Ansible loads variables in this order (lowest to highest precedence):

1. Role defaults (`roles/*/defaults/main.yml`)
2. `inventory/group_vars/all.yml`
3. `inventory/group_vars/vault.yml` (shared secrets)
4. `inventory/group_vars/<group>.yml`
5. `inventory/host_vars/<hostname>/vars.yml`
6. `inventory/host_vars/<hostname>/vault.yml` (highest precedence)

Variables defined in higher precedence files override the same variables in lower precedence files.

## Vault Structure

### Group-Level Vault (Shared Secrets)

Use `inventory/group_vars/vault.yml` for secrets that are the same across all servers:

- Manual user password (same login credentials everywhere)
- Shared API keys
- Shared database credentials

### Host-Level Vault (Per-Host Secrets)

Use `inventory/host_vars/<hostname>/vault.yml` for secrets unique to each server:

- Root password (different for each server)
- Tailscale pre-auth key (unique per server)
- Host-specific API keys

**Why separate vaults?**
- Prevents accidentally reusing secrets that should be unique per host
- Makes it clear which secrets are shared vs. unique
- Simplifies credential rotation

## Generating Hashed Passwords

The manual user password must be a hashed password, not plaintext:

**Method 1: Using mkpasswd (recommended):**
```bash
mkpasswd --method=sha-512
```

**Method 2: Using Python:**
```bash
python3 -c 'import crypt; print(crypt.crypt("your-password", crypt.mksalt(crypt.METHOD_SHA512)))'
```

**Method 3: Using Ansible:**
```bash
uv run ansible localhost -m debug -a "msg={{ 'your-password' | password_hash('sha512') }}"
```

The output will look like: `$6$rounds=656000$randomsalt$longhashstring`

## Tailscale Configuration

### Generating Pre-Auth Keys

From your Headscale server:

```bash
# Generate a single-use key with 24h expiration (recommended)
headscale preauthkeys create --user your-user --reusable=false --expiration 24h

# Generate a reusable key (less secure)
headscale preauthkeys create --user your-user --reusable=true --expiration 90d
```

**Security Note:** Each server should have its own unique pre-auth key. Never reuse keys across multiple servers.

### Headscale Control Server

The control server URL should point to your Headscale instance:

```yaml
tailscale_control_server: "https://headscale.example.com"
```

Ensure the control server is accessible from the VPS before running bootstrap.

## Multiple VPS Management

Organize multiple VPS servers into groups:

```yaml
# inventory/production
all:
  children:
    webservers:
      hosts:
        web-01:
          ansible_host: 203.0.113.20
        web-02:
          ansible_host: 203.0.113.21
    
    databases:
      hosts:
        db-01:
          ansible_host: 203.0.113.30
```

Create group-specific variables:

```yaml
# inventory/group_vars/webservers.yml
zram_enabled: true
zram_size: "1G"
system_hostname: "{{ inventory_hostname }}"

# inventory/group_vars/databases.yml
zram_enabled: true
zram_size: "2G"
disk_swap_size: "4G"
```

Run bootstrap on specific groups:

```bash
# Bootstrap all webservers
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --limit webservers

# Bootstrap specific host
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --limit db-01
```

## Swap Configuration

See the `SWAP CONFIGURATION` section in `inventory/group_vars/all.yml.example` for available variables, strategies, and an explanation of zram vs. disk swap.

## Time Synchronization

### Chrony (Recommended)

More accurate, better for servers:

```yaml
time_sync_service: "chrony"
ntp_servers:
  - "0.debian.pool.ntp.org"
  - "1.debian.pool.ntp.org"
```

### systemd-timesyncd (Simpler)

Simpler, sufficient for most use cases:

```yaml
time_sync_service: "timesyncd"
ntp_servers:
  - "time.cloudflare.com"
  - "time.google.com"
```

## Custom SSH Port

Change SSH to a non-standard port for additional obscurity:

```yaml
ssh_port: 2222
```

After bootstrap, connect with:

```bash
ssh -p 2222 admin@your-vps-ip
```

**Note:** Update your firewall rules if using external firewalls.

## Ansible Tags

Run specific parts of the playbook using tags:

```bash
# Only update packages
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --tags system_updates

# Only configure users
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --tags users

# Skip Tailscale installation
uv run ansible-playbook -i inventory/production site.yml --ask-vault-pass --skip-tags tailscale
```

Available tags:
- `system_updates`
- `users`
- `ssh_hardening`
- `tailscale`
- `firewall`
- `emergency_access`
- `fail2ban`
- `logging`
- `time_sync`
- `swap`
- `system_config`
