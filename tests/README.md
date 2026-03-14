# Test Suite Documentation

This project uses pytest markers to organize and run different types of tests efficiently.

## Available Test Markers

### `@pytest.mark.unit`
Fast tests with no external dependencies. These tests verify logic by reading configuration files and templates without requiring actual system resources.

**Characteristics:**
- Fast execution (< 1 second per test)
- No network access required
- No VM or container required
- Tests configuration files, templates, and role structure

**Example:**
```python
@pytest.mark.property
@pytest.mark.unit
def test_ssh_config_properties():
    # Reads and validates SSH config template
    pass
```

### `@pytest.mark.property`
Property-based tests using Hypothesis. These tests verify universal properties that should hold for all valid inputs.

**Characteristics:**
- Generates many test cases automatically
- Tests edge cases and boundary conditions
- Verifies correctness properties across input space

**Example:**
```python
@pytest.mark.property
@pytest.mark.unit
@given(username=valid_username())
def test_user_creation_property(username: str):
    # Verifies property holds for any valid username
    pass
```

### `@pytest.mark.integration`
Tests that require actual system resources like VMs, containers, or real network connections.

**Characteristics:**
- Slow execution (seconds to minutes)
- Requires test infrastructure
- Tests actual system behavior
- May modify system state

**Example:**
```python
@pytest.mark.integration
@pytest.mark.slow
def test_actual_user_creation():
    # Runs Ansible playbook and verifies user exists
    pass
```

### `@pytest.mark.slow`
Tests that take significant time to execute, regardless of type.

**Characteristics:**
- Execution time > 5 seconds
- Often combined with integration tests
- Useful for CI/CD optimization

## Running Tests

### Run all tests
```bash
make test
```

### Run only unit tests (fast)
```bash
make test-unit
```

### Run only property-based tests
```bash
make test-property
```

### Run only integration tests (slow, requires infrastructure)
```bash
make test-integration
```

### Run specific marker combinations
```bash
# Property tests that are also unit tests
uv run pytest -m "property and unit"

# All tests except integration
uv run pytest -m "not integration"

# Only slow tests
uv run pytest -m slow

# Property tests that are NOT unit tests
uv run pytest -m "property and not unit"
```

## Current Test Organization

### Unit Tests (`tests/unit/`)
- `test_users.py` - User creation, SSH keys, sudo configuration
- `test_ssh_hardening.py` - SSHD config directives, algorithms, session security
- `test_firewall.py` - NFTables rules, policies, dual-stack, SSH access
- `test_emergency_script.py` - Script generation, sed commands, service restarts
- `test_emergency_script_edge_cases.py` - Missing configs, idempotency, backups
- `test_tailscale.py` - Installation, connectivity verification, skip-when-disabled
- `test_system_services.py` - Fail2ban, journald, time sync, swap configuration

### Property Tests (`tests/property/`)
- `test_user_properties.py` - User management across input space
- `test_ssh_hardening_properties.py` - SSH config properties
- `test_ssh_interface_restriction_properties.py` - ListenAddress binding
- `test_tailscale_properties.py` - Installation and connectivity
- `test_firewall_properties.py` - Dual-stack, stateful rules, SSH access, port knocking
- `test_emergency_access_properties.py` - Deployment, operations, idempotency
- `test_fail2ban_properties.py` - Config, journald/nftables integration
- `test_logging_properties.py` - Journald storage, compression, restarts
- `test_system_config_properties.py` - Hostname, time sync, NTP servers
- `test_swap_properties.py` - Zram, disk swap, priorities, size formats
- `test_system_updates_properties.py` - Package updates, idempotency
- `test_filesystem_hardening_properties.py` - Mount options
- `test_login_policy_properties.py` - Shell timeout, securetty, login.defs
- `test_pam_hardening_properties.py` - Faillock, resource limits
- `test_sudo_hardening_properties.py` - Sudo security defaults
- `test_idempotency_properties.py` - Playbook re-run properties
- `test_verification_properties.py` - Verification round-trip properties
- `test_configuration_properties.py` - Variable validation
- `test_service_properties.py` - Service management
- `test_playbook_behavior_properties.py` - Restarts, validation, handlers

