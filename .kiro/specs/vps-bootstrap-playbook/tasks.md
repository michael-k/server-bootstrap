# Implementation Plan: VPS Bootstrap Playbook

## Overview

This implementation plan breaks down the VPS Bootstrap Playbook into discrete, manageable tasks. The playbook will be implemented using Ansible YAML for infrastructure automation, Bash for the emergency access script, and Python (pytest + hypothesis) for comprehensive testing.

The implementation follows a logical progression: project structure → core roles → integration → testing. Each task builds on previous work, with checkpoints to ensure incremental validation.

## Tasks

- [x] 1. Set up project structure and configuration
  - Create pyproject.toml with ansible-core, pytest, hypothesis dependencies
  - Create Makefile with targets for playbook execution and testing
  - Create README.md with prerequisites, variable documentation, and usage instructions
  - Create directory structure: roles/, tests/, inventory examples
  - Create ansible.cfg with sensible defaults
  - _Requirements: 16.1, 16.2, 16.3, 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12_

- [x] 2. Implement users role
  - [x] 2.1 Create users role structure (tasks, defaults, handlers)
    - Define default variables for user names, UIDs, SSH key paths
    - _Requirements: 1.1, 1.2, 1.7, 2.1, 2.2, 2.6_
  
  - [x] 2.2 Implement manual access user creation
    - Create user with uid 1000, password authentication, sudo with password
    - Deploy SSH public keys to authorized_keys with mode 0600
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8_
  
  - [x] 2.3 Implement Ansible user creation
    - Create user with uid 1999, no password, passwordless sudo
    - Deploy SSH public keys to authorized_keys with mode 0600
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8_
  
  - [x] 2.4 Write property test for user creation
    - **Property 1: User Account Creation with Fixed UIDs**
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
  
  - [x] 2.5 Write property test for SSH key deployment
    - **Property 2: SSH Key Deployment and Permissions**
    - **Validates: Requirements 1.6, 1.7, 1.8, 2.5, 2.6, 2.7**
  
  - [x] 2.6 Write property test for sudo configuration
    - **Property 3: Sudo Privilege Configuration**
    - **Validates: Requirements 1.4, 2.3**

- [x] 3. Implement ssh_hardening role
  - [x] 3.1 Create ssh_hardening role structure
    - Define default variables for SSH port, timeouts, algorithm restrictions
    - Create sshd_config.j2 template with hardened settings
    - _Requirements: 3.11, 3.15, 3.16, 3.17_
  
  - [x] 3.2 Implement SSH daemon hardening configuration
    - Template sshd_config with disabled password auth, root login, dangerous features
    - Restrict algorithms to modern elliptic curves and AEAD ciphers
    - Configure AllowUsers, MaxAuthTries, LoginGraceTime, ClientAlive settings
    - Add handler to restart sshd on configuration changes
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 3.18_
  
  - [x] 3.3 Write property test for SSH hardening configuration
    - **Property 5: SSH Daemon Hardening Configuration**
    - **Validates: Requirements 3.1-3.9, 3.14, 3.18**
  
  - [x] 3.4 Write property test for SSH access restriction
    - **Property 6: SSH Access Restriction**
    - **Validates: Requirements 3.10**

- [x] 4. Implement system_updates role
  - [x] 4.1 Create system_updates role with apt update and upgrade tasks
    - Execute apt update to refresh package lists
    - Execute apt upgrade with non-interactive mode
    - Check for /var/run/reboot-required and notify operator
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  
  - [x] 4.2 Write property test for system updates
    - **Property 16: System Package Updates**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [x] 5. Implement tailscale role
  - [x] 5.1 Create tailscale role structure
    - Define default variables for enable flag, control server URL, pre-auth key
    - Add conditional execution based on tailscale_enabled variable
    - _Requirements: 4.1, 4.2, 4.3_
  
  - [x] 5.2 Implement Tailscale installation and authentication
    - Install Tailscale packages from official repository
    - Authenticate with Headscale using pre-auth key from Vault
    - Configure control server URL
    - Enable and start Tailscale service
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [x] 5.3 Implement Tailscale connectivity verification
    - Verify Tailscale interface exists and is connected
    - Test connectivity through Tailscale interface before SSH restriction
    - Fail with clear error if connectivity test fails
    - _Requirements: 5.1_
  
  - [x] 5.4 Write property test for Tailscale installation
    - **Property 10: Tailscale Installation and Configuration**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
  
  - [x] 5.5 Write property test for conditional execution
    - **Property 11: Tailscale Conditional Execution**
    - **Validates: Requirements 4.6, 9.8**

