# Design Document: VPS Bootstrap Playbook

## Overview

The VPS Bootstrap Playbook is a single-execution Ansible automation that transforms a fresh VPS from root-only access to a hardened, production-ready state. The playbook establishes secure access patterns through dedicated user accounts, hardens SSH configuration with modern cryptographic standards, optionally integrates Tailscale VPN with firewall restrictions, and configures essential system services including intrusion prevention, logging, time synchronization, and swap management.

### Design Goals

1. **Security First**: Eliminate common attack vectors through SSH hardening, firewall configuration, and intrusion prevention
2. **Idempotency**: Safe to re-run without side effects, reporting only actual changes
3. **Flexibility**: Support both VPN-restricted and public SSH access patterns through configuration
4. **Recoverability**: Provide emergency access mechanisms when VPN connectivity fails
5. **Testability**: Include comprehensive automated verification of all configuration aspects
6. **Modern Tooling**: Use contemporary Python dependency management (uv, pyproject.toml) for reproducible execution

### Execution Model

The playbook executes once manually against a brand-new server using root credentials (password or SSH key). After successful execution, the root account is locked down, and all future access occurs through the dedicated user accounts. The playbook is designed to be idempotent, allowing re-execution for configuration updates or verification.

## Architecture

### High-Level Architecture

```mermaid
graph TB
    subgraph "Execution Environment"
        Operator[System Administrator]
        AnsibleController[Ansible Controller<br/>with uv + pyproject.toml]
    end
    
    subgraph "Target VPS"
        subgraph "Access Layer"
            SSHD[SSH Daemon<br/>Hardened Config]
            ManualUser[Manual Access User<br/>uid 1000]
            AnsibleUser[Ansible User<br/>uid 1999]
        end
        
        subgraph "Network Layer"
            NFTables[NFTables Firewall<br/>IPv4 + IPv6]
            Tailscale[Tailscale VPN<br/>Optional]
            Fail2ban[Fail2ban<br/>Intrusion Prevention]
        end
        
        subgraph "System Services"
            Journald[Journald Logging]
            TimeSync[Time Synchronization<br/>chrony/timesyncd]
            Swap[Swap Management<br/>zram + disk]
        end
        
        subgraph "Emergency Tools"
            EmergencyScript[Emergency Access Script<br/>/root/]
        end
    end
    
    Operator -->|Initial Bootstrap| AnsibleController
    AnsibleController -->|Ansible Playbook<br/>root credentials| SSHD
    SSHD --> ManualUser
    SSHD --> AnsibleUser
    ManualUser -.->|Future Access| Operator
    AnsibleUser -.->|Future Automation| AnsibleController
    
    Tailscale -->|Restricts| SSHD
    NFTables -->|Filters| SSHD
    Fail2ban -->|Monitors| SSHD
    Fail2ban -->|Updates| NFTables
    
    EmergencyScript -.->|Toggles| SSHD
    EmergencyScript -.->|Toggles| NFTables
```

### Architectural Layers

1. **Access Layer**: User account management and SSH daemon configuration
   - Creates two dedicated user accounts with distinct privilege models
   - Hardens SSH with modern cryptographic algorithms and restrictive policies
   - Supports interface-based access restrictions when VPN is enabled

2. **Network Layer**: Firewall, VPN, and intrusion prevention
   - NFTables provides stateful packet filtering for IPv4 and IPv6
   - Optional Tailscale VPN creates a secure overlay network
   - Fail2ban monitors authentication logs and dynamically blocks malicious IPs

3. **System Services Layer**: Core system functionality
   - Journald manages persistent system logging with configurable retention
   - Time synchronization ensures accurate timestamps for logs and certificates
   - Swap configuration (zram and/or disk) provides memory pressure relief

4. **Emergency Tools Layer**: Recovery mechanisms
   - Emergency script allows toggling SSH restrictions when VPN fails
   - Deployed only when Tailscale is enabled

### Role-Based Organization

The playbook is organized into logical Ansible roles, each responsible for a specific aspect of system configuration:

```
roles/
├── users/              # User account creation and SSH key deployment
├── ssh_hardening/      # SSH daemon configuration and service management
├── tailscale/          # VPN installation and authentication
├── firewall/           # NFTables configuration and rule management
├── emergency_access/   # Emergency script deployment
├── fail2ban/           # Intrusion prevention configuration
├── logging/            # Journald configuration
├── time_sync/          # NTP service configuration
├── swap/               # Swap space configuration (zram and disk)
└── system_updates/     # Package updates and system maintenance
```

Each role follows Ansible best practices with tasks, handlers, templates, and defaults organized in standard directories.

## Components and Interfaces