### Integration Tests (`tests/integration/`)
- `test_bootstrap_integration.py` - Full bootstrap, SSH behavior, users, idempotency
- `test_tailscale_integration.py` - Tailscale-specific integration
- `test_single_role.py` - Individual role execution

### Verification Playbook
- `verify_bootstrap.yml` - 44 post-bootstrap checks (Tests 14.1-14.44)

## Adding New Tests

### Property-based unit test
```python
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

@pytest.mark.property
@pytest.mark.unit
@settings(max_examples=100)
@given(value=st.integers())
def test_my_property(value: int):
    # Test implementation
    pass
```

### Integration test
```python
import pytest

@pytest.mark.integration
@pytest.mark.slow
def test_actual_deployment():
    # Test implementation that requires real infrastructure
    pass
```

### Mixed property + integration test
```python
import pytest
from hypothesis import given
from hypothesis import strategies as st

@pytest.mark.property
@pytest.mark.integration
@pytest.mark.slow
@given(config=valid_config())
def test_deployment_property(config):
    # Property test that requires actual system
    pass
```

## CI/CD Optimization

The marker system enables efficient CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - run: make test-unit  # Run fast tests first
  
  integration-tests:
    runs-on: ubuntu-latest
    needs: fast-tests  # Only run if fast tests pass
    steps:
      - run: make test-integration  # Run slow tests later
