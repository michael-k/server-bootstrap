# Requirements Document

## Introduction

The VPS Bootstrap Playbook is an Ansible playbook that prepares a fresh VPS for regular Ansible management. The playbook executes once manually against a brand-new server using root credentials, establishing secure access patterns, hardening SSH configuration, and optionally configuring Tailscale VPN with firewall restrictions.

## Glossary

- **Bootstrap_Playbook**: The Ansible playbook that performs initial VPS configuration
- **Manual_Access_User**: A dedicated user account (uid 1000) for human administrator access with sudo privileges
- **Ansible_User**: A dedicated user account (uid 1999) for automated Ansible management with sudo privileges
- **SSHD**: The SSH daemon service that handles remote access
- **Tailscale**: Optional VPN service for secure network access
- **Tailscale_Interface**: The network interface created by Tailscale (typically tailscale0)
- **Headscale**: A self-hosted Tailscale control server used as the Control_Server
- **Emergency_Script**: A script deployed to /root/ that can toggle SSH access restrictions
- **NFTables**: The firewall system used for packet filtering
- **Control_Server**: The Tailscale coordination server (Headscale instance)
- **Vault**: Ansible Vault for encrypted secret storage
- **Pre_Auth_Key**: A pre-authentication key stored in Vault, used to register the node with the Control_Server
- **Test_Suite**: Automated tests that verify the bootstrap configuration
- **Fail2ban**: Intrusion prevention software that monitors log files and bans IPs with repeated failed login attempts
- **Journald**: The systemd journal service for system logging
- **Time_Sync_Service**: Network time synchronization service (chrony or systemd-timesyncd)
- **Swap_File**: A file-based swap space for virtual memory
- **Zram**: A compressed RAM block device that provides compressed swap in memory
- **Zram_Device**: The block device created by zram (typically /dev/zram0)

## Requirements

### Requirement 1: Manual Access User Creation

**User Story:** As a system administrator, I want a dedicated manual access user account, so that I can access the server for maintenance without using root.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL create the Manual_Access_User with uid 1000
2. THE Bootstrap_Playbook SHALL accept the Manual_Access_User username as a configurable variable
3. THE Bootstrap_Playbook SHALL accept the Manual_Access_User password as a runtime variable provided during workflow execution
4. THE Bootstrap_Playbook SHALL grant sudo privileges to the Manual_Access_User
5. THE Bootstrap_Playbook SHALL configure password authentication for the Manual_Access_User
6. THE Bootstrap_Playbook SHALL deploy SSH public keys to the Manual_Access_User authorized_keys file
7. THE Bootstrap_Playbook SHALL accept the Manual_Access_User public key file path as a configurable variable
8. THE Bootstrap_Playbook SHALL set appropriate permissions on the Manual_Access_User authorized_keys file

### Requirement 2: Ansible User Creation

**User Story:** As a system administrator, I want a dedicated Ansible user account, so that automated management tasks run with appropriate privileges.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL create the Ansible_User with uid 1999
2. THE Bootstrap_Playbook SHALL accept the Ansible_User username as a configurable variable
3. THE Bootstrap_Playbook SHALL grant passwordless sudo privileges to the Ansible_User
4. THE Bootstrap_Playbook SHALL configure SSH key-only authentication for the Ansible_User
5. THE Bootstrap_Playbook SHALL deploy SSH public keys to the Ansible_User authorized_keys file
6. THE Bootstrap_Playbook SHALL accept the Ansible_User public key file path as a configurable variable
7. THE Bootstrap_Playbook SHALL set appropriate permissions on the Ansible_User authorized_keys file
8. THE Bootstrap_Playbook SHALL disable password authentication for the Ansible_User

### Requirement 3: SSH Hardening