### User Management Component

**Responsibilities**:
- Create Manual_Access_User (uid 1000) with password and SSH key authentication
- Create Ansible_User (uid 1999) with SSH key-only authentication
- Configure sudo privileges (password-required for manual user, passwordless for Ansible user)
- Deploy SSH public keys to authorized_keys files with correct permissions

**Interfaces**:
- Input: Configuration variables (usernames, public key paths, manual user password)
- Output: User accounts in /etc/passwd, /etc/shadow, /etc/sudoers.d/
- Dependencies: None (executes first)

**Key Design Decisions**:
- Fixed UIDs ensure consistency across deployments and simplify permission management
- Separate authentication models reflect different use cases (human vs automation)
- Public key files are read from the controller and deployed to target

### SSH Hardening Component

**Responsibilities**:
- Configure SSH daemon with modern cryptographic algorithms
- Restrict authentication methods to public key only
- Disable dangerous features (X11, TCP forwarding, agent forwarding, tunneling)
- Restrict access to specific users
- Configure session timeouts and connection limits
- Optionally restrict listening interface to Tailscale

**Interfaces**:
- Input: Configuration variables (port, allowed users, Tailscale interface)
- Output: /etc/ssh/sshd_config
- Dependencies: User Management (requires user accounts to exist)
- Handlers: Restart sshd service on configuration changes

**Key Design Decisions**:
- Template-based configuration ensures consistency and version control
- Modern algorithm restrictions (curve25519, chacha20-poly1305, AEAD ciphers)
- Interface restriction happens after Tailscale connectivity verification
- Service restart uses handlers to avoid unnecessary restarts

**Cryptographic Standards**:
- Key Exchange: curve25519-sha256, curve25519-sha256@libssh.org, diffie-hellman-group16-sha512, diffie-hellman-group18-sha512
- Ciphers: chacha20-poly1305@openssh.com, aes256-gcm@openssh.com, aes128-gcm@openssh.com
- MACs: hmac-sha2-512-etm@openssh.com, hmac-sha2-256-etm@openssh.com

### Tailscale Component

**Responsibilities**:
- Install Tailscale from official repository
- Authenticate with Headscale control server using pre-auth key
- Configure and start Tailscale service
- Verify connectivity before SSH restriction

**Interfaces**:
- Input: Configuration variables (enable flag, control server URL, pre-auth key from Vault)
- Output: Tailscale installation, /etc/tailscale/, tailscale0 interface
- Dependencies: None (but must complete before SSH interface restriction)
- External: Headscale control server (network dependency)

**Key Design Decisions**:
- Conditional execution based on enable flag
- Pre-auth key stored in Ansible Vault for security
- Connectivity verification prevents lockout scenarios
- Service enabled for automatic startup on boot

### Firewall Component

**Responsibilities**:
- Configure NFTables rules for IPv4 and IPv6
- Implement default-deny policy with explicit allow rules
- Restrict SSH access based on Tailscale status
- Allow Tailscale WireGuard traffic when VPN is enabled
- Persist rules across reboots

**Interfaces**:
- Input: Configuration variables (SSH port, Tailscale interface, Tailscale enabled flag)
- Output: /etc/nftables.conf
- Dependencies: Tailscale (when enabled, requires interface to exist)
- Handlers: Reload nftables service on configuration changes

**Key Design Decisions**:
- Separate tables for IPv4 and IPv6 with consistent policies
- Stateful firewall (established/related connections allowed)
- Loopback traffic always allowed
- Template-based rules with conditional SSH restrictions
- Service enabled for automatic rule loading on boot

**Firewall Rules Structure**:
```
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        
        # Allow established/related
        ct state established,related accept
        
        # Allow loopback
        iif lo accept
        
        # Allow SSH (interface-restricted or all)
        [conditional based on Tailscale]
        
        # Allow Tailscale WireGuard (if enabled)
        [conditional based on Tailscale]
    }
    
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
}
```

### Emergency Access Component

**Responsibilities**:
- Deploy emergency script to /root/
- Provide mechanism to toggle SSH restrictions
- Modify both SSHD configuration and NFTables rules
- Support restore operation to return to restricted state

**Interfaces**:
- Input: Configuration variables (Tailscale enabled flag, SSH port, Tailscale interface)
- Output: /root/emergency-ssh-access.sh (executable script)
- Dependencies: SSH Hardening, Firewall (modifies their configurations)

**Key Design Decisions**:
- Deployed only when Tailscale is enabled
- Idempotent operations (safe to run multiple times)
- Modifies configuration files in-place using sed
- Restarts services after configuration changes
- Two modes: unrestrict (default) and restore (with --restore flag)