- [x] 6. Implement SSH interface restriction
  - [x] 6.1 Add SSH interface restriction logic to ssh_hardening role
    - Configure ListenAddress based on Tailscale status
    - When Tailscale enabled: listen only on Tailscale interface
    - When Tailscale disabled: listen on all interfaces (0.0.0.0, ::)
    - _Requirements: 5.1, 5.2, 5.3_
  
  - [x] 6.2 Write property test for SSH interface restriction
    - **Property 12: SSH Interface Restriction with Safety Check**
    - **Property 13: SSH Interface Configuration Based on VPN Status**
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [x] 7. Checkpoint - Verify core access configuration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement firewall role
  - [x] 8.1 Create firewall role structure
    - Define variables for SSH port, Tailscale interface, enable flag
    - Create nftables.conf.j2 template
    - _Requirements: 8.1, 8.2_
  
  - [x] 8.2 Implement NFTables configuration
    - Configure dual-stack rules (IPv4 and IPv6)
    - Set default policies to drop for input and forward chains
    - Allow established/related connections and loopback traffic
    - Conditionally restrict SSH to Tailscale interface or allow from all
    - Allow Tailscale WireGuard traffic when enabled
    - Add handler to reload nftables on configuration changes
    - Enable nftables service for boot persistence
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11_
  
  - [x] 8.3 Write property test for NFTables configuration
    - **Property 17: NFTables Dual-Stack Configuration**
    - **Property 18: NFTables Stateful Firewall Rules**
    - **Property 19: NFTables SSH Access Control**
    - **Validates: Requirements 8.1-8.8**
  
  - [x] 8.4 Write property test for service persistence
    - **Property 21: NFTables Service Persistence**
    - **Validates: Requirements 8.10, 8.11**

- [x] 9. Implement emergency_access role
  - [x] 9.1 Create emergency_access role structure
    - Create emergency-ssh-access.sh.j2 template
    - Add conditional deployment based on Tailscale enabled flag
    - _Requirements: 9.1, 9.8_
  
  - [x] 9.2 Implement emergency access script
    - Script toggles SSH ListenAddress between Tailscale IP and 0.0.0.0
    - Script updates NFTables rules to match SSH restriction
    - Script restarts sshd and reloads nftables after changes
    - Support unrestrict mode (default) and restore mode (--restore flag)
    - Implement idempotency checks
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_
  
  - [x] 9.3 Write property test for emergency script operations
    - **Property 23: Emergency Script Unrestrict Operation**
    - **Property 24: Emergency Script Restore Operation**
    - **Property 25: Emergency Script Round-Trip Restoration**
    - **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 9.6**
  
  - [x] 9.4 Write unit tests for emergency script edge cases
    - Test script behavior with missing configuration files
    - Test service restart failures
    - Test idempotency in both modes

- [x] 10. Implement fail2ban role
  - [x] 10.1 Create fail2ban role structure
    - Define default variables for max retry, ban time, find time
    - Create jail.local.j2 template for SSH monitoring
    - _Requirements: 10.3, 10.4_
  
  - [x] 10.2 Implement fail2ban configuration
    - Install fail2ban package
    - Configure SSH jail with journald backend
    - Configure NFTables integration
    - Enable and start fail2ban service
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  
  - [x] 10.3 Write property test for fail2ban configuration
    - **Property 27: Fail2ban Installation and Configuration**
    - **Validates: Requirements 10.1-10.7**

- [x] 11. Implement logging role
  - [x] 11.1 Create logging role structure
    - Define default variables for max disk usage and retention time
    - Create journald.conf.j2 template
    - _Requirements: 11.2, 11.3_
  
  - [x] 11.2 Implement journald configuration
    - Configure persistent storage to disk
    - Set SystemMaxUse and MaxRetentionSec from variables
    - Add handler to restart systemd-journald
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  
  - [x] 11.3 Write property test for journald configuration
    - **Property 28: Journald Persistent Logging Configuration**
    - **Validates: Requirements 11.1, 11.2, 11.3**

- [x] 12. Implement system_config role
  - [x] 12.1 Create system_config role structure
    - Define default variables for hostname, NTP servers, and time sync service choice
    - Create templates for chrony.conf and timesyncd.conf
    - _Requirements: 6.1, 6.2, 6.3, 12.2_
  
  - [x] 12.2 Implement hostname configuration
    - Set hostname using hostname module when variable is defined
    - Persist hostname across reboots
    - Skip when hostname variable is empty or undefined
    - _Requirements: 6.1, 6.2, 6.3_
  
  - [x] 12.3 Implement time synchronization configuration
    - Install and configure chrony or systemd-timesyncd
    - Configure NTP server list
    - Enable and start time sync service
    - Verify synchronization status after service start
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [x] 12.4 Write property test for hostname configuration
    - **Property 14: Hostname Configuration Persistence**
    - **Property 15: Hostname Configuration Skip**
    - **Validates: Requirements 6.1, 6.2, 6.3**
  
  - [x] 12.5 Write property test for time sync configuration
    - **Property 29: Time Synchronization Service Configuration**
    - **Validates: Requirements 12.1-12.5**

