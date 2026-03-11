# VPS Bootstrap Playbook

An Ansible playbook that prepares a fresh VPS for regular Ansible management. This playbook executes once manually against a brand-new server using root credentials, establishing secure access patterns, hardening SSH configuration, and optionally configuring Tailscale VPN with firewall restrictions.

**⚠️ Important: This playbook is designed for initial setup only.** Run it once against a fresh VPS to establish secure access and hardened configuration. After bootstrap, use regular Ansible playbooks for ongoing management.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Generating SSH Key Pairs](#generating-ssh-key-pairs)
- [Configuration](#configuration)
- [Running the Playbook](#running-the-playbook)
- [Verification](#verification)
- [Testing](#testing)
- [Emergency Access](#emergency-access)
- [Project Structure](#project-structure)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before running this playbook, ensure you have:

1. **Python 3.11 or higher** installed on your local machine
2. **uv** package manager installed ([installation instructions](https://docs.astral.sh/uv/getting-started/installation/))
3. **SSH access to the target VPS** as root (password or SSH key)
4. **Fresh VPS running Debian stable** (tested on Debian 12/13)
5. **SSH key pairs generated** for manual and Ansible users (see below)

### Installing uv

uv is a fast Python package manager that handles dependency management and virtual environments automatically.

**Linux/macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Alternative methods:**
```bash
# Using pip
pip install uv

# Using Homebrew (macOS)
brew install uv

# Using pipx
pipx install uv
```

For more installation options, see: https://docs.astral.sh/uv/getting-started/installation/

### Verifying Installation

After installing uv, verify it's working:

```bash
uv --version
```

The playbook will automatically install all required dependencies (Ansible, pytest, hypothesis) when you run it through `make` commands or `uv run`.

## Quick Start

For the impatient, here's the minimal setup:

```bash
# 1. Generate SSH keys
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_admin -C "admin@vps"
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_ansible -C "ansible@vps"

# 2. Copy example inventory and customize
cp inventory/production.example inventory/production
cp inventory/group_vars/all.yml.example inventory/group_vars/all.yml
cp inventory/group_vars/vault.yml.example inventory/group_vars/vault.yml

# 3. Edit inventory files with your VPS details
nano inventory/production
nano inventory/group_vars/all.yml
nano inventory/group_vars/vault.yml

# 4. Encrypt vault
uv run ansible-vault encrypt inventory/group_vars/vault.yml

# 5. Run bootstrap
make bootstrap
```

For detailed instructions, continue reading below.

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

## Configuration

The playbook uses a flexible configuration system with inventory files, group variables, and encrypted vaults.

### Configuration File Structure

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

### Step 1: Create Inventory File

Copy the example and customize for your VPS:

```bash
cp inventory/production.example inventory/production
nano inventory/production
```

**Simple single-VPS example:**

```yaml
all:
  hosts:
    my-vps:
      ansible_host: 203.0.113.10
      ansible_user: root
      # Use SSH key (recommended)
      ansible_ssh_private_key_file: ~/.ssh/id_rsa_root
      # Or use password from vault
      # ansible_ssh_pass: "{{ vault_root_password }}"
```

**Multiple VPS with groups:**

```yaml
all:
  children:
    webservers:
      hosts:
        web-01:
          ansible_host: 203.0.113.20
          ansible_user: root
        web-02:
          ansible_host: 203.0.113.21
          ansible_user: root
    
    databases:
      hosts:
        db-01:
          ansible_host: 203.0.113.30
          ansible_user: root
```

### Step 2: Configure Variables

Copy the example and customize:

```bash
cp inventory/group_vars/all.yml.example inventory/group_vars/all.yml
nano inventory/group_vars/all.yml
```

See [Variable Documentation](#variable-documentation) below for all available options.

### Step 3: Set Up Secrets with Ansible Vault

The playbook uses Ansible Vault to encrypt sensitive data. There are two types of vault files:

#### Group-Level Vault (Shared Secrets)

Secrets that are the same across all servers (e.g., admin user password):

```bash
# Copy example
cp inventory/group_vars/vault.yml.example inventory/group_vars/vault.yml

# Edit with your secrets
nano inventory/group_vars/vault.yml

# Encrypt the file
uv run ansible-vault encrypt inventory/group_vars/vault.yml
```

**Example group vault content (before encryption):**

```yaml
---
# Hashed password for manual access user (same on all servers)
vault_manual_user_password: "$6$rounds=656000$YourSaltHere$YourHashedPasswordHere"
```

**Generate hashed password:**

```bash
# Method 1: Using mkpasswd (recommended)
mkpasswd --method=sha-512

# Method 2: Using Python
python3 -c 'import crypt; print(crypt.crypt("your-password", crypt.mksalt(crypt.METHOD_SHA512)))'

# Method 3: Using Ansible
uv run ansible localhost -m debug -a "msg={{ 'your-password' | password_hash('sha512') }}"
```

#### Host-Level Vault (Per-Host Secrets)

Secrets unique to each server (e.g., root password, Tailscale keys):

```bash
# Create directory for each host
mkdir -p inventory/host_vars/my-vps

# Copy example
cp inventory/host_vars/vps-prod-01/vault.yml.example inventory/host_vars/my-vps/vault.yml

# Edit with host-specific secrets
nano inventory/host_vars/my-vps/vault.yml

# Encrypt the file
uv run ansible-vault encrypt inventory/host_vars/my-vps/vault.yml
```

**Example host vault content (before encryption):**

```yaml
---
# Root password for initial connection (if using password auth)
vault_root_password: "your-root-password"

# Tailscale pre-auth key (if using Tailscale)
vault_tailscale_pre_auth_key: "tskey-auth-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

#### Managing Encrypted Vaults

```bash
# Edit encrypted vault
uv run ansible-vault edit inventory/group_vars/vault.yml

# View encrypted vault without editing
uv run ansible-vault view inventory/group_vars/vault.yml

# Change vault password
uv run ansible-vault rekey inventory/group_vars/vault.yml

# Decrypt vault (not recommended for version control)
uv run ansible-vault decrypt inventory/group_vars/vault.yml
```

#### Using a Vault Password File

For automation or convenience, you can store the vault password in a file:

```bash
# Create password file
echo "your-vault-password" > .vault-pass
chmod 600 .vault-pass

# Add to .gitignore
echo ".vault-pass" >> .gitignore

# Use with playbook
uv run ansible-playbook -i inventory/production playbook.yml --vault-password-file .vault-pass
```

**⚠️ Security Warning:** Never commit `.vault-pass` to version control!

### Variable Documentation

### Variable Documentation

All configurable variables with descriptions, defaults, and requirements:

#### User Configuration (Required)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `manual_user_name` | Yes | - | Username for manual access (human administrator). Created with uid 1000. |
| `manual_user_password` | Yes | - | Hashed password for manual user (from vault). Use `mkpasswd --method=sha-512` to generate. |
| `manual_user_ssh_key_file` | Yes | - | Path to manual user's public SSH key file on the Ansible controller (e.g., `~/.ssh/id_ed25519_admin.pub`). |
| `ansible_user_name` | Yes | - | Username for Ansible automation. Created with uid 1999. |
| `ansible_user_ssh_key_file` | Yes | - | Path to Ansible user's public SSH key file on the Ansible controller (e.g., `~/.ssh/id_ed25519_ansible.pub`). |

**Example:**
```yaml
manual_user_name: "admin"
manual_user_password: "{{ vault_manual_user_password }}"
manual_user_ssh_key_file: "~/.ssh/id_ed25519_admin.pub"
ansible_user_name: "ansible"
ansible_user_ssh_key_file: "~/.ssh/id_ed25519_ansible.pub"
```

#### SSH Hardening Configuration (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ssh_port` | No | 22 | SSH listening port. Change to non-standard port for additional obscurity. |
| `ssh_max_auth_tries` | No | 3 | Maximum authentication attempts before disconnecting. Limits brute-force attacks. |
| `ssh_login_grace_time` | No | "30s" | Time allowed for successful authentication. Reduces exposure window. |
| `ssh_client_alive_interval` | No | 300 | Seconds between keepalive messages. Detects dead connections. |
| `ssh_client_alive_count_max` | No | 2 | Keepalive messages before disconnect. Allows temporary network interruptions. |

**Example:**
```yaml
ssh_port: 22
ssh_max_auth_tries: 3
ssh_login_grace_time: "30s"
ssh_client_alive_interval: 300
ssh_client_alive_count_max: 2
```

#### Tailscale VPN Configuration (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `tailscale_enabled` | No | false | Enable Tailscale VPN integration. When enabled, SSH access is restricted to the Tailscale interface. |
| `tailscale_control_server` | Conditional | - | Headscale control server URL (required if `tailscale_enabled` is true). Example: `https://headscale.example.com` |
| `tailscale_pre_auth_key` | Conditional | - | Pre-authentication key from vault (required if `tailscale_enabled` is true). Generate from Headscale. |
| `tailscale_interface` | No | "tailscale0" | Tailscale network interface name. Used for SSH restriction and firewall rules. |

**Example:**
```yaml
tailscale_enabled: true
tailscale_control_server: "https://headscale.example.com"
tailscale_pre_auth_key: "{{ vault_tailscale_pre_auth_key }}"
tailscale_interface: "tailscale0"
```

**Generating Tailscale Pre-Auth Keys:**

From your Headscale server:
```bash
# Generate a single-use key with 24h expiration
headscale preauthkeys create --user your-user --reusable=false --expiration 24h

# Generate a reusable key (less secure)
headscale preauthkeys create --user your-user --reusable=true --expiration 90d
```

**⚠️ Security Note:** Each server should have its own unique pre-auth key. Never reuse keys across multiple servers.

#### Firewall Configuration

Firewall rules are automatically derived from other configuration variables. No separate firewall-specific variables are required.

- SSH port from `ssh_port`
- Tailscale interface from `tailscale_interface` (when `tailscale_enabled` is true)
- SSH access restriction based on `tailscale_enabled` flag

#### Fail2ban Intrusion Prevention (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `fail2ban_max_retry` | No | 5 | Failed authentication attempts before banning an IP. Balance between security and legitimate user mistakes. |
| `fail2ban_ban_time` | No | "10m" | Duration to ban an IP address. Format: time with unit (s, m, h, d). |
| `fail2ban_find_time` | No | "10m" | Time window for counting failed attempts. Failed attempts within this window count toward max_retry. |

**Example:**
```yaml
fail2ban_max_retry: 5
fail2ban_ban_time: "10m"
fail2ban_find_time: "10m"
```

#### System Logging Configuration (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `journald_max_disk_usage` | No | "500M" | Maximum disk space for journal logs. Prevents logs from consuming excessive disk space. Format: size with unit (K, M, G). |
| `journald_max_retention_time` | No | "1month" | Maximum time to retain journal logs. Balance between log availability and disk usage. Format: time with unit (day, week, month, year). |

**Example:**
```yaml
journald_max_disk_usage: "500M"
journald_max_retention_time: "1month"
```

#### Time Synchronization Configuration (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `time_sync_service` | No | "chrony" | Time synchronization service. Options: "chrony" (recommended, more accurate) or "timesyncd" (simpler). |
| `ntp_servers` | No | Debian pool | List of NTP servers for time synchronization. Use geographically close servers for better accuracy. |

**Example:**
```yaml
time_sync_service: "chrony"
ntp_servers:
  - "0.debian.pool.ntp.org"
  - "1.debian.pool.ntp.org"
  - "2.debian.pool.ntp.org"
  - "3.debian.pool.ntp.org"
```

#### Swap Configuration (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `zram_enabled` | No | false | Enable zram compressed swap in memory. Recommended for VPS with limited RAM (< 2GB). |
| `zram_size` | Conditional | - | Zram device size (required if `zram_enabled` is true). Format: Percentage of RAM (e.g., "50%") or absolute size (e.g., "2G"). |
| `disk_swap_size` | No | "" | Disk swap file size. Format: Size with unit (e.g., "2G") or empty string to disable. Recommended: 1-2x RAM for systems with < 2GB RAM. |

**Swap Priority:**
- Zram swap (if enabled): priority 100 (faster, accessed first)
- Disk swap (if enabled): priority 10 (slower, accessed second)
- Both can be enabled simultaneously for layered swap strategy

**Example:**
```yaml
# Zram only (fast, limited by RAM)
zram_enabled: true
zram_size: "50%"
disk_swap_size: ""

# Disk swap only (slower, larger capacity)
zram_enabled: false
disk_swap_size: "4G"

# Both (layered strategy)
zram_enabled: true
zram_size: "1G"
disk_swap_size: "4G"
```

#### Hostname Configuration (Optional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `system_hostname` | No | "" | System hostname. Leave empty to keep existing hostname. Example: "vps-prod-01" or "web-server-01". |

**Example:**
```yaml
system_hostname: "vps-prod-01"
```

### Configuration Examples

#### Minimal Configuration (No Tailscale)

```yaml
# inventory/group_vars/all.yml
manual_user_name: "admin"
manual_user_password: "{{ vault_manual_user_password }}"
manual_user_ssh_key_file: "~/.ssh/id_ed25519_admin.pub"
ansible_user_name: "ansible"
ansible_user_ssh_key_file: "~/.ssh/id_ed25519_ansible.pub"
```

#### Full Configuration (With Tailscale)

```yaml
# inventory/group_vars/all.yml
manual_user_name: "admin"
manual_user_password: "{{ vault_manual_user_password }}"
manual_user_ssh_key_file: "~/.ssh/id_ed25519_admin.pub"
ansible_user_name: "ansible"
ansible_user_ssh_key_file: "~/.ssh/id_ed25519_ansible.pub"

ssh_port: 22
tailscale_enabled: true
tailscale_control_server: "https://headscale.example.com"
tailscale_pre_auth_key: "{{ vault_tailscale_pre_auth_key }}"

fail2ban_max_retry: 5
fail2ban_ban_time: "10m"

zram_enabled: true
zram_size: "50%"
disk_swap_size: "2G"

system_hostname: "vps-prod-01"
```

## Running the Playbook

### Initial Bootstrap

Once you've configured your inventory and variables, run the bootstrap playbook:

```bash
make bootstrap
```

This will:
1. Prompt for your vault password
2. Connect to the VPS as root
3. Execute all bootstrap tasks

**Alternative methods:**

```bash
# Using uv run directly
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass

# Using a vault password file
uv run ansible-playbook -i inventory/production playbook.yml --vault-password-file .vault-pass

# Limit to specific hosts
make bootstrap ARGS="--limit web-01"
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --limit web-01

# Check mode (dry run)
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --check

# Verbose output for debugging
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass -vvv
```

### What the Playbook Does

The bootstrap playbook executes the following steps in order:

1. **System Updates** - Updates all packages to latest versions
2. **User Creation** - Creates manual access and Ansible users with SSH keys
3. **SSH Hardening** - Configures SSH with modern cryptography and restrictive policies
4. **Tailscale Installation** (optional) - Installs and configures Tailscale VPN
5. **Firewall Configuration** - Sets up NFTables with default-deny policy
6. **Emergency Access** (if Tailscale enabled) - Deploys emergency script to /root/
7. **Fail2ban** - Configures intrusion prevention
8. **Logging** - Configures journald with persistent storage
9. **Time Synchronization** - Sets up NTP service
10. **Swap Configuration** (optional) - Configures zram and/or disk swap
11. **System Configuration** - Sets hostname (if configured)

### Expected Output

Successful execution looks like:

```
PLAY [Bootstrap VPS] ***********************************************************

TASK [Gathering Facts] *********************************************************
ok: [my-vps]

TASK [system_updates : Update apt cache] **************************************
changed: [my-vps]

TASK [system_updates : Upgrade all packages] **********************************
changed: [my-vps]

...

PLAY RECAP *********************************************************************
my-vps                     : ok=45   changed=32   unreachable=0    failed=0    skipped=5    rescued=0    ignored=0
```

### After Bootstrap

After successful bootstrap:

1. **Root SSH access is disabled** - You can no longer SSH as root
2. **Use the manual access user** - SSH with the user you configured:
   ```bash
   ssh admin@your-vps-ip
   ```
3. **Ansible uses the Ansible user** - Future Ansible playbooks should use:
   ```yaml
   ansible_user: ansible
   ansible_ssh_private_key_file: ~/.ssh/id_ed25519_ansible
   ```

### Re-running the Playbook

The playbook is idempotent and safe to re-run:

```bash
make bootstrap
```

On subsequent runs:
- Already-configured items will show "ok" (no changes)
- Only modified configurations will show "changed"
- No errors will occur from existing configuration

This is useful for:
- Updating configuration variables
- Applying new roles or tasks
- Verifying current state

## Verification

After bootstrap, verify the configuration:

```bash
make verify
```

This runs a comprehensive test suite that checks all 44 configuration aspects defined in the requirements.

## Verification

After bootstrap, verify the configuration with the comprehensive test suite:

```bash
make verify
```

This runs 44 verification checks covering:

- User accounts (UIDs, sudo privileges)
- SSH configuration (algorithms, policies, service state)
- Tailscale service and connectivity (if enabled)
- NFTables rules and policies
- Fail2ban, journald, time sync services
- Swap configuration (if enabled)
- Hostname configuration (if set)
- Emergency script deployment (if Tailscale enabled)

**Example output:**

```
TASK [Verify manual user exists with uid 1000] ********************************
ok: [my-vps]

TASK [Verify Ansible user exists with uid 1999] *******************************
ok: [my-vps]

TASK [Verify SSH password authentication is disabled] *************************
ok: [my-vps]

...

PLAY RECAP *********************************************************************
my-vps                     : ok=44   changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

All tasks should show "ok" with 0 failures.

## Testing

## Testing

The project includes comprehensive tests to verify playbook functionality. All tests use property-based testing with Hypothesis to validate correctness across a wide range of inputs.

### Running All Tests

```bash
make test
```

This runs the complete test suite (unit, property-based, and integration tests).

### Running Specific Test Categories

```bash
# Unit tests only (specific examples and edge cases)
make test-unit

# Property-based tests only (randomized inputs with Hypothesis)
make test-property

# Integration tests only (full bootstrap execution)
make test-integration
```

### Test Organization

```
tests/
├── unit/                    # Specific configuration examples and edge cases
│   ├── test_user_management.py
│   ├── test_ssh_hardening.py
│   ├── test_tailscale.py
│   ├── test_firewall.py
│   ├── test_emergency_script.py
│   └── test_system_services.py
├── property/                # Property-based tests with randomized inputs
│   ├── test_idempotency_properties.py
│   ├── test_configuration_properties.py
│   └── test_service_properties.py
├── integration/             # Full bootstrap execution tests
│   └── test_bootstrap_integration.py
└── verify_bootstrap.yml     # Post-bootstrap verification playbook
```

### Understanding Test Output

**Successful test run:**
```
============================= test session starts ==============================
collected 87 items

tests/unit/test_user_management.py ........                              [  9%]
tests/unit/test_ssh_hardening.py ..........                              [ 20%]
tests/property/test_idempotency_properties.py ..................          [ 41%]
tests/integration/test_bootstrap_integration.py ...                      [100%]

============================== 87 passed in 45.23s ==============================
```

**Failed test:**
```
FAILED tests/unit/test_ssh_hardening.py::test_ssh_port_configuration - AssertionError
```

Run with verbose output for details:
```bash
make test ARGS="-v"
# or
uv run pytest tests/ -v
```

### Property-Based Testing

The test suite uses Hypothesis for property-based testing, which:

- Generates hundreds of random test cases automatically
- Finds edge cases that manual tests might miss
- Validates universal correctness properties

Example property test:
```python
@given(st.integers(min_value=1024, max_value=65535))
def test_ssh_port_configuration(port):
    """SSH daemon should listen on any valid configured port."""
    # Test validates this property holds for all valid ports
```

### Linting and Code Quality

```bash
# Check Python code with ruff
make python-lint

# Auto-fix Python code issues
make python-lint-fix

# Check Ansible files with ansible-lint
make ansible-lint

# Auto-fix Ansible files
make ansible-lint-fix

# Check specific paths
make ansible-lint ARGS="roles/users/"
make ansible-lint-fix ARGS="roles/firewall/"
```

## Emergency Access

When Tailscale is enabled, SSH access is restricted to the Tailscale interface only. If you lose Tailscale connectivity, you can use the emergency access script to temporarily allow SSH from all interfaces.

### When to Use Emergency Access

Use the emergency script when:
- Tailscale VPN is down or unreachable
- You need to access the server via the public interface
- You're troubleshooting Tailscale connectivity issues
- You need to perform maintenance that requires public SSH access

### Emergency Script Location

The script is deployed to `/root/emergency-ssh-access.sh` on the target VPS (only when Tailscale is enabled).

### Unrestrict SSH Access

If you lose Tailscale connectivity and need public SSH access:

**Via console access (VPS provider's web console):**

```bash
# Log in as root via console
sudo /root/emergency-ssh-access.sh
```

**Via existing SSH session:**

```bash
# If you still have an active SSH session
sudo /root/emergency-ssh-access.sh
```

This will:
1. Modify SSHD configuration to listen on all interfaces (0.0.0.0)
2. Update NFTables rules to allow SSH from all interfaces
3. Restart SSHD service
4. Reload NFTables rules

After running, you can SSH from any IP address.

### Restore Restricted Access

After fixing Tailscale connectivity, restore the restricted configuration:

```bash
sudo /root/emergency-ssh-access.sh --restore
```

This will:
1. Modify SSHD configuration to listen only on Tailscale interface
2. Update NFTables rules to restrict SSH to Tailscale interface
3. Restart SSHD service
4. Reload NFTables rules

### Script Behavior

**Idempotency:**
- Safe to run multiple times in either mode
- Running unrestrict twice has no additional effect
- Running restore twice has no additional effect

**Round-trip restoration:**
- Running unrestrict followed by restore returns to original state
- No manual configuration editing required

**Safety:**
- Script checks for existing configuration before making changes
- Service restarts are handled automatically
- Changes take effect immediately

### Example Usage Scenario

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

### Security Considerations

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

### Troubleshooting Emergency Script

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

### Common Issues and Solutions

#### Cannot Connect to VPS After Bootstrap

**Symptom:** SSH connection refused or times out after running bootstrap.

**Possible causes and solutions:**

1. **Using wrong SSH key:**
   ```bash
   # Verify you're using the correct key
   ssh -i ~/.ssh/id_ed25519_admin admin@your-vps-ip
   ```

2. **Connecting as root (now disabled):**
   ```bash
   # Don't use root - use the manual access user
   ssh admin@your-vps-ip  # Correct
   ssh root@your-vps-ip   # Wrong - root login is disabled
   ```

3. **Tailscale enabled but not connected:**
   ```bash
   # If Tailscale is enabled, you must connect through the VPN
   # Check Tailscale status on your local machine
   tailscale status
   
   # Connect to VPS via Tailscale IP
   ssh admin@100.x.x.x
   
   # Or use emergency script via console access
   ```

4. **Firewall blocking connection:**
   ```bash
   # Via console access, check NFTables rules
   sudo nft list ruleset
   
   # Temporarily disable firewall for testing
   sudo systemctl stop nftables
   
   # If this fixes it, check firewall configuration
   ```

#### Playbook Fails During Execution

**Symptom:** Ansible playbook fails with error message.

**Solutions:**

1. **Check the Ansible log:**
   ```bash
   cat ansible.log
   ```

2. **Run with verbose output:**
   ```bash
   uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass -vvv
   ```

3. **Common errors:**

   **"Authentication failure":**
   ```bash
   # Check root credentials in inventory
   # Verify SSH key or password is correct
   ssh root@your-vps-ip  # Test manually
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

   **"Permission denied":**
   ```bash
   # Ensure you're connecting as root for initial bootstrap
   # Check ansible_user in inventory
   ```

#### Tailscale Connectivity Issues

**Symptom:** Tailscale fails to connect or verify.

**Solutions:**

1. **Check Tailscale service status:**
   ```bash
   # Via console access
   sudo systemctl status tailscale
   sudo tailscale status
   ```

2. **Verify Headscale control server:**
   ```bash
   # Test connectivity to control server
   curl -I https://headscale.example.com
   ```

3. **Check pre-auth key:**
   ```bash
   # Ensure key is valid and not expired
   # Generate new key from Headscale:
   headscale preauthkeys create --user your-user --reusable=false --expiration 24h
   
   # Update vault with new key
   uv run ansible-vault edit inventory/host_vars/your-vps/vault.yml
   ```

4. **Playbook aborts before SSH restriction:**
   - This is intentional - the playbook verifies Tailscale connectivity before restricting SSH
   - Fix Tailscale issue and re-run playbook
   - Or disable Tailscale: `tailscale_enabled: false`

#### Test Failures

**Symptom:** Tests fail when running `make test`.

**Solutions:**

1. **Run tests with verbose output:**
   ```bash
   uv run pytest tests/ -v
   ```

2. **Run specific failing test:**
   ```bash
   uv run pytest tests/unit/test_ssh_hardening.py::test_specific_test -v
   ```

3. **Check test environment:**
   ```bash
   # Ensure dependencies are installed
   uv sync
   
   # Check Python version
   python3 --version  # Should be 3.11+
   ```

4. **Property-based test failures:**
   - Hypothesis may find edge cases
   - Check the failing example in test output
   - This indicates a real issue that needs fixing

#### Vault Issues

**Symptom:** Cannot decrypt or edit vault files.

**Solutions:**

1. **Forgot vault password:**
   ```bash
   # If you have an unencrypted backup, re-encrypt with new password
   cp vault.yml.backup inventory/group_vars/vault.yml
   uv run ansible-vault encrypt inventory/group_vars/vault.yml
   ```

2. **Vault file corrupted:**
   ```bash
   # Check if file is actually encrypted
   head inventory/group_vars/vault.yml
   # Should start with: $ANSIBLE_VAULT;1.1;AES256
   
   # If not encrypted, encrypt it
   uv run ansible-vault encrypt inventory/group_vars/vault.yml
   ```

3. **Multiple vault passwords:**
   ```bash
   # Use --vault-id to specify which vault
   uv run ansible-vault edit --vault-id group@prompt inventory/group_vars/vault.yml
   uv run ansible-vault edit --vault-id host@prompt inventory/host_vars/vps-01/vault.yml
   ```

#### SSH Key Issues

**Symptom:** SSH key authentication fails.

**Solutions:**

1. **Verify key permissions:**
   ```bash
   # Private key should be 600
   chmod 600 ~/.ssh/id_ed25519_admin
   
   # Public key should be 644
   chmod 644 ~/.ssh/id_ed25519_admin.pub
   ```

2. **Verify key is loaded:**
   ```bash
   # Add key to SSH agent
   ssh-add ~/.ssh/id_ed25519_admin
   
   # List loaded keys
   ssh-add -l
   ```

3. **Test key manually:**
   ```bash
   # Test SSH with specific key
   ssh -i ~/.ssh/id_ed25519_admin -v admin@your-vps-ip
   ```

4. **Verify public key was deployed:**
   ```bash
   # Via console access
   sudo cat /home/admin/.ssh/authorized_keys
   
   # Should contain your public key
   ```

#### Idempotency Issues

**Symptom:** Re-running playbook shows unexpected changes.

**Solutions:**

1. **Check what's changing:**
   ```bash
   # Run in check mode to see what would change
   uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --check --diff
   ```

2. **Review changed tasks:**
   - Some tasks may legitimately change (e.g., package updates)
   - Configuration changes should only occur if variables changed
   - Service restarts are normal if configuration changed

3. **Force idempotency:**
   ```bash
   # Run twice - second run should show no changes
   make bootstrap
   make bootstrap  # Should show mostly "ok", few "changed"
   ```

#### Performance Issues

**Symptom:** Playbook runs slowly or times out.

**Solutions:**

1. **Enable pipelining:**
   ```ini
   # ansible.cfg (already configured)
   [ssh_connection]
   pipelining = True
   ```

2. **Increase timeout:**
   ```bash
   # For slow connections
   uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --timeout=60
   ```

3. **Check network latency:**
   ```bash
   # Test connection speed
   ping -c 10 your-vps-ip
   
   # Test SSH connection time
   time ssh admin@your-vps-ip exit
   ```

### Getting Help

If you encounter issues not covered here:

1. **Check Ansible logs:**
   ```bash
   cat ansible.log
   ```

2. **Run with maximum verbosity:**
   ```bash
   uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass -vvvv
   ```

3. **Verify prerequisites:**
   - Python 3.11+ installed
   - uv installed and working
   - SSH access to VPS as root
   - Correct inventory configuration
   - Valid vault passwords

4. **Test individual roles:**
   ```bash
   # Test specific role
   uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --tags users
   ```

5. **Check system requirements:**
   - VPS running Debian 12/13
   - Minimum 512MB RAM
   - At least 10GB disk space
   - Network connectivity

### Debug Mode

Enable debug mode for detailed troubleshooting:

```bash
# Set environment variable
export ANSIBLE_DEBUG=1

# Run playbook
make bootstrap

# Or with uv run
ANSIBLE_DEBUG=1 uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass -vvvv
```

### Rollback

If bootstrap fails partway through:

1. **Restore from VPS provider snapshot** (if available)
2. **Or manually revert changes:**
   ```bash
   # Via console access as root
   
   # Re-enable root login temporarily
   sed -i 's/PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config
   systemctl restart sshd
   
   # Remove created users if needed
   userdel -r admin
   userdel -r ansible
   
   # Restore original sshd_config
   cp /etc/ssh/sshd_config.backup /etc/ssh/sshd_config
   systemctl restart sshd
   ```

3. **Re-run bootstrap after fixing issues**

## Advanced Usage

### Multiple VPS Management

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
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --limit webservers

# Bootstrap specific host
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --limit db-01
```

### Custom SSH Port

Change SSH to a non-standard port for additional obscurity:

```yaml
# inventory/group_vars/all.yml
ssh_port: 2222
```

After bootstrap, connect with:

```bash
ssh -p 2222 admin@your-vps-ip
```

### Different Time Sync Services

Choose between chrony (more accurate) and systemd-timesyncd (simpler):

```yaml
# Use chrony (recommended)
time_sync_service: "chrony"

# Or use systemd-timesyncd
time_sync_service: "timesyncd"
```

### Custom NTP Servers

Use geographically closer or private NTP servers:

```yaml
ntp_servers:
  - "time.cloudflare.com"
  - "time.google.com"
  - "ntp.example.com"  # Your private NTP server
```

### Layered Swap Strategy

Combine zram (fast) and disk swap (large) for optimal performance:

```yaml
# Fast compressed swap in RAM
zram_enabled: true
zram_size: "1G"

# Larger disk-based swap as fallback
disk_swap_size: "4G"
```

The system will use zram first (priority 100), then fall back to disk swap (priority 10) when needed.

### Ansible Tags

Run specific parts of the playbook using tags:

```bash
# Only update packages
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --tags system_updates

# Only configure users
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --tags users

# Skip Tailscale installation
uv run ansible-playbook -i inventory/production playbook.yml --ask-vault-pass --skip-tags tailscale
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

## Best Practices

### Security

1. **Use strong passwords** - Generate with `pwgen -s 32` or password manager
2. **Rotate credentials regularly** - Update vault passwords and SSH keys periodically
3. **Limit vault access** - Only authorized personnel should have vault passwords
4. **Use unique pre-auth keys** - Never reuse Tailscale keys across servers
5. **Monitor fail2ban logs** - Check for attack patterns: `sudo journalctl -u fail2ban`
6. **Keep systems updated** - Re-run bootstrap periodically to apply updates
7. **Use SSH keys only** - Never enable password authentication for SSH
8. **Restrict SSH to VPN** - Enable Tailscale for production servers
9. **Backup vault files** - Store encrypted vaults and passwords separately
10. **Audit access** - Review who has access to servers and vault passwords

### Operations

1. **Test in staging first** - Always test configuration changes on non-production servers
2. **Use version control** - Commit inventory and playbook changes to git
3. **Document changes** - Add comments explaining non-obvious configuration choices
4. **Monitor services** - Set up monitoring for SSH, Tailscale, fail2ban, etc.
5. **Plan for emergencies** - Know how to use emergency script and console access
6. **Verify after bootstrap** - Always run `make verify` after bootstrap
7. **Keep backups** - Take VPS snapshots before running bootstrap
8. **Use check mode** - Test changes with `--check` flag before applying
9. **Review logs** - Check `ansible.log` after each run
10. **Maintain documentation** - Update README when adding custom configurations

### Development

1. **Run tests before committing** - `make test` should pass
2. **Lint code** - `make python-lint` and `make ansible-lint` should pass
3. **Use property-based tests** - Add Hypothesis tests for new features
4. **Test idempotency** - Ensure playbook can be re-run safely
5. **Document variables** - Add descriptions to all new variables
6. **Follow Ansible best practices** - Use handlers, templates, and proper task naming
7. **Keep roles focused** - Each role should have a single responsibility
8. **Use meaningful commit messages** - Explain what and why, not just what
9. **Review before merging** - Have another person review configuration changes
10. **Test on fresh VPS** - Verify bootstrap works on clean Debian installation

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

### Rotating Credentials

**SSH Keys:**

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

**Vault Passwords:**

```bash
# Change vault password
uv run ansible-vault rekey inventory/group_vars/vault.yml

# Update password in password manager
```

**Tailscale Pre-Auth Keys:**

```bash
# Generate new key from Headscale
headscale preauthkeys create --user your-user --reusable=false --expiration 24h

# Update host vault
uv run ansible-vault edit inventory/host_vars/your-vps/vault.yml

# Re-run bootstrap
make bootstrap
```

### Monitoring

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

### Backup and Recovery

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

## FAQ

**Q: Can I run this on Ubuntu instead of Debian?**

A: The playbook is designed for Debian stable. Ubuntu may work but is untested. You may need to adjust package names and paths.

**Q: Can I use this for existing servers?**

A: Yes, the playbook is idempotent. However, it will modify SSH configuration and firewall rules, which could lock you out if not careful. Test thoroughly first.

**Q: Do I need Tailscale?**

A: No, Tailscale is optional. Set `tailscale_enabled: false` to skip VPN configuration and allow SSH from all interfaces.

**Q: Can I change the user UIDs?**

A: UIDs are fixed (1000 for manual user, 1999 for Ansible user) for consistency. Changing them requires modifying the roles.

**Q: How do I add more users?**

A: This playbook creates two users for bootstrap. For additional users, create a separate Ansible playbook that runs after bootstrap.

**Q: Can I use password authentication for SSH?**

A: No, password authentication is disabled for security. The playbook only supports SSH key authentication.

**Q: What if I lose my SSH keys?**

A: Use your VPS provider's console access to log in and add new keys to `~/.ssh/authorized_keys`, or use the emergency script if Tailscale is enabled.

**Q: How do I uninstall/revert changes?**

A: The easiest way is to restore from a VPS snapshot. Manual reversion requires undoing all configuration changes, which is complex.

**Q: Can I run this in production?**

A: Yes, this playbook is designed for production use. Test thoroughly in staging first, and ensure you have console access as a backup.

**Q: How often should I run bootstrap?**

A: Run every 1-2 weeks for security updates, or whenever you change configuration variables.

## License

This project is provided as-is for bootstrapping VPS servers. Modify as needed for your environment.

## Contributing

This playbook is designed for initial VPS setup. For ongoing management, create separate Ansible playbooks that use the established user accounts and access patterns.

Contributions are welcome! Please:
1. Test changes on a fresh Debian VPS
2. Run `make test` to ensure all tests pass
3. Run `make python-lint` and `make ansible-lint` to check code quality
4. Update documentation for new features
5. Add property-based tests for new functionality