**User Story:** As a security administrator, I want SSH access hardened, so that the server is protected from unauthorized access.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL disable password authentication in SSHD configuration
2. THE Bootstrap_Playbook SHALL disable root login in SSHD configuration
3. THE Bootstrap_Playbook SHALL restrict SSHD key exchange algorithms to modern elliptic curves only
4. THE Bootstrap_Playbook SHALL restrict SSHD ciphers to authenticated encryption algorithms only
5. THE Bootstrap_Playbook SHALL restrict SSHD MACs to Encrypt-Then-MAC variants only
6. THE Bootstrap_Playbook SHALL disable X11 forwarding in SSHD configuration
7. THE Bootstrap_Playbook SHALL disable TCP forwarding in SSHD configuration
8. THE Bootstrap_Playbook SHALL disable agent forwarding in SSHD configuration
9. THE Bootstrap_Playbook SHALL disable tunneling in SSHD configuration
10. THE Bootstrap_Playbook SHALL restrict SSHD access to the Manual_Access_User and Ansible_User only
11. THE Bootstrap_Playbook SHALL accept the SSH port as an optional configurable variable with a default of 22
12. THE Bootstrap_Playbook SHALL configure SSHD to listen on the specified port
13. WHEN SSHD configuration is modified, THE Bootstrap_Playbook SHALL restart the SSHD service
14. THE Bootstrap_Playbook SHALL restrict SSHD authentication to public key only
15. THE Bootstrap_Playbook SHALL configure MaxAuthTries to a low value
16. THE Bootstrap_Playbook SHALL configure LoginGraceTime to a short duration
17. THE Bootstrap_Playbook SHALL configure ClientAliveInterval and ClientAliveCountMax for idle session management
18. THE Bootstrap_Playbook SHALL disable empty passwords in SSHD configuration

### Requirement 4: Tailscale Installation

**User Story:** As a system administrator, I want optional Tailscale VPN installation, so that I can access the server through a secure private network.

#### Acceptance Criteria

1. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL install Tailscale packages from the official repository
2. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL authenticate Tailscale with the Control_Server using a Pre_Auth_Key from Vault
3. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL configure Tailscale to use the Headscale Control_Server URL
4. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL enable the Tailscale service to start on boot
5. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL start the Tailscale service
6. WHERE Tailscale is disabled, THE Bootstrap_Playbook SHALL skip Tailscale installation steps

### Requirement 5: SSH Interface Restriction

**User Story:** As a security administrator, I want SSH restricted to the Tailscale interface when VPN is enabled, so that SSH is not exposed to the public internet.

#### Acceptance Criteria

1. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL verify Tailscale connectivity before restricting SSH
2. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL configure SSHD to listen only on the Tailscale_Interface
3. WHERE Tailscale is disabled, THE Bootstrap_Playbook SHALL configure SSHD to listen on all interfaces

### Requirement 6: Hostname Configuration

**User Story:** As a system administrator, I want to set the server hostname, so that the server is identifiable on the network.

#### Acceptance Criteria

1. WHERE a hostname is configured, THE Bootstrap_Playbook SHALL set the system hostname to the specified value
2. WHERE a hostname is configured, THE Bootstrap_Playbook SHALL persist the hostname across system reboots
3. WHERE no hostname is configured, THE Bootstrap_Playbook SHALL skip hostname configuration

### Requirement 7: System Updates

**User Story:** As a system administrator, I want the system packages updated, so that the server runs current software versions.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL execute apt update to refresh package lists
2. THE Bootstrap_Playbook SHALL execute apt upgrade to install available updates
3. THE Bootstrap_Playbook SHALL target Debian stable distribution
4. WHEN package upgrades require a system reboot, THE Bootstrap_Playbook SHALL notify the operator

### Requirement 8: Firewall Configuration