```

## Best Practices

1. **Mark all tests appropriately** - Every test should have at least one marker
2. **Combine markers when relevant** - A test can be both `@pytest.mark.property` and `@pytest.mark.unit`
3. **Use `unit` for fast tests** - If it doesn't need real infrastructure, mark it as `unit`
4. **Use `integration` for real system tests** - If it needs VMs, containers, or network, mark it as `integration`
5. **Use `slow` for long-running tests** - Help developers and CI systems optimize test runs
6. **Run fast tests during development** - Use `make test-unit` for quick feedback
7. **Run all tests before committing** - Use `make test` to ensure everything passes

## Hypothesis Configuration

Property-based tests use Hypothesis with the following configuration (in `pyproject.toml`):

```toml
[tool.hypothesis]
max_examples = 100
```

This means each property test will run 100 different generated test cases by default. You can override this per-test using `@settings(max_examples=N)`.

## Requirements Traceability Matrix

Maps each acceptance criterion from [requirements.md](../.kiro/specs/vps-bootstrap-playbook/requirements.md) to the tests that cover it.

**Legend:** U = Unit test, P = Property test, I = Integration test, V = Verification playbook (verify_bootstrap.yml)

### Req 1: Manual Access User Creation

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 1.1 | Create user with uid 1000 | `test_users::TestManualUserCreation::test_manual_user_uid_is_1000` | `test_user_properties` | `test_bootstrap_integration::TestFullBootstrapExecution::test_bootstrap_creates_manual_user` | Test 14.1 |
| 1.2 | Configurable username variable | `test_users::TestManualUserCreation` (fixture-driven) | `test_user_properties` | | |
| 1.3 | Password as runtime variable | `test_users::TestManualUserCreation::test_manual_user_password_uses_pre_hashed_variable` | `test_user_properties` | | |
| 1.4 | Grant sudo privileges | `test_users::TestSudoConfiguration::test_manual_user_sudo_content_requires_password` | `test_sudo_hardening_properties` | `test_bootstrap_integration::TestUsersBehavior::test_manual_user_can_sudo_with_password` | Test 14.3 |
| 1.5 | Configure password auth | `test_users::TestManualUserCreation` | `test_user_properties` | | |
| 1.6 | Deploy SSH public keys | `test_users::TestSSHKeyDeployment::test_manual_user_authorized_key_state_present` | `test_user_properties` | | |
| 1.7 | Configurable key file path | `test_users::TestSSHKeyDeployment` | `test_user_properties` | | |
| 1.8 | Permissions on authorized_keys | `test_users::TestSSHKeyDeployment::test_manual_user_authorized_keys_mode_uses_variable` | `test_user_properties` | | Test 14.3 |

### Req 2: Ansible User Creation

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 2.1 | Create user with uid 1999 | `test_users::TestAnsibleUserCreation::test_deploy_user_uid_is_1999` | `test_user_properties` | `test_bootstrap_integration::TestFullBootstrapExecution::test_bootstrap_creates_ansible_user` | Test 14.2 |
| 2.2 | Configurable username variable | `test_users::TestAnsibleUserCreation` (fixture-driven) | `test_user_properties` | | |
| 2.3 | Passwordless sudo | `test_users::TestSudoConfiguration::test_ansible_user_sudo_content_is_passwordless` | `test_sudo_hardening_properties` | `test_bootstrap_integration::TestUsersBehavior::test_ansible_user_has_passwordless_sudo` | Test 14.4 |
| 2.4 | SSH key-only auth | `test_users::TestAnsibleUserCreation::test_ansible_user_password_is_locked` | `test_user_properties` | | |
| 2.5 | Deploy SSH public keys | `test_users::TestSSHKeyDeployment::test_ansible_user_authorized_key_state_present` | `test_user_properties` | | |
| 2.6 | Configurable key file path | `test_users::TestSSHKeyDeployment` | `test_user_properties` | | |
| 2.7 | Permissions on authorized_keys | `test_users::TestSSHKeyDeployment::test_ansible_user_authorized_keys_mode_uses_variable` | `test_user_properties` | | Test 14.4 |
| 2.8 | Disable password auth | `test_users::TestAnsibleUserCreation::test_ansible_user_password_is_locked` | `test_user_properties` | | |

### Req 3: SSH Hardening

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 3.1 | Disable password auth | `test_ssh_hardening::TestSSHDConfigDirectives::test_password_authentication_disabled` | `test_ssh_hardening_properties` | `test_bootstrap_integration::TestSSHHardeningBehavior::test_password_auth_rejected` | Test 14.5 |
| 3.2 | Disable root login | `test_ssh_hardening::TestSSHDConfigDirectives::test_root_login_disabled` | `test_ssh_hardening_properties` | `test_bootstrap_integration::TestSSHHardeningBehavior::test_root_login_rejected` | Test 14.6 |
| 3.3 | Restrict KEX algorithms | `test_ssh_hardening::TestAlgorithmRestrictions::test_kex_algorithms_present`, `test_no_weak_kex_algorithms` | `test_ssh_hardening_properties` | | Test 14.9 |
| 3.4 | Restrict ciphers (AEAD) | `test_ssh_hardening::TestAlgorithmRestrictions::test_ciphers_are_aead_only`, `test_no_cbc_ciphers` | `test_ssh_hardening_properties` | | Test 14.10 |
| 3.5 | Restrict MACs (ETM) | `test_ssh_hardening::TestAlgorithmRestrictions::test_macs_are_etm_only`, `test_no_non_etm_macs` | `test_ssh_hardening_properties` | | Test 14.11 |
| 3.6 | Disable X11 forwarding | `test_ssh_hardening::TestSSHDConfigDirectives::test_x11_forwarding_disabled` | `test_ssh_hardening_properties` | | Test 14.12 |
| 3.7 | Disable TCP forwarding | `test_ssh_hardening::TestSSHDConfigDirectives::test_tcp_forwarding_disabled` | `test_ssh_hardening_properties` | | Test 14.13 |
| 3.8 | Disable agent forwarding | `test_ssh_hardening::TestSSHDConfigDirectives::test_agent_forwarding_disabled` | `test_ssh_hardening_properties` | | Test 14.14 |
| 3.9 | Disable tunneling | `test_ssh_hardening::TestSSHDConfigDirectives::test_tunneling_disabled` | `test_ssh_hardening_properties` | | Test 14.15 |
| 3.10 | Restrict to allowed users only | `test_ssh_hardening::TestAllowUsersDirective` | `test_ssh_hardening_properties` | `test_bootstrap_integration::TestSSHHardeningBehavior::test_unknown_user_rejected` | Test 14.8 |
| 3.11 | Configurable SSH port (default 22) | `test_ssh_hardening::TestSSHDConfigDirectives::test_custom_ssh_port` | `test_ssh_hardening_properties` | | |
| 3.12 | Listen on specified port | `test_ssh_hardening::TestSSHDConfigDirectives::test_ssh_port_rendered` | `test_ssh_hardening_properties` | | Test 14.7 |
| 3.13 | Restart SSHD on config change | | `test_playbook_behavior_properties::TestServiceRestartProperties` | | |
| 3.14 | Public key auth only | `test_ssh_hardening::TestSSHDConfigDirectives::test_pubkey_authentication_enabled` | `test_ssh_hardening_properties` | | Test 14.5 |
| 3.15 | Low MaxAuthTries | `test_ssh_hardening::TestSessionSecurity::test_max_auth_tries` | `test_ssh_hardening_properties` | | |
| 3.16 | Short LoginGraceTime | `test_ssh_hardening::TestSessionSecurity::test_login_grace_time` | `test_ssh_hardening_properties` | | |
| 3.17 | ClientAlive interval/count | `test_ssh_hardening::TestSessionSecurity::test_client_alive_interval`, `test_client_alive_count_max` | `test_ssh_hardening_properties` | | |
| 3.18 | Disable empty passwords | `test_ssh_hardening::TestSSHDConfigDirectives::test_empty_passwords_disabled` | `test_ssh_hardening_properties` | | Test 14.5 |

### Req 4: Tailscale Installation

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 4.1 | Install from official repo | `test_tailscale::TestTailscaleInstallation::test_gpg_key_task_exists`, `test_repository_task_exists`, `test_install_package_task_exists` | `test_tailscale_properties::TestTailscaleInstallationProperties` | | |
| 4.2 | Auth with Pre-Auth Key | `test_tailscale::TestTailscaleInstallation::test_authenticate_task_uses_authkey` | `test_tailscale_properties` | | |
| 4.3 | Configure Control Server URL | `test_tailscale::TestTailscaleInstallation::test_authenticate_task_uses_login_server` | `test_tailscale_properties` | | |
| 4.4 | Enable on boot | `test_tailscale::TestTailscaleInstallation::test_service_enabled_task_exists` | `test_tailscale_properties` | | Test 14.19 |
| 4.5 | Start service | `test_tailscale::TestTailscaleInstallation::test_service_started_task_exists` | `test_tailscale_properties` | | Test 14.18 |
| 4.6 | Skip when disabled | `test_tailscale::TestTailscaleSkipWhenDisabled::test_main_tasks_use_when_condition` | `test_tailscale_properties::TestTailscaleConditionalExecutionProperties` | `test_bootstrap_integration::TestDisabledServices::test_tailscale_not_running` | |

### Req 5: SSH Interface Restriction

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 5.1 | Verify Tailscale connectivity first | `test_tailscale::TestTailscaleConnectivityVerification::test_interface_wait_task_exists` | `test_tailscale_properties::TestTailscaleConnectivityVerificationProperties` | | |
| 5.2 | Listen only on Tailscale when enabled | `test_ssh_hardening::TestSSHInterfaceRestriction::test_listen_tailscale_only_when_enabled` | `test_ssh_interface_restriction_properties` | | Test 14.20 |
| 5.3 | Listen on all when disabled | `test_ssh_hardening::TestSSHInterfaceRestriction::test_listen_all_interfaces_when_tailscale_disabled` | `test_ssh_interface_restriction_properties` | | |

### Req 6: Hostname Configuration

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 6.1 | Set hostname when specified | | `test_system_config_properties::TestHostnameConfigurationProperties` | | Test 14.29 |
| 6.2 | Persist across reboots | | `test_system_config_properties::TestHostnameConfigurationProperties` | | |
| 6.3 | Skip when not configured | | `test_system_config_properties::TestHostnameConfigurationProperties` | | |

### Req 7: System Updates

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 7.1 | Execute apt update | | `test_system_updates_properties` | | |
| 7.2 | Execute apt upgrade | | `test_system_updates_properties` | | |
| 7.3 | Target Debian stable | | `test_system_updates_properties` | | |
| 7.4 | Notify when reboot required | | `test_system_updates_properties` | | |

### Req 8: Firewall Configuration

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 8.1 | NFTables rules for IPv4 | `test_firewall::TestNFTablesRuleStructure::test_uses_inet_family` | `test_firewall_properties::TestNFTablesDualStackProperties` | | |
| 8.2 | NFTables rules for IPv6 | `test_firewall::TestDualStackRules::test_icmp_rules_for_both_stacks` | `test_firewall_properties::TestNFTablesDualStackProperties` | | |
| 8.3 | Allow established/related | `test_firewall::TestDefaultPolicies::test_established_related_accepted` | `test_firewall_properties::TestNFTablesStatefulFirewallProperties` | | Test 14.26 |
| 8.4 | Allow loopback | `test_firewall::TestDefaultPolicies::test_loopback_accepted` | `test_firewall_properties::TestNFTablesStatefulFirewallProperties` | | Test 14.27 |
| 8.5 | Default input: drop | `test_firewall::TestDefaultPolicies::test_input_chain_default_drop` | `test_firewall_properties` | | Test 14.24 |
| 8.6 | Default forward: drop | `test_firewall::TestDefaultPolicies::test_forward_chain_default_drop` | `test_firewall_properties` | | Test 14.25 |
| 8.7 | SSH restricted to Tailscale when enabled | `test_firewall::TestSSHAccessRules::test_ssh_restricted_to_tailscale_when_enabled` | `test_firewall_properties::TestNFTablesSSHAccessControlProperties` | `test_tailscale_integration` | |
| 8.8 | SSH from all when disabled | `test_firewall::TestSSHAccessRules::test_ssh_allowed_from_all_when_tailscale_disabled` | `test_firewall_properties::TestNFTablesSSHAccessControlProperties` | | Test 14.28 |
| 8.9 | Allow WireGuard UDP when enabled | `test_firewall::TestSSHAccessRules::test_wireguard_allowed_when_tailscale_enabled` | `test_firewall_properties` | | |
| 8.10 | Enable NFTables service | | `test_firewall_properties::TestNFTablesServicePersistenceProperties` | `test_bootstrap_integration::TestFullBootstrapExecution::test_bootstrap_configures_firewall` | Test 14.22 |
| 8.11 | Persist rules across reboots | | `test_firewall_properties::TestNFTablesServicePersistenceProperties` | | Test 14.23 |

### Req 9: Emergency Access Script

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 9.1 | Deploy to /root/ when Tailscale enabled | `test_emergency_script::TestScriptGeneration::test_script_deployed_to_root` | `test_emergency_access_properties::TestEmergencyScriptDeploymentProperties` | | Test 14.21 |
| 9.2 | Unrestrict SSH+NFTables (no args) | `test_emergency_script::TestUnrestrictModeSedCommands` | `test_emergency_access_properties::TestEmergencyScriptOperationsProperties` | | |
| 9.3 | Restore restrictions (--restore) | `test_emergency_script::TestRestoreModeSedCommands` | `test_emergency_access_properties::TestEmergencyScriptOperationsProperties` | | |
| 9.4 | Round-trip restore | `test_emergency_script_edge_cases::TestIdempotency::test_alternating_modes_idempotency` | `test_emergency_access_properties::TestEmergencyScriptIdempotencyProperties` | | |
| 9.5 | Restart SSHD after change | `test_emergency_script::TestServiceRestartCommands::test_sshd_restart_command_present` | `test_emergency_access_properties` | | |
| 9.6 | Reload NFTables after change | `test_emergency_script::TestServiceRestartCommands::test_nftables_reload_command_present` | `test_emergency_access_properties` | | |
| 9.7 | Idempotent (safe to re-run) | `test_emergency_script::TestUnrestrictModeSedCommands::test_unrestrict_idempotency_check_present`, `test_emergency_script_edge_cases::TestIdempotency` | `test_emergency_access_properties::TestEmergencyScriptIdempotencyProperties` | | |
| 9.8 | Skip when Tailscale disabled | | `test_emergency_access_properties::TestEmergencyScriptDeploymentProperties` | `test_bootstrap_integration::TestDisabledServices::test_emergency_script_not_deployed_when_tailscale_disabled` | |

### Req 10: Intrusion Prevention

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 10.1 | Install fail2ban | `test_system_services::TestFail2banConfiguration::test_install_task_exists` | `test_fail2ban_properties` | | |
| 10.2 | Monitor SSHD logs | `test_system_services::TestFail2banConfiguration::test_sshd_jail_enabled`, `test_backend_is_systemd` | `test_fail2ban_properties` | | Test 14.32 |
| 10.3 | Configure maxretry/findtime | `test_system_services::TestFail2banConfiguration::test_max_retry_rendered`, `test_find_time_rendered` | `test_fail2ban_properties` | | |
| 10.4 | Configurable ban duration | `test_system_services::TestFail2banConfiguration::test_ban_time_rendered` | `test_fail2ban_properties` | | |
| 10.5 | Work with NFTables | `test_system_services::TestFail2banConfiguration::test_banaction_is_nftables` | `test_fail2ban_properties::TestFail2banNFTablesIntegrationProperties` | | |
| 10.6 | Enable on boot | `test_system_services::TestFail2banConfiguration::test_service_enabled_task_exists` | `test_fail2ban_properties` | | Test 14.31 |
| 10.7 | Start service | `test_system_services::TestFail2banConfiguration::test_service_started_task_exists` | `test_fail2ban_properties` | `test_bootstrap_integration::TestFullBootstrapExecution::test_bootstrap_configures_fail2ban` | Test 14.30 |

### Req 11: System Logging

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 11.1 | Persist logs to disk | `test_system_services::TestJournaldConfiguration::test_storage_is_persistent` | `test_logging_properties::TestJournaldProperties` | | Test 14.33 |
| 11.2 | Configurable max disk usage | `test_system_services::TestJournaldConfiguration::test_max_disk_usage_rendered` | `test_logging_properties::TestJournaldProperties` | | |
| 11.3 | Configurable retention time | `test_system_services::TestJournaldConfiguration::test_max_retention_rendered` | `test_logging_properties::TestJournaldProperties` | | |
| 11.4 | Restart journald on change | `test_system_services::TestJournaldConfiguration::test_deploy_task_notifies_restart` | `test_logging_properties::TestJournaldServiceRestartProperties` | | |

### Req 12: Time Synchronization

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 12.1 | Install and configure service | `test_system_services::TestTimeSyncServiceSelection::test_chrony_contains_pool_directives` | `test_system_config_properties::TestTimeSynchronizationProperties` | | |
| 12.2 | Reliable NTP servers | `test_system_services::TestTimeSyncServiceSelection::test_chrony_has_all_four_servers`, `test_timesyncd_ntp_line` | `test_system_config_properties::TestNTPServerConfigurationProperties` | | |
| 12.3 | Enable on boot | | `test_system_config_properties::TestTimeSynchronizationProperties` | | Test 14.35 |
| 12.4 | Start service | | `test_system_config_properties::TestTimeSynchronizationProperties` | | Test 14.34 |
| 12.5 | Verify sync is active | | `test_system_config_properties::TestTimeSynchronizationProperties` | `test_bootstrap_integration::TestTimeSyncBehavior` | Test 14.36 |

### Req 13: Swap Configuration

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 13.1 | Configurable zram enablement | `test_system_services::TestSwapPriorityValues::test_zram_conditional_on_zram_enabled` | `test_swap_properties::TestZramSwapProperties` | | |
| 13.2 | Configurable zram size | `test_system_services::TestSwapPriorityValues::test_zram_percentage_size`, `test_zram_absolute_size_*` | `test_swap_properties::TestZramSizeFormatProperties` | | |
| 13.3 | Install zram-tools/systemd | | `test_swap_properties::TestZramSwapProperties` | | |
| 13.4 | Create zram device | | `test_swap_properties::TestZramSwapProperties` | | Test 14.37 |
| 13.5 | Lz4 compression | `test_system_services::TestSwapPriorityValues::test_zram_compression_is_lz4` | `test_swap_properties::TestZramSwapProperties` | | Test 14.39 |
| 13.6 | Format as swap | | `test_swap_properties::TestZramSwapProperties` | | |
| 13.7 | Enable as swap | | `test_swap_properties::TestZramSwapProperties` | | Test 14.38 |
| 13.8 | Initialize on boot | | `test_swap_properties::TestZramSwapProperties` | | |
| 13.9 | Zram priority > disk | `test_system_services::TestSwapPriorityValues::test_zram_priority_higher_than_disk` | `test_swap_properties::TestSwapPriorityProperties` | | Test 14.40 |
| 13.10 | Configurable disk swap size | `test_system_services::TestSwapPriorityValues::test_disk_swap_conditional_on_size` | `test_swap_properties::TestDiskSwapProperties` | | |
| 13.11 | Create /swapfile | | `test_swap_properties::TestDiskSwapProperties` | | Test 14.41 |
| 13.12 | Permissions 0600 | `test_system_services::TestSwapPriorityValues::test_disk_swap_file_mode_0600` | `test_swap_properties::TestDiskSwapProperties` | | |
| 13.13 | Format as swap | | `test_swap_properties::TestDiskSwapProperties` | | |
| 13.14 | Enable swap file | | `test_swap_properties::TestDiskSwapProperties` | | Test 14.42 |
| 13.15 | Add to /etc/fstab | `test_system_services::TestSwapPriorityValues::test_disk_swap_fstab_entry_includes_priority` | `test_swap_properties::TestDiskSwapProperties` | | Test 14.43 |
| 13.16 | Disk priority < zram | `test_system_services::TestSwapPriorityValues::test_zram_priority_higher_than_disk` | `test_swap_properties::TestSwapPriorityProperties` | | |
| 13.17 | Skip when neither enabled | | `test_swap_properties::TestSwapConfigurationSkipProperties` | | |

### Req 14: Configuration Testing

All 44 acceptance criteria are implemented as Tests 14.1-14.44 in `verify_bootstrap.yml`. See the [Verification Playbook](#verification-playbook) section above.

### Req 15: Idempotency

| AC | Description | U | P | I | V |
|----|-------------|---|---|---|---|
| 15.1 | Fresh VPS with root password | | `test_idempotency_properties` | `test_bootstrap_integration::TestFullBootstrapExecution` | |
| 15.2 | Fresh VPS with root SSH key | | `test_idempotency_properties` | `test_bootstrap_integration::TestFullBootstrapExecution` | |
| 15.3 | No errors on re-run | | `test_idempotency_properties` | `test_bootstrap_integration::TestPlaybookIdempotency::test_second_run_reports_no_failures` | |
| 15.4 | No changes on re-run | | `test_idempotency_properties` | `test_bootstrap_integration::TestPlaybookIdempotency::test_second_run_reports_no_failures` | |
| 15.5 | Apply only diffs | | `test_idempotency_properties` | `test_bootstrap_integration::TestPlaybookIdempotency::test_check_mode_reports_no_changes` | |

### Req 16: Documentation

| AC | Description | Covered By |
|----|-------------|------------|
| 16.1 | pyproject.toml | `pyproject.toml` |
| 16.2 | Makefile | `Makefile` |
| 16.3 | Makefile uses uv run for ansible-playbook | `Makefile::bootstrap` |
| 16.4 | Makefile uses uv run for ansible-vault | `AGENTS.md` documents `uv run ansible-vault` |
| 16.5 | README with variable docs | `README.md` |
| 16.6 | Document prerequisites | `README.md` |
| 16.7 | Document initial-setup-only | `README.md` |
| 16.8 | Document SSH key generation | `README.md` |
| 16.9 | Document required variables | `README.md` |
| 16.10 | Document secrets management | `README.md` |
| 16.11 | Document running playbook | `README.md` |
| 16.12 | Document running test suite | `README.md` |