- [x] 13. Implement swap role
  - [x] 13.1 Create swap role structure
    - Define default variables for zram enable, zram size, disk swap size
    - Add conditional logic for zram and disk swap
    - _Requirements: 13.1, 13.2, 13.10_
  
  - [x] 13.2 Implement zram swap configuration
    - Install zram-tools or configure via systemd
    - Create zram device with specified size
    - Configure lz4 compression algorithm
    - Format and enable zram device as swap with priority 100
    - Configure boot persistence
    - _Requirements: 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9_
  
  - [x] 13.3 Implement disk swap configuration
    - Create /swapfile with specified size and mode 0600
    - Format and enable swap file with priority 10
    - Add to /etc/fstab for persistence
    - _Requirements: 13.11, 13.12, 13.13, 13.14, 13.15, 13.16_
  
  - [x] 13.4 Write property test for swap configuration
    - **Property 30: Zram Swap Configuration**
    - **Property 31: Disk Swap Configuration**
    - **Property 32: Swap Configuration Skip**
    - **Validates: Requirements 13.1-13.17**

- [x] 14. Checkpoint - Verify all roles implemented
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Create main playbook orchestration
  - [x] 15.1 Create site.yml main playbook
    - Define play targeting all hosts with root user
    - Include all roles in logical order: system_updates, users, ssh_hardening, tailscale, firewall, emergency_access, fail2ban, logging, system_config, swap
    - Add pre-flight checks for required variables and Debian stable
    - _Requirements: All requirements (orchestration)_
  
  - [x] 15.2 Create example inventory files
    - Create inventory/production.example with host examples
    - Create inventory/group_vars/all.yml.example with all configurable variables
    - Document variable purposes and defaults
    - _Requirements: 16.5_
  
  - [x] 15.3 Create Ansible Vault example
    - Create vault.yml.example with secret variable templates
    - Document vault encryption and usage
    - _Requirements: 16.10_
  
  - [x] 15.4 Write property test for playbook idempotency
    - **Property 33: Playbook Idempotency**
    - **Validates: Requirements 15.3, 15.4, 15.5**

- [ ] 16. Implement verification test suite
  - [x] 16.1 Create tests/verify_bootstrap.yml playbook
    - Implement 44 verification tasks from Requirement 14
    - Verify user accounts, UIDs, sudo configuration
    - Verify SSH configuration, algorithms, service state
    - Verify Tailscale service and connectivity (conditional)
    - Verify NFTables rules, policies, service state
    - Verify fail2ban, journald, time sync services
    - Verify swap configuration (conditional)
    - Verify hostname configuration (conditional)
    - Verify emergency script deployment (conditional)
    - _Requirements: 14.1-14.44_
  
  - [x] 16.2 Add verification test execution to Makefile
    - Add 'make verify' target to run verification playbook
    - _Requirements: 16.2, 16.12_
  
  - [ ]* 16.3 Write property test for configuration verification
    - **Property 34: Configuration Verification Round-Trip**
    - **Validates: Requirements 14.1-14.44**

- [ ] 17. Implement property-based test suite
  - [ ] 17.1 Create tests/property/ directory structure
    - Create test_idempotency_properties.py
    - Create test_configuration_properties.py
    - Create test_service_properties.py
    - Configure pytest with hypothesis settings (min 100 examples)
    - _Requirements: Testing strategy from design_
  
  - [ ] 17.2 Implement property tests for user management
    - Property 1: User creation with fixed UIDs
    - Property 2: SSH key deployment and permissions
    - Property 3: Sudo privilege configuration
    - Property 4: User authentication method configuration
    - Use hypothesis strategies for username generation
    - _Requirements: 1.1-1.8, 2.1-2.8_
  
  - [ ] 17.3 Implement property tests for SSH hardening
    - Property 5: SSH daemon hardening configuration
    - Property 6: SSH access restriction
    - Property 7: SSH port configuration
    - Property 8: SSH session security configuration
    - Use hypothesis strategies for port numbers and timeouts
    - _Requirements: 3.1-3.18_
  
  - [ ] 17.4 Implement property tests for Tailscale and firewall
    - Property 10: Tailscale installation and configuration
    - Property 11: Tailscale conditional execution
    - Property 12: SSH interface restriction with safety check
    - Property 13: SSH interface configuration based on VPN status
    - Property 17-21: NFTables configuration properties
    - _Requirements: 4.1-4.6, 5.1-5.3, 8.1-8.11_
  
  - [ ] 17.5 Implement property tests for emergency access
    - Property 22: Emergency script deployment
    - Property 23: Emergency script unrestrict operation
    - Property 24: Emergency script restore operation
    - Property 25: Emergency script round-trip restoration
    - Property 26: Emergency script idempotency
    - _Requirements: 9.1-9.8_
  
  - [ ] 17.6 Implement property tests for system services
    - Property 27: Fail2ban installation and configuration
    - Property 28: Journald persistent logging configuration
    - Property 29: Time synchronization service configuration
    - Property 30-32: Swap configuration properties
    - _Requirements: 10.1-10.7, 11.1-11.4, 12.1-12.5, 13.1-13.17_
  
  - [ ] 17.7 Implement property tests for playbook behavior
    - Property 9: Service restart on configuration change
    - Property 14-15: Hostname configuration properties
    - Property 16: System package updates
    - Property 33: Playbook idempotency
    - Property 34: Configuration verification round-trip
    - _Requirements: 6.1-6.3, 7.1-7.4, 15.3-15.5, 14.1-14.44_