**User Story:** As a security administrator, I want NFTables firewall configured, so that network access is controlled.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL configure NFTables rules for IPv4 traffic
2. THE Bootstrap_Playbook SHALL configure NFTables rules for IPv6 traffic
3. THE Bootstrap_Playbook SHALL allow established and related connections through the firewall
4. THE Bootstrap_Playbook SHALL allow loopback interface traffic through the firewall
5. THE Bootstrap_Playbook SHALL set the default input policy to drop
6. THE Bootstrap_Playbook SHALL set the default forward policy to drop
7. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL restrict SSH port access to the Tailscale_Interface only
8. WHERE Tailscale is disabled, THE Bootstrap_Playbook SHALL allow SSH port access from all interfaces
9. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL allow Tailscale's own traffic (WireGuard UDP) through the firewall
10. THE Bootstrap_Playbook SHALL enable the NFTables service
11. THE Bootstrap_Playbook SHALL persist NFTables rules across system reboots

### Requirement 9: Emergency Access Script

**User Story:** As a system administrator, I want an emergency script to toggle SSH restrictions, so that I can recover access if Tailscale fails.

#### Acceptance Criteria

1. WHERE Tailscale is enabled, THE Bootstrap_Playbook SHALL deploy the Emergency_Script to /root/
2. WHEN the Emergency_Script is invoked without arguments, IT SHALL reconfigure SSHD and NFTables to allow SSH access via the public interface
3. WHEN the Emergency_Script is invoked with a restore argument, IT SHALL reconfigure SSHD and NFTables to restrict SSH access to the Tailscale_Interface only
4. WHEN the Emergency_Script is run without arguments and then again with the restore argument, the original restricted state SHALL be restored
5. THE Emergency_Script SHALL restart SSHD after modifying configuration
6. THE Emergency_Script SHALL reload NFTables rules after modifying firewall configuration
7. THE Emergency_Script SHALL be idempotent (safe to re-run in either mode)
8. WHERE Tailscale is disabled, THE Bootstrap_Playbook SHALL skip Emergency_Script deployment

### Requirement 10: Intrusion Prevention

**User Story:** As a security administrator, I want fail2ban configured to block repeated failed login attempts, so that the server is protected from brute-force attacks.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL install fail2ban from the Debian repository
2. THE Bootstrap_Playbook SHALL configure fail2ban to monitor SSHD logs
3. THE Bootstrap_Playbook SHALL configure fail2ban to ban IPs after a configurable number of failed SSH authentication attempts
4. THE Bootstrap_Playbook SHALL configure fail2ban ban duration as a configurable variable
5. THE Bootstrap_Playbook SHALL configure fail2ban to work with NFTables
6. THE Bootstrap_Playbook SHALL enable the fail2ban service to start on boot
7. THE Bootstrap_Playbook SHALL start the fail2ban service

### Requirement 11: System Logging Configuration

**User Story:** As a system administrator, I want journald configured with appropriate retention settings, so that system logs are available for troubleshooting.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL configure journald to persist logs to disk
2. THE Bootstrap_Playbook SHALL configure journald maximum disk usage as a configurable variable with a reasonable default
3. THE Bootstrap_Playbook SHALL configure journald log retention time as a configurable variable with a reasonable default
4. THE Bootstrap_Playbook SHALL restart the journald service after configuration changes

### Requirement 12: Time Synchronization

**User Story:** As a system administrator, I want time synchronization configured, so that system time is accurate for logs, certificates, and distributed systems.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL install and configure a Time_Sync_Service
2. THE Bootstrap_Playbook SHALL configure the Time_Sync_Service with reliable NTP servers
3. THE Bootstrap_Playbook SHALL enable the Time_Sync_Service to start on boot
4. THE Bootstrap_Playbook SHALL start the Time_Sync_Service
5. THE Bootstrap_Playbook SHALL verify time synchronization is active after service start

### Requirement 13: Swap Configuration

**User Story:** As a system administrator, I want swap space configured with optional compression, so that the system can handle memory pressure efficiently without crashing.

#### Acceptance Criteria