**Script Operations**:
- Unrestrict mode: Changes ListenAddress to 0.0.0.0, updates NFTables to allow SSH from all interfaces
- Restore mode: Changes ListenAddress to Tailscale IP, updates NFTables to restrict SSH to Tailscale interface
- Both modes: Restart sshd, reload nftables

### Fail2ban Component

**Responsibilities**:
- Install fail2ban from Debian repository
- Configure SSH monitoring with configurable ban thresholds
- Integrate with NFTables for IP blocking
- Configure ban duration and retry limits

**Interfaces**:
- Input: Configuration variables (max retries, ban duration)
- Output: /etc/fail2ban/jail.local, /etc/fail2ban/jail.d/
- Dependencies: SSH Hardening (monitors sshd), Firewall (uses nftables)
- External: Journald logs (data source)

**Key Design Decisions**:
- Uses journald backend for log monitoring
- NFTables integration for consistent firewall management
- Configurable thresholds allow tuning for different threat models
- Service enabled for automatic startup on boot

### Logging Component

**Responsibilities**:
- Configure journald for persistent disk logging
- Set maximum disk usage limits
- Configure log retention time
- Restart journald service after configuration changes

**Interfaces**:
- Input: Configuration variables (max disk usage, retention time)
- Output: /etc/systemd/journald.conf
- Dependencies: None
- Handlers: Restart systemd-journald service

**Key Design Decisions**:
- Persistent storage ensures logs survive reboots
- Configurable limits prevent disk exhaustion
- Template-based configuration for consistency

### Time Synchronization Component

**Responsibilities**:
- Install and configure time synchronization service
- Configure reliable NTP servers
- Verify synchronization status after service start
- Enable service for automatic startup

**Interfaces**:
- Input: Configuration variables (NTP servers, preferred service)
- Output: /etc/chrony/chrony.conf or /etc/systemd/timesyncd.conf
- Dependencies: None
- External: NTP servers (network dependency)

**Key Design Decisions**:
- Support both chrony and systemd-timesyncd
- Prefer chrony for better accuracy and features
- Verification step ensures synchronization is working
- Multiple NTP servers for redundancy

### Swap Management Component

**Responsibilities**:
- Configure optional zram compressed swap in memory
- Configure optional disk-based swap file
- Set swap priorities (zram higher than disk)
- Ensure persistence across reboots

**Interfaces**:
- Input: Configuration variables (zram enabled, zram size, disk swap size)
- Output: /dev/zram0, /swapfile, /etc/fstab, systemd units
- Dependencies: None

**Key Design Decisions**:
- Zram uses lz4 compression for speed
- Zram priority higher than disk swap (faster access)
- Disk swap file at /swapfile with 0600 permissions
- Both zram and disk swap can be enabled simultaneously
- Skip swap configuration if neither is enabled

**Swap Priority Strategy**:
- Zram: priority 100 (accessed first, faster)
- Disk: priority 10 (accessed second, slower but larger)

### System Updates Component

**Responsibilities**:
- Update package lists (apt update)
- Install available package upgrades (apt upgrade)
- Notify operator if reboot is required
- Target Debian stable distribution

**Interfaces**:
- Input: None (uses system package manager)
- Output: Updated packages, /var/run/reboot-required (if applicable)
- Dependencies: None (executes early)
- External: Debian package repositories (network dependency)