- [ ] 18. Implement unit test suite
  - [ ] 18.1 Create tests/unit/ directory structure
    - Create test files for each role
    - Configure pytest for unit test execution
    - _Requirements: Testing strategy from design_
  
  - [ ] 18.2 Write unit tests for user management
    - Test specific username creation
    - Test SSH key deployment with specific key content
    - Test sudo configuration file content
    - Test authorized_keys permissions
    - _Requirements: 1.1-1.8, 2.1-2.8_
  
  - [ ] 18.3 Write unit tests for SSH hardening
    - Test specific SSHD configuration directives
    - Test algorithm restriction lists
    - Test AllowUsers directive with specific users
    - Test service restart handler
    - _Requirements: 3.1-3.18_
  
  - [ ] 18.4 Write unit tests for Tailscale
    - Test installation when enabled
    - Test skip when disabled
    - Test connectivity verification logic
    - _Requirements: 4.1-4.6, 5.1-5.3_
  
  - [ ] 18.5 Write unit tests for firewall
    - Test NFTables rule structure
    - Test IPv4 and IPv6 rule parity
    - Test conditional SSH access rules
    - Test default policies
    - _Requirements: 8.1-8.11_
  
  - [ ] 18.6 Write unit tests for emergency script
    - Test script generation with specific variables
    - Test unrestrict mode sed commands
    - Test restore mode sed commands
    - Test service restart commands
    - _Requirements: 9.1-9.8_
  
  - [ ] 18.7 Write unit tests for system services
    - Test fail2ban jail configuration
    - Test journald configuration values
    - Test time sync service selection
    - Test swap priority values
    - _Requirements: 10.1-10.7, 11.1-11.4, 12.1-12.5, 13.1-13.17_
  
  - [ ] 18.8 Write integration tests
    - Test full bootstrap execution on test VM
    - Test playbook on fresh system (password auth)
    - Test playbook on fresh system (SSH key auth)
    - Test playbook on already-configured system
    - Test emergency script end-to-end functionality
    - _Requirements: 15.1, 15.2, 15.3_

- [ ] 19. Checkpoint - Verify all tests implemented and passing
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 20. Documentation and final integration
  - [ ] 20.1 Complete README.md
    - Document all configurable variables with descriptions and defaults
    - Document prerequisites (uv, Ansible, SSH keys)
    - Document Vault setup and secret management
    - Document playbook execution steps
    - Document verification test execution
    - Document emergency script usage
    - Add troubleshooting section
    - _Requirements: 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12_
  
  - [ ] 20.2 Add inline documentation
    - Add comments to all Ansible tasks explaining purpose
    - Add comments to templates explaining configuration choices
    - Add docstrings to all Python test functions
    - Add comments to emergency script explaining operations
    - _Requirements: Documentation best practices_
  
  - [ ] 20.3 Create example configurations
    - Create example inventory for single VPS
    - Create example inventory for multiple VPS
    - Create example group_vars with common configurations
    - Create example vault.yml with all required secrets
    - _Requirements: 16.5, 16.10_

- [ ] 21. Final checkpoint - Complete system verification
  - Run full test suite (unit + property + integration)
  - Run verification playbook against test environment
  - Verify all 44 verification tests pass
  - Verify README instructions are accurate
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at logical breaks
- Property tests validate universal correctness properties across configuration space
- Unit tests validate specific examples and edge cases
- The verification test suite (Requirement 14) provides 44 concrete validation checks
- All roles follow Ansible best practices with tasks, defaults, handlers, and templates
- The emergency script provides recovery mechanism when Tailscale VPN fails
- Idempotency is a core design principle - playbook is safe to re-run