1. THE Bootstrap_Playbook SHALL accept zram enablement as an optional configurable variable
2. THE Bootstrap_Playbook SHALL accept zram size as an optional configurable variable (as percentage of RAM or absolute size)
3. WHERE zram is enabled, THE Bootstrap_Playbook SHALL install zram-tools or configure zram via systemd
4. WHERE zram is enabled, THE Bootstrap_Playbook SHALL create a Zram_Device with the specified size
5. WHERE zram is enabled, THE Bootstrap_Playbook SHALL configure the Zram_Device to use lz4 compression algorithm
6. WHERE zram is enabled, THE Bootstrap_Playbook SHALL format the Zram_Device as swap space
7. WHERE zram is enabled, THE Bootstrap_Playbook SHALL enable the Zram_Device as swap
8. WHERE zram is enabled, THE Bootstrap_Playbook SHALL configure the Zram_Device to initialize on boot
9. WHERE zram is enabled, THE Bootstrap_Playbook SHALL set swap priority for the Zram_Device higher than disk swap
10. THE Bootstrap_Playbook SHALL accept disk swap size as an optional configurable variable
11. WHERE disk swap size is configured, THE Bootstrap_Playbook SHALL create a Swap_File at /swapfile with the specified size
12. WHERE disk swap size is configured, THE Bootstrap_Playbook SHALL set appropriate permissions on the Swap_File (0600)
13. WHERE disk swap size is configured, THE Bootstrap_Playbook SHALL format the Swap_File as swap space
14. WHERE disk swap size is configured, THE Bootstrap_Playbook SHALL enable the Swap_File
15. WHERE disk swap size is configured, THE Bootstrap_Playbook SHALL add the Swap_File to /etc/fstab for persistence across reboots
16. WHERE disk swap size is configured AND zram is enabled, THE Bootstrap_Playbook SHALL set swap priority for the Swap_File lower than the Zram_Device
17. WHERE neither zram nor disk swap is configured, THE Bootstrap_Playbook SHALL skip swap configuration

### Requirement 14: Configuration Testing

**User Story:** As a system administrator, I want automated tests to verify the bootstrap configuration, so that I can confirm the server is properly configured.

#### Acceptance Criteria