**Key Design Decisions**:
- Non-interactive execution (assumes yes to prompts)
- Notification-only for reboots (doesn't auto-reboot)
- Executes early to ensure security updates are applied

## Data Models

### Configuration Variables

The playbook uses Ansible variables for configuration, organized into logical groups:

#### User Configuration
```yaml
# Manual access user (human administrator)
manual_user_name: "admin"              # Username for manual access
manual_user_uid: 1000                  # Fixed UID
manual_user_password: "{{ vault_manual_user_password }}"  # From runtime or vault
manual_user_ssh_key_file: "~/.ssh/id_ed25519_admin.pub"  # Public key path

# Ansible automation user
ansible_user_name: "ansible"           # Username for automation
ansible_user_uid: 1999                 # Fixed UID
ansible_user_ssh_key_file: "~/.ssh/id_ed25519_ansible.pub"  # Public key path
```

#### SSH Configuration
```yaml
ssh_port: 22                           # SSH listening port
ssh_max_auth_tries: 3                  # Maximum authentication attempts
ssh_login_grace_time: "30s"            # Time allowed for authentication
ssh_client_alive_interval: 300         # Seconds between keepalive messages
ssh_client_alive_count_max: 2          # Keepalive messages before disconnect
```

#### Tailscale Configuration
```yaml
tailscale_enabled: false               # Enable Tailscale VPN
tailscale_control_server: "https://headscale.example.com"  # Headscale URL
tailscale_pre_auth_key: "{{ vault_tailscale_pre_auth_key }}"  # From vault
tailscale_interface: "tailscale0"      # Interface name
```

#### Firewall Configuration
```yaml
# Firewall rules are derived from other variables
# No separate firewall-specific variables needed
```

#### Fail2ban Configuration
```yaml
fail2ban_max_retry: 5                  # Failed attempts before ban
fail2ban_ban_time: "10m"               # Ban duration
fail2ban_find_time: "10m"              # Time window for counting failures
```

#### Logging Configuration
```yaml
journald_max_disk_usage: "500M"        # Maximum journal disk usage
journald_max_retention_time: "1month"  # Maximum log retention
```

#### Time Synchronization Configuration
```yaml
time_sync_service: "chrony"            # Service choice: chrony or timesyncd
ntp_servers:                           # NTP server list
  - "0.debian.pool.ntp.org"
  - "1.debian.pool.ntp.org"
  - "2.debian.pool.ntp.org"
  - "3.debian.pool.ntp.org"
```

#### Swap Configuration
```yaml
zram_enabled: false                    # Enable zram compressed swap
zram_size: "50%"                       # Size as percentage of RAM or absolute (e.g., "2G")
disk_swap_size: ""                     # Disk swap size (e.g., "2G", empty to disable)
```

#### Hostname Configuration
```yaml
system_hostname: ""                    # System hostname (empty to skip)
```

### Vault Secrets

Sensitive data is stored in Ansible Vault:

```yaml
# vault.yml (encrypted)
vault_manual_user_password: "hashed_password_here"
vault_tailscale_pre_auth_key: "tskey-auth-xxxxx"
```

### File System Structure

After playbook execution, the target VPS has the following structure:

```
/
├── etc/
│   ├── ssh/
│   │   └── sshd_config                # Hardened SSH configuration
│   ├── nftables.conf                  # Firewall rules
│   ├── fail2ban/
│   │   ├── jail.local                 # Fail2ban configuration
│   │   └── jail.d/                    # Additional jail configurations
│   ├── systemd/
│   │   ├── journald.conf              # Logging configuration
│   │   └── system/                    # Service units (zram, etc.)
│   ├── chrony/
│   │   └── chrony.conf                # Time sync configuration (if chrony)
│   ├── systemd/
│   │   └── timesyncd.conf             # Time sync configuration (if timesyncd)
│   ├── fstab                          # Swap file mount configuration
│   ├── sudoers.d/
│   │   ├── manual_user                # Manual user sudo config
│   │   └── ansible_user               # Ansible user sudo config
│   └── tailscale/                     # Tailscale configuration (if enabled)
├── home/
│   ├── admin/                         # Manual access user home
│   │   └── .ssh/
│   │       └── authorized_keys        # SSH public keys
│   └── ansible/                       # Ansible user home
│       └── .ssh/
│           └── authorized_keys        # SSH public keys
├── root/
│   └── emergency-ssh-access.sh        # Emergency access script (if Tailscale enabled)
├── swapfile                           # Disk swap file (if configured)
└── dev/
    └── zram0                          # Zram device (if enabled)
```

### Test Suite Data Model

The test suite verifies configuration through structured checks:

```yaml
# Test categories
tests:
  users:
    - name: "Manual user exists with correct UID"
      check: "getent passwd {{ manual_user_name }}"
      expected: "uid=1000"
    - name: "Ansible user exists with correct UID"
      check: "getent passwd {{ ansible_user_name }}"
      expected: "uid=1999"
  
  ssh:
    - name: "Password authentication disabled"
      check: "sshd -T | grep passwordauthentication"
      expected: "passwordauthentication no"
    - name: "Root login disabled"
      check: "sshd -T | grep permitrootlogin"
      expected: "permitrootlogin no"
  
  firewall:
    - name: "NFTables service active"
      check: "systemctl is-active nftables"
      expected: "active"
  
  # ... additional test categories
```

Each test has:
- **name**: Human-readable description
- **check**: Command to execute
- **expected**: Expected output or pattern
- **conditional**: Optional condition for test execution (e.g., Tailscale enabled)


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, several opportunities for consolidation emerged:

1. **User creation properties (1.1, 2.1)** can be combined into a single property about user creation with specified UIDs
2. **SSH key deployment properties (1.6-1.8, 2.5-2.7)** share the same verification logic and can be combined
3. **SSH hardening properties (3.3-3.5, 3.6-3.9, 3.14-3.18)** can be grouped into configuration verification properties
4. **Service enablement properties** (multiple requirements) follow the same pattern and can be consolidated
5. **Conditional execution properties** (Tailscale enabled/disabled) can be combined into single properties with conditional logic
6. **Swap configuration properties (13.4-13.9, 13.11-13.15)** can be consolidated into device-type-agnostic properties

The following properties represent the unique, non-redundant correctness guarantees:

### Property 1: User Account Creation with Fixed UIDs

*For any* execution of the bootstrap playbook with configured user names, the manual access user SHALL be created with uid 1000 and the Ansible user SHALL be created with uid 1999.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**

### Property 2: SSH Key Deployment and Permissions

*For any* user account (manual or Ansible) with a configured SSH public key file path, the playbook SHALL deploy the public key to the user's authorized_keys file with mode 0600 and correct ownership.

**Validates: Requirements 1.6, 1.7, 1.8, 2.5, 2.6, 2.7**

### Property 3: Sudo Privilege Configuration

*For any* execution of the bootstrap playbook, the manual access user SHALL have password-required sudo privileges and the Ansible user SHALL have passwordless sudo privileges.

**Validates: Requirements 1.4, 2.3**

### Property 4: User Authentication Method Configuration

*For any* execution of the bootstrap playbook, the manual access user SHALL support both password and SSH key authentication, while the Ansible user SHALL support only SSH key authentication.

**Validates: Requirements 1.3, 1.5, 2.4, 2.8**

### Property 5: SSH Daemon Hardening Configuration

*For any* execution of the bootstrap playbook, the SSHD configuration SHALL disable password authentication globally, disable root login, restrict key exchange algorithms to modern elliptic curves, restrict ciphers to authenticated encryption, restrict MACs to Encrypt-Then-MAC variants, and disable X11 forwarding, TCP forwarding, agent forwarding, tunneling, and empty passwords.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.14, 3.18**

### Property 6: SSH Access Restriction

*For any* execution of the bootstrap playbook with configured user names, the SSHD AllowUsers directive SHALL contain only the manual access user and Ansible user.

**Validates: Requirements 3.10**

### Property 7: SSH Port Configuration

*For any* execution of the bootstrap playbook with an optional SSH port variable, the SSHD SHALL listen on the specified port (or default port 22 if not specified).

**Validates: Requirements 3.11, 3.12**

### Property 8: SSH Session Security Configuration

*For any* execution of the bootstrap playbook, the SSHD configuration SHALL set MaxAuthTries to a low value, LoginGraceTime to a short duration, and configure ClientAliveInterval and ClientAliveCountMax for idle session management.

**Validates: Requirements 3.15, 3.16, 3.17**

### Property 9: Service Restart on Configuration Change

*For any* service (SSHD, NFTables, journald, fail2ban, time sync) whose configuration is modified by the playbook, the service SHALL be restarted or reloaded after the configuration change.

**Validates: Requirements 3.13, 8.10, 11.4**

### Property 10: Tailscale Installation and Configuration

*For any* execution of the bootstrap playbook WHERE Tailscale is enabled, the playbook SHALL install Tailscale packages, authenticate with the control server using a pre-auth key from Vault, configure the control server URL, enable the service, and start the service.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

### Property 11: Tailscale Conditional Execution

*For any* execution of the bootstrap playbook WHERE Tailscale is disabled, the playbook SHALL skip all Tailscale installation, configuration, and SSH restriction steps.

**Validates: Requirements 4.6, 9.8**

### Property 12: SSH Interface Restriction with Safety Check

*For any* execution of the bootstrap playbook WHERE Tailscale is enabled, the playbook SHALL verify Tailscale connectivity before configuring SSHD to listen only on the Tailscale interface.

**Validates: Requirements 5.1, 5.2**

### Property 13: SSH Interface Configuration Based on VPN Status

*For any* execution of the bootstrap playbook WHERE Tailscale is disabled, the SSHD SHALL be configured to listen on all interfaces.

**Validates: Requirements 5.3**

### Property 14: Hostname Configuration Persistence

*For any* execution of the bootstrap playbook WHERE a hostname is configured, the system hostname SHALL be set to the specified value and persisted across reboots.

**Validates: Requirements 6.1, 6.2**

### Property 15: Hostname Configuration Skip

*For any* execution of the bootstrap playbook WHERE no hostname is configured, the playbook SHALL skip hostname configuration and leave the existing hostname unchanged.

**Validates: Requirements 6.3**

### Property 16: System Package Updates

*For any* execution of the bootstrap playbook on a Debian stable system, the playbook SHALL execute apt update and apt upgrade, and notify the operator if a reboot is required.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 17: NFTables Dual-Stack Configuration

*For any* execution of the bootstrap playbook, NFTables rules SHALL be configured for both IPv4 and IPv6 traffic with identical policies.

**Validates: Requirements 8.1, 8.2**

### Property 18: NFTables Stateful Firewall Rules

*For any* execution of the bootstrap playbook, NFTables SHALL allow established and related connections, allow loopback interface traffic, and set default input and forward policies to drop.

**Validates: Requirements 8.3, 8.4, 8.5, 8.6**

### Property 19: NFTables SSH Access Control

*For any* execution of the bootstrap playbook, NFTables SHALL restrict SSH port access to the Tailscale interface only when Tailscale is enabled, or allow SSH port access from all interfaces when Tailscale is disabled.

**Validates: Requirements 8.7, 8.8**

### Property 20: NFTables Tailscale Traffic Allowance

*For any* execution of the bootstrap playbook WHERE Tailscale is enabled, NFTables SHALL allow Tailscale's WireGuard UDP traffic through the firewall.

**Validates: Requirements 8.9**

### Property 21: NFTables Service Persistence

*For any* execution of the bootstrap playbook, the NFTables service SHALL be enabled to start on boot, ensuring rules persist across system reboots.

**Validates: Requirements 8.10, 8.11**

### Property 22: Emergency Script Deployment

*For any* execution of the bootstrap playbook WHERE Tailscale is enabled, an emergency access script SHALL be deployed to /root/ that can toggle SSH restrictions.

**Validates: Requirements 9.1**

### Property 23: Emergency Script Unrestrict Operation

*For any* invocation of the emergency script without arguments, the script SHALL reconfigure SSHD to listen on all interfaces and update NFTables to allow SSH from all interfaces, then restart SSHD and reload NFTables.

**Validates: Requirements 9.2, 9.5, 9.6**

### Property 24: Emergency Script Restore Operation

*For any* invocation of the emergency script with a restore argument, the script SHALL reconfigure SSHD to listen only on the Tailscale interface and update NFTables to restrict SSH to the Tailscale interface, then restart SSHD and reload NFTables.

**Validates: Requirements 9.3, 9.5, 9.6**

### Property 25: Emergency Script Round-Trip Restoration

*For any* system state with Tailscale-restricted SSH, running the emergency script without arguments and then with the restore argument SHALL return the system to the original restricted state.

**Validates: Requirements 9.4**

### Property 26: Emergency Script Idempotency

*For any* invocation mode (unrestrict or restore), running the emergency script multiple times in the same mode SHALL produce consistent results without errors.

**Validates: Requirements 9.7**

### Property 27: Fail2ban Installation and Configuration

*For any* execution of the bootstrap playbook, fail2ban SHALL be installed, configured to monitor SSHD logs, configured with a configurable ban threshold and duration, integrated with NFTables, enabled to start on boot, and started.

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**

### Property 28: Journald Persistent Logging Configuration

*For any* execution of the bootstrap playbook, journald SHALL be configured to persist logs to disk with configurable maximum disk usage and retention time.

**Validates: Requirements 11.1, 11.2, 11.3**

### Property 29: Time Synchronization Service Configuration

*For any* execution of the bootstrap playbook, a time synchronization service SHALL be installed, configured with reliable NTP servers, enabled to start on boot, started, and verified to be actively synchronizing.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

### Property 30: Zram Swap Configuration

*For any* execution of the bootstrap playbook WHERE zram is enabled with a specified size, a zram device SHALL be created with the specified size, configured to use lz4 compression, formatted as swap, enabled as swap, configured to initialize on boot, and assigned a higher priority than disk swap.

**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9**

### Property 31: Disk Swap Configuration

*For any* execution of the bootstrap playbook WHERE disk swap size is configured, a swap file SHALL be created at /swapfile with the specified size and mode 0600, formatted as swap, enabled as swap, added to /etc/fstab for persistence, and assigned a lower priority than zram swap if zram is also enabled.

**Validates: Requirements 13.10, 13.11, 13.12, 13.13, 13.14, 13.15, 13.16**

### Property 32: Swap Configuration Skip

*For any* execution of the bootstrap playbook WHERE neither zram nor disk swap is configured, the playbook SHALL skip all swap configuration steps.

**Validates: Requirements 13.17**

### Property 33: Playbook Idempotency

*For any* execution of the bootstrap playbook against an already-configured server, the playbook SHALL complete without errors, report no changes for already-configured items, and apply only configuration changes that differ from the current state.

**Validates: Requirements 15.3, 15.4, 15.5**

### Property 34: Configuration Verification Round-Trip

*For any* configuration aspect modified by the bootstrap playbook, the test suite SHALL verify the configuration matches the expected state, demonstrating that playbook execution followed by test execution confirms correctness.

**Validates: Requirements 14.1-14.44 (all test suite verification requirements)**

## Error Handling

### Playbook Execution Errors

The playbook implements defensive error handling at multiple levels:

1. **Pre-flight Checks**:
   - Verify target system is Debian stable before proceeding
   - Verify required variables are defined (user names, SSH key files)
   - Verify SSH key files exist and are readable on the controller
   - Verify Vault secrets are accessible when Tailscale is enabled

2. **Tailscale Connectivity Verification**:
   - Before restricting SSH to Tailscale interface, verify Tailscale is connected
   - Test connectivity through Tailscale interface
   - Fail with clear error message if connectivity test fails
   - This prevents lockout scenarios

3. **Service Restart Failures**:
   - Use handlers with failure detection
   - If SSHD restart fails, attempt to restore previous configuration
   - Log detailed error messages for troubleshooting
   - Exit with non-zero status to indicate failure

4. **Package Installation Failures**:
   - Retry package operations with exponential backoff
   - Verify package repositories are accessible
   - Provide clear error messages indicating which package failed

5. **File Permission Errors**:
   - Verify file operations succeed before proceeding
   - Use Ansible's built-in error handling for file operations
   - Validate file permissions after setting them

6. **Vault Decryption Errors**:
   - Fail early if Vault password is incorrect
   - Provide clear error message indicating Vault access failure
   - Do not proceed with partial configuration

### Emergency Script Error Handling

The emergency script implements robust error handling:

1. **Configuration File Validation**:
   - Verify /etc/ssh/sshd_config exists before modification
   - Verify /etc/nftables.conf exists before modification
   - Exit with error if configuration files are missing

2. **Service Control Errors**:
   - Check if systemctl commands succeed
   - Provide clear error messages if service restart/reload fails
   - Exit with non-zero status on failure

3. **Idempotency Protection**:
   - Check current state before making changes
   - Skip changes if already in desired state
   - Prevent configuration corruption from repeated execution

### Test Suite Error Handling

The test suite provides clear pass/fail reporting:

1. **Test Execution**:
   - Each test runs independently
   - Test failures do not prevent subsequent tests from running
   - Collect all test results before reporting

2. **Test Result Reporting**:
   - Clear pass/fail status for each test
   - Detailed error messages for failures
   - Summary statistics (total tests, passed, failed)
   - Exit with non-zero status if any test fails

3. **Conditional Test Handling**:
   - Skip tests that don't apply to current configuration
   - Mark skipped tests clearly in output
   - Don't count skipped tests as failures

## Testing Strategy

### Dual Testing Approach

The VPS Bootstrap Playbook requires both unit testing and property-based testing for comprehensive verification:

**Unit Tests** focus on:
- Specific configuration examples (e.g., creating a user named "admin" with uid 1000)
- Edge cases (e.g., empty hostname variable, missing SSH key file)
- Error conditions (e.g., invalid Vault password, unreachable package repository)
- Integration points (e.g., fail2ban integration with NFTables)
- Specific test cases from Requirement 14 (44 verification tests)

**Property-Based Tests** focus on:
- Universal properties across all valid configurations
- Idempotency verification with randomized configurations
- Round-trip properties (e.g., emergency script unrestrict then restore)
- Configuration consistency across multiple executions
- Randomized input validation (e.g., various username formats, SSH port numbers)

Together, unit tests catch concrete bugs in specific scenarios, while property-based tests verify general correctness across the configuration space.

### Property-Based Testing Configuration

**Testing Framework**: Use `pytest` with `hypothesis` for property-based testing in Python

**Test Organization**:
```
tests/
├── unit/
│   ├── test_user_creation.py
│   ├── test_ssh_hardening.py
│   ├── test_firewall.py
│   ├── test_emergency_script.py
│   └── ...
├── property/
│   ├── test_idempotency_properties.py
│   ├── test_configuration_properties.py
│   ├── test_service_properties.py
│   └── ...
└── integration/
    ├── test_full_bootstrap.py
    └── test_verification_suite.py
```

**Property Test Configuration**:
- Minimum 100 iterations per property test (configurable via pytest)
- Each property test references its design document property in a comment
- Tag format: `# Feature: vps-bootstrap-playbook, Property {number}: {property_text}`

**Example Property Test Structure**:
```python
from hypothesis import given, settings
import hypothesis.strategies as st

@settings(max_examples=100)
@given(
    manual_user=st.text(min_size=1, max_size=32, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'))),
    ansible_user=st.text(min_size=1, max_size=32, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd')))
)
def test_user_creation_with_fixed_uids(manual_user, ansible_user):
    """
    Feature: vps-bootstrap-playbook, Property 1: User Account Creation with Fixed UIDs
    
    For any execution of the bootstrap playbook with configured user names,
    the manual access user SHALL be created with uid 1000 and the Ansible user
    SHALL be created with uid 1999.
    """
    # Test implementation
    pass
```

### Unit Testing Strategy

**Unit Test Categories**:

1. **User Management Tests**:
   - Verify manual user creation with specific username
   - Verify Ansible user creation with specific username
   - Verify sudo configuration files are created correctly
   - Verify SSH key deployment with specific key content
   - Verify authorized_keys file permissions

2. **SSH Hardening Tests**:
   - Verify specific SSHD configuration directives
   - Verify cryptographic algorithm restrictions
   - Verify feature disablement (X11, forwarding, etc.)
   - Verify AllowUsers directive content
   - Verify SSHD service restart on configuration change

3. **Tailscale Tests**:
   - Verify Tailscale installation when enabled
   - Verify Tailscale skip when disabled
   - Verify control server configuration
   - Verify connectivity check before SSH restriction

4. **Firewall Tests**:
   - Verify NFTables rule structure
   - Verify IPv4 and IPv6 rule parity
   - Verify SSH access rules based on Tailscale status
   - Verify default policies
   - Verify stateful connection rules

5. **Emergency Script Tests**:
   - Verify script deployment when Tailscale enabled
   - Verify script absence when Tailscale disabled
   - Verify unrestrict operation modifies correct files
   - Verify restore operation modifies correct files
   - Verify service restarts after script execution

6. **Service Configuration Tests**:
   - Verify fail2ban configuration and service state
   - Verify journald configuration
   - Verify time sync service configuration
   - Verify service enablement for boot

7. **Swap Configuration Tests**:
   - Verify zram device creation when enabled
   - Verify disk swap file creation when configured
   - Verify swap priorities
   - Verify persistence configuration

8. **Idempotency Tests**:
   - Run playbook twice, verify second run reports no changes
   - Modify one configuration item, verify only that item changes on re-run
   - Verify playbook succeeds on fresh system
   - Verify playbook succeeds on already-configured system

9. **Integration Tests**:
   - Full bootstrap execution on test VM
   - Run verification test suite (Requirement 14)
   - Verify all 44 test cases pass
   - Test emergency script functionality end-to-end

### Test Execution Environment

**Test Infrastructure**:
- Use Docker containers or VMs for isolated test environments
- Provide fresh Debian stable images for each test run
- Support both password and SSH key authentication for initial connection
- Clean up test environments after execution

**Continuous Integration**:
- Run unit tests on every commit
- Run property-based tests on every pull request
- Run full integration tests on release candidates
- Maintain test coverage metrics (target: >90% for playbook tasks)

**Manual Testing**:
- Document manual test procedures for emergency script
- Provide test checklist for release validation
- Include instructions for testing on real VPS providers

### Test Data Management

**SSH Key Generation for Tests**:
```bash
# Generate test key pairs
ssh-keygen -t ed25519 -f tests/fixtures/test_manual_key -N ""
ssh-keygen -t ed25519 -f tests/fixtures/test_ansible_key -N ""
```

**Vault Secrets for Tests**:
```yaml
# tests/fixtures/test_vault.yml (encrypted)
vault_manual_user_password: "$6$test$hashed_password"
vault_tailscale_pre_auth_key: "tskey-auth-test-key"
```

**Test Configuration Variables**:
```yaml
# tests/fixtures/test_vars.yml
manual_user_name: "testadmin"
ansible_user_name: "testansible"
ssh_port: 2222
tailscale_enabled: true
tailscale_control_server: "http://localhost:8080"
# ... additional test variables
```

### Verification Test Suite (Requirement 14)

The verification test suite is implemented as an Ansible playbook that runs after bootstrap:

**Test Playbook Structure**:
```yaml
# tests/verify_bootstrap.yml
- name: Verify VPS Bootstrap Configuration
  hosts: all
  tasks:
    - name: Verify manual user exists with uid 1000
      # Test implementation
    
    - name: Verify Ansible user exists with uid 1999
      # Test implementation
    
    # ... 42 additional verification tasks
```

**Test Execution**:
```bash
# Run verification suite
make verify

# Or directly with uv
uv run ansible-playbook -i inventory tests/verify_bootstrap.yml
```

**Test Output**:
- Clear pass/fail status for each of 44 tests
- Summary report with total passed/failed
- Detailed error messages for failures
- Exit code 0 if all tests pass, non-zero otherwise