1. THE Test_Suite SHALL verify the Manual_Access_User exists with uid 1000
2. THE Test_Suite SHALL verify the Ansible_User exists with uid 1999
3. THE Test_Suite SHALL verify the Manual_Access_User has sudo privileges
4. THE Test_Suite SHALL verify the Ansible_User has passwordless sudo privileges
5. THE Test_Suite SHALL verify SSHD password authentication is disabled
6. THE Test_Suite SHALL verify SSHD root login is disabled
7. THE Test_Suite SHALL verify SSHD is listening on the configured port only
8. THE Test_Suite SHALL verify SSHD AllowUsers is restricted to Manual_Access_User and Ansible_User
9. THE Test_Suite SHALL verify SSHD key exchange algorithms match the hardened configuration
10. THE Test_Suite SHALL verify SSHD ciphers match the hardened configuration
11. THE Test_Suite SHALL verify SSHD MACs match the hardened configuration
12. THE Test_Suite SHALL verify X11 forwarding is disabled in SSHD
13. THE Test_Suite SHALL verify TCP forwarding is disabled in SSHD
14. THE Test_Suite SHALL verify agent forwarding is disabled in SSHD
15. THE Test_Suite SHALL verify tunneling is disabled in SSHD
16. THE Test_Suite SHALL verify SSHD service is running
17. THE Test_Suite SHALL verify SSHD service is enabled to start on boot
18. WHERE Tailscale is enabled, THE Test_Suite SHALL verify Tailscale service is running
19. WHERE Tailscale is enabled, THE Test_Suite SHALL verify Tailscale service is enabled to start on boot
20. WHERE Tailscale is enabled, THE Test_Suite SHALL verify SSH is restricted to Tailscale_Interface
21. WHERE Tailscale is enabled, THE Test_Suite SHALL verify the Emergency_Script exists at /root/
22. THE Test_Suite SHALL verify NFTables service is active
23. THE Test_Suite SHALL verify NFTables service is enabled to start on boot
24. THE Test_Suite SHALL verify NFTables default input policy is drop
25. THE Test_Suite SHALL verify NFTables default forward policy is drop
26. THE Test_Suite SHALL verify NFTables allows established and related connections
27. THE Test_Suite SHALL verify NFTables allows loopback traffic
28. THE Test_Suite SHALL verify only the configured SSH port is accessible through the firewall
29. THE Test_Suite SHALL verify the system hostname matches the configured value when hostname is set
30. THE Test_Suite SHALL verify fail2ban service is active
31. THE Test_Suite SHALL verify fail2ban service is enabled to start on boot
32. THE Test_Suite SHALL verify fail2ban is monitoring SSHD
33. THE Test_Suite SHALL verify journald is configured to persist logs to disk
34. THE Test_Suite SHALL verify the Time_Sync_Service is active
35. THE Test_Suite SHALL verify the Time_Sync_Service is enabled to start on boot
36. THE Test_Suite SHALL verify time synchronization status is active
37. WHERE zram is enabled, THE Test_Suite SHALL verify the Zram_Device exists
38. WHERE zram is enabled, THE Test_Suite SHALL verify the Zram_Device is active as swap space
39. WHERE zram is enabled, THE Test_Suite SHALL verify the Zram_Device compression algorithm is lz4
40. WHERE zram is enabled, THE Test_Suite SHALL verify the Zram_Device has higher swap priority than disk swap
41. WHERE disk swap is configured, THE Test_Suite SHALL verify the Swap_File exists at /swapfile
42. WHERE disk swap is configured, THE Test_Suite SHALL verify the Swap_File is active as swap space
43. WHERE disk swap is configured, THE Test_Suite SHALL verify the Swap_File is in /etc/fstab
44. THE Test_Suite SHALL report all verification results clearly with pass/fail status

### Requirement 15: Idempotency

**User Story:** As a system administrator, I want the playbook to be idempotent, so that running it multiple times produces consistent results without errors.

#### Acceptance Criteria

1. WHEN the Bootstrap_Playbook executes against a fresh VPS with root password access, THE Bootstrap_Playbook SHALL complete successfully
2. WHEN the Bootstrap_Playbook executes against a fresh VPS with root SSH key access, THE Bootstrap_Playbook SHALL complete successfully
3. WHEN the Bootstrap_Playbook executes against an already-configured server, THE Bootstrap_Playbook SHALL complete without errors
4. WHEN the Bootstrap_Playbook executes against an already-configured server, THE Bootstrap_Playbook SHALL report no changes for already-configured items
5. WHEN the Bootstrap_Playbook executes against an already-configured server, THE Bootstrap_Playbook SHALL apply only configuration changes that differ from the current state

### Requirement 16: Documentation

**User Story:** As a developer, I want the project structured with modern Python tooling, so that dependencies and execution are managed consistently.

#### Acceptance Criteria

1. THE Bootstrap_Playbook project SHALL include a pyproject.toml file for dependency management
2. THE Bootstrap_Playbook project SHALL include a Makefile for common operations
3. THE Makefile SHALL execute ansible-playbook using uv run
4. THE Makefile SHALL execute ansible-vault using uv run
5. THE Bootstrap_Playbook project SHALL include a README with variable documentation
6. THE README SHALL document prerequisites for running the Bootstrap_Playbook
7. THE README SHALL document that the Bootstrap_Playbook is designed for initial setup only
8. THE README SHALL document how to generate SSH key pairs
9. THE README SHALL document required variables for playbook execution
10. THE README SHALL document secrets management using ansible-vault
11. THE README SHALL document instructions for running the playbook
12. THE README SHALL document instructions for running the Test_Suite

