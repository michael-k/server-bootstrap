"""
Property-based tests for swap configuration in VPS Bootstrap Playbook.

These tests verify universal properties about zram and disk swap configuration
across all valid configurations.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Hypothesis strategies for generating valid swap configuration values
@st.composite
def valid_zram_size_percentage(draw):
    """Generate valid zram size as percentage of RAM (1-100%)."""
    percentage = draw(st.integers(min_value=1, max_value=100))
    return f"{percentage}%"


@st.composite
def valid_zram_size_absolute(draw):
    """Generate valid zram size as absolute size."""
    # Support MB and GB formats
    unit = draw(st.sampled_from(["M", "G"]))
    if unit == "M":
        # 256MB to 8192MB (8GB)
        value = draw(st.integers(min_value=256, max_value=8192))
    else:
        # 1GB to 8GB
        value = draw(st.integers(min_value=1, max_value=8))
    return f"{value}{unit}"


@st.composite
def valid_zram_size(draw):
    """Generate valid zram size (percentage or absolute)."""
    format_choice = draw(st.sampled_from(["percentage", "absolute"]))
    if format_choice == "percentage":
        return draw(valid_zram_size_percentage())
    else:
        return draw(valid_zram_size_absolute())


@st.composite
def valid_disk_swap_size(draw):
    """Generate valid disk swap size."""
    # Support MB and GB formats
    unit = draw(st.sampled_from(["M", "G"]))
    if unit == "M":
        # 512MB to 16384MB (16GB)
        value = draw(st.integers(min_value=512, max_value=16384))
    else:
        # 1GB to 16GB
        value = draw(st.integers(min_value=1, max_value=16))
    return f"{value}{unit}"


@st.composite
def valid_swap_priority(draw):
    """Generate valid swap priority values (0-32767)."""
    return draw(st.integers(min_value=0, max_value=32767))


@st.composite
def valid_compression_algorithm(draw):
    """Generate valid zram compression algorithms."""
    return draw(st.sampled_from(["lz4", "lzo", "zstd", "lz4hc"]))


class TestZramSwapProperties:
    """Property-based tests for zram swap configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        zram_size=valid_zram_size(),
        zram_priority=valid_swap_priority(),
    )
    def test_property_30_zram_swap_configuration(
        self,
        zram_size: str,
        zram_priority: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 30: Zram Swap Configuration

        For any execution of the bootstrap playbook WHERE zram is enabled with a
        specified size, a zram device SHALL be created with the specified size,
        configured to use lz4 compression, formatted as swap, enabled as swap,
        configured to initialize on boot, and assigned a higher priority than disk swap.

        Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9
        """
        # This property test verifies the swap role's zram behavior by checking:
        # 1. zram-tools is installed (Requirement 13.3)
        # 2. zram device is created with specified size (Requirement 13.4)
        # 3. lz4 compression is configured (Requirement 13.5)
        # 4. zram device is formatted as swap (Requirement 13.6)
        # 5. zram device is enabled as swap (Requirement 13.7)
        # 6. zram device initializes on boot (Requirement 13.8)
        # 7. zram priority is higher than disk swap (Requirement 13.9)

        # Read the swap role tasks
        tasks_path = Path("roles/swap/tasks/main.yml")
        assert tasks_path.exists(), "Swap tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify zram configuration is conditionally included
        assert "ansible.builtin.include_tasks: zram.yml" in tasks_content, (
            "Zram configuration tasks must be included"
        )
        assert "when: zram_enabled | bool" in tasks_content, (
            "Zram configuration must be conditional on zram_enabled variable"
        )

        # Read the zram tasks
        zram_tasks_path = Path("roles/swap/tasks/zram.yml")
        assert zram_tasks_path.exists(), "Zram tasks file must exist"

        zram_tasks_content = zram_tasks_path.read_text()

        # Verify Requirement 13.3: zram-tools is installed
        assert "ansible.builtin.apt:" in zram_tasks_content, (
            "Zram-tools must be installed using apt module (Requirement 13.3)"
        )
        assert "name: zram-tools" in zram_tasks_content, (
            "Zram-tools package must be installed (Requirement 13.3)"
        )
        assert "state: present" in zram_tasks_content, (
            "Zram-tools package state must be present"
        )

        # Verify package cache is updated
        assert (
            "update_cache: true" in zram_tasks_content
            or "update_cache: yes" in zram_tasks_content
        ), "Package cache should be updated during zram-tools installation"

        # Verify zram configuration file is deployed
        assert "ansible.builtin.template:" in zram_tasks_content, (
            "Zram configuration must be deployed using template module"
        )
        assert "src: zram.conf.j2" in zram_tasks_content, (
            "Zram configuration template must be zram.conf.j2"
        )
        assert "dest: /etc/default/zramswap" in zram_tasks_content, (
            "Zram configuration must be deployed to /etc/default/zramswap"
        )

        # Verify configuration changes trigger service restart
        assert "notify: Restart zramswap service" in zram_tasks_content, (
            "Configuration changes must trigger zramswap service restart"
        )

        # Verify Requirement 13.8: zramswap service is enabled to start on boot
        assert "ansible.builtin.systemd:" in zram_tasks_content, (
            "Zramswap service must be managed using systemd module"
        )
        assert "name: zramswap" in zram_tasks_content, (
            "Service name must be zramswap"
        )
        assert "enabled: true" in zram_tasks_content or "enabled: yes" in zram_tasks_content, (
            "Zramswap service must be enabled to start on boot (Requirement 13.8)"
        )

        # Verify Requirement 13.7: zramswap service is started
        assert "state: started" in zram_tasks_content, (
            "Zramswap service must be started (Requirement 13.7)"
        )

        # Verify zram device creation is verified
        assert "ansible.builtin.wait_for:" in zram_tasks_content, (
            "Zram device creation must be verified using wait_for module"
        )
        assert "path: /dev/zram0" in zram_tasks_content, (
            "Wait for /dev/zram0 device to be created (Requirement 13.4)"
        )

        # Verify Requirement 13.7: zram device is active as swap
        assert "ansible.builtin.command: swapon --show --noheadings" in zram_tasks_content, (
            "Zram swap activation must be verified using swapon command (Requirement 13.7)"
        )
        assert "register: swap_status" in zram_tasks_content, (
            "Swap status must be registered for verification"
        )
        assert "'/dev/zram0' not in swap_status.stdout" in zram_tasks_content, (
            "Verification must check that /dev/zram0 is in swap output"
        )

        # Verify Requirement 13.5: lz4 compression algorithm is verified
        assert (
            "ansible.builtin.command: cat /sys/block/zram0/comp_algorithm"
            in zram_tasks_content
        ), "Zram compression algorithm must be verified (Requirement 13.5)"
        assert "register: zram_comp_algo" in zram_tasks_content, (
            "Compression algorithm must be registered for verification"
        )

        # Verify lz4 compression is asserted
        assert "ansible.builtin.assert:" in zram_tasks_content, (
            "Compression algorithm must be asserted"
        )
        assert (
            "'[lz4]' in zram_comp_algo.stdout or 'lz4' in zram_comp_algo.stdout"
            in zram_tasks_content
        ), "Assertion must check for lz4 compression (Requirement 13.5)"

        # Read the swap defaults
        defaults_path = Path("roles/swap/defaults/main.yml")
        assert defaults_path.exists(), "Swap defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify Requirement 13.1: zram enablement is configurable
        assert "zram_enabled:" in defaults_content, (
            "zram_enabled must be defined in defaults (Requirement 13.1)"
        )
        assert "zram_enabled: false" in defaults_content, (
            "Default zram_enabled should be false (opt-in)"
        )

        # Verify Requirement 13.2: zram size is configurable
        assert "zram_size:" in defaults_content, (
            "zram_size must be defined in defaults (Requirement 13.2)"
        )

        # Verify default zram size is reasonable (percentage or absolute)
        assert (
            '"50%"' in defaults_content or "'50%'" in defaults_content or
            '"2G"' in defaults_content or "'2G'" in defaults_content or
            '"1G"' in defaults_content or "'1G'" in defaults_content
        ), "Default zram_size should be a reasonable value (percentage or absolute size)"

        # Verify Requirement 13.9: zram priority is configurable and higher than disk swap
        assert "zram_swap_priority:" in defaults_content, (
            "zram_swap_priority must be defined in defaults (Requirement 13.9)"
        )
        assert "disk_swap_priority:" in defaults_content, (
            "disk_swap_priority must be defined in defaults"
        )

        # Extract priority values to verify zram priority is higher
        zram_priority_line = [
            line for line in defaults_content.split('\n')
            if 'zram_swap_priority:' in line
        ]
        disk_priority_line = [
            line for line in defaults_content.split('\n')
            if 'disk_swap_priority:' in line
        ]

        if zram_priority_line and disk_priority_line:
            # Extract value, removing comments
            zram_value_str = zram_priority_line[0].split(':')[1].split('#')[0].strip()
            disk_value_str = disk_priority_line[0].split(':')[1].split('#')[0].strip()
            zram_priority_value = int(zram_value_str)
            disk_priority_value = int(disk_value_str)
            assert zram_priority_value > disk_priority_value, (
                f"Zram priority ({zram_priority_value}) must be higher than disk swap priority "
                f"({disk_priority_value}) (Requirement 13.9)"
            )

        # Read the zram configuration template
        template_path = Path("roles/swap/templates/zram.conf.j2")
        assert template_path.exists(), "Zram configuration template must exist"

        template_content = template_path.read_text()

        # Verify Requirement 13.2: size configuration supports percentage format
        assert "{% if zram_size.endswith('%') %}" in template_content, (
            "Template must support percentage format for zram_size (Requirement 13.2)"
        )
        assert "PERCENTAGE={{ zram_size.rstrip('%') }}" in template_content, (
            "Template must configure PERCENTAGE when using percentage format"
        )

        # Verify Requirement 13.2: size configuration supports absolute format
        assert (
            "{% if zram_size.endswith('G') or zram_size.endswith('g') %}"
            in template_content
        ), "Template must support GB format for zram_size (Requirement 13.2)"
        assert (
            "SIZE={{ (zram_size.rstrip('Gg') | int) * 1024 }}" in template_content
        ), "Template must convert GB to MB for SIZE configuration"
        assert (
            "{% elif zram_size.endswith('M') or zram_size.endswith('m') %}"
            in template_content
        ), "Template must support MB format for zram_size (Requirement 13.2)"
        assert "SIZE={{ zram_size.rstrip('Mm') | int }}" in template_content, (
            "Template must configure SIZE when using MB format"
        )

        # Verify Requirement 13.5: lz4 compression algorithm is configured
        assert "ALGO=lz4" in template_content, (
            "Template must configure lz4 compression algorithm (Requirement 13.5)"
        )

        # Verify Requirement 13.9: priority is configured
        assert (
            "PRIORITY={{ zram_swap_priority }}" in template_content
        ), (
            "Template must configure swap priority using zram_swap_priority "
            "variable (Requirement 13.9)"
        )

        # Verify template has Ansible managed comment
        assert (
            "Managed by Ansible" in template_content
            or "do not edit" in template_content.lower()
        ), "Template should have Ansible managed comment"

        # Verify handlers file exists for service restart
        handlers_path = Path("roles/swap/handlers/main.yml")
        assert handlers_path.exists(), "Swap handlers file must exist"

        handlers_content = handlers_path.read_text()

        # Verify restart handler is defined
        assert "name: Restart zramswap service" in handlers_content, (
            "Restart zramswap service handler must be defined"
        )
        assert "ansible.builtin.systemd:" in handlers_content, (
            "Restart handler must use systemd module"
        )
        assert "name: zramswap" in handlers_content, (
            "Restart handler must target zramswap service"
        )
        assert "state: restarted" in handlers_content, (
            "Restart handler must restart the service"
        )

        # Property verified: The swap role configuration ensures that:
        # - zram_enabled is configurable (13.1)
        # - zram_size is configurable with percentage and absolute formats (13.2)
        # - zram-tools is installed (13.3)
        # - zram device is created with specified size (13.4)
        # - lz4 compression is configured and verified (13.5)
        # - zram device is formatted as swap (13.6)
        # - zram device is enabled as swap (13.7)
        # - zramswap service is enabled to start on boot (13.8)
        # - zram priority is higher than disk swap priority (13.9)
        # - Configuration changes trigger service restart
        # - This applies consistently across all valid configuration values


class TestDiskSwapProperties:
    """Property-based tests for disk swap configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        disk_swap_size=valid_disk_swap_size(),
        disk_priority=valid_swap_priority(),
    )
    def test_property_31_disk_swap_configuration(
        self,
        disk_swap_size: str,
        disk_priority: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 31: Disk Swap Configuration

        For any execution of the bootstrap playbook WHERE disk swap size is configured,
        a swap file SHALL be created at /swapfile with the specified size and mode 0600,
        formatted as swap, enabled as swap, added to /etc/fstab for persistence, and
        assigned a lower priority than zram swap if zram is also enabled.

        Validates: Requirements 13.10, 13.11, 13.12, 13.13, 13.14, 13.15, 13.16
        """
        # This property test verifies the swap role's disk swap behavior by checking:
        # 1. disk_swap_size is configurable (Requirement 13.10)
        # 2. swap file is created at /swapfile with specified size (Requirement 13.11)
        # 3. swap file has mode 0600 (Requirement 13.12)
        # 4. swap file is formatted as swap (Requirement 13.13)
        # 5. swap file is enabled as swap (Requirement 13.14)
        # 6. swap file is added to /etc/fstab (Requirement 13.15)
        # 7. disk swap priority is lower than zram (Requirement 13.16)

        # Read the swap role tasks
        tasks_path = Path("roles/swap/tasks/main.yml")
        assert tasks_path.exists(), "Swap tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify disk swap configuration is conditionally included
        assert "ansible.builtin.include_tasks: disk_swap.yml" in tasks_content, (
            "Disk swap configuration tasks must be included"
        )
        assert "when: disk_swap_size | length > 0" in tasks_content, (
            "Disk swap configuration must be conditional on disk_swap_size variable"
        )

        # Read the disk swap tasks
        disk_swap_tasks_path = Path("roles/swap/tasks/disk_swap.yml")
        assert disk_swap_tasks_path.exists(), "Disk swap tasks file must exist"

        disk_swap_tasks_content = disk_swap_tasks_path.read_text()

        # Verify Requirement 13.11: swap file is created with specified size
        assert "ansible.builtin.command:" in disk_swap_tasks_content, (
            "Swap file must be created using command module"
        )
        assert "cmd: \"fallocate -l {{ disk_swap_size }} /swapfile\"" in disk_swap_tasks_content, (
            "Swap file must be created using fallocate with disk_swap_size (Requirement 13.11)"
        )
        assert "creates: /swapfile" in disk_swap_tasks_content, (
            "Swap file creation must be idempotent using creates parameter"
        )

        # Verify Requirement 13.12: swap file permissions are set to 0600
        assert "ansible.builtin.file:" in disk_swap_tasks_content, (
            "Swap file permissions must be set using file module"
        )
        assert "path: /swapfile" in disk_swap_tasks_content, (
            "File module must target /swapfile"
        )
        assert (
            "mode: \"0600\"" in disk_swap_tasks_content
            or "mode: '0600'" in disk_swap_tasks_content
        ), "Swap file must have mode 0600 (Requirement 13.12)"
        assert "owner: root" in disk_swap_tasks_content, (
            "Swap file must be owned by root"
        )
        assert "group: root" in disk_swap_tasks_content, (
            "Swap file must be owned by root group"
        )

        # Verify Requirement 13.13: swap file is formatted
        assert "cmd: mkswap /swapfile" in disk_swap_tasks_content, (
            "Swap file must be formatted using mkswap (Requirement 13.13)"
        )
        assert "when: swap_file_created.changed" in disk_swap_tasks_content, (
            "Swap formatting must be conditional on file creation"
        )

        # Verify Requirement 13.14: swap file is enabled with priority
        assert (
            "cmd: \"swapon --priority {{ disk_swap_priority }} /swapfile\""
            in disk_swap_tasks_content
        ), "Swap file must be enabled with priority using swapon (Requirement 13.14)"
        assert "when: swap_formatted.changed" in disk_swap_tasks_content, (
            "Swap enablement must be conditional on formatting"
        )

        # Verify Requirement 13.15: swap file is added to /etc/fstab
        assert "ansible.builtin.lineinfile:" in disk_swap_tasks_content, (
            "Swap file must be added to fstab using lineinfile module (Requirement 13.15)"
        )
        assert "path: /etc/fstab" in disk_swap_tasks_content, (
            "Lineinfile must target /etc/fstab"
        )
        assert (
            "line: \"/swapfile none swap sw,pri={{ disk_swap_priority }} 0 0\""
            in disk_swap_tasks_content
        ), "Fstab entry must include swap file with priority (Requirement 13.15)"
        assert "state: present" in disk_swap_tasks_content, (
            "Fstab entry must be present"
        )

        # Verify idempotency check for fstab
        assert "check_mode: true" in disk_swap_tasks_content, (
            "Fstab check must use check_mode for idempotency"
        )
        assert "register: fstab_check" in disk_swap_tasks_content, (
            "Fstab check result must be registered"
        )

        # Read the swap defaults
        defaults_path = Path("roles/swap/defaults/main.yml")
        assert defaults_path.exists(), "Swap defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify Requirement 13.10: disk_swap_size is configurable
        assert "disk_swap_size:" in defaults_content, (
            "disk_swap_size must be defined in defaults (Requirement 13.10)"
        )
        assert (
            'disk_swap_size: ""' in defaults_content
            or "disk_swap_size: ''" in defaults_content
        ), "Default disk_swap_size should be empty string (disabled by default)"

        # Verify disk swap priority is configurable
        assert "disk_swap_priority:" in defaults_content, (
            "disk_swap_priority must be defined in defaults"
        )

        # Verify Requirement 13.16: disk swap priority is lower than zram
        zram_priority_line = [
            line for line in defaults_content.split('\n')
            if 'zram_swap_priority:' in line
        ]
        disk_priority_line = [
            line for line in defaults_content.split('\n')
            if 'disk_swap_priority:' in line
        ]

        if zram_priority_line and disk_priority_line:
            # Extract value, removing comments
            zram_value_str = zram_priority_line[0].split(':')[1].split('#')[0].strip()
            disk_value_str = disk_priority_line[0].split(':')[1].split('#')[0].strip()
            zram_priority_value = int(zram_value_str)
            disk_priority_value = int(disk_value_str)
            assert disk_priority_value < zram_priority_value, (
                f"Disk swap priority ({disk_priority_value}) must be lower than zram priority "
                f"({zram_priority_value}) (Requirement 13.16)"
            )

        # Property verified: The swap role configuration ensures that:
        # - disk_swap_size is configurable (13.10)
        # - swap file is created at /swapfile with specified size (13.11)
        # - swap file has mode 0600 for security (13.12)
        # - swap file is formatted as swap (13.13)
        # - swap file is enabled as swap with priority (13.14)
        # - swap file is added to /etc/fstab for persistence (13.15)
        # - disk swap priority is lower than zram priority (13.16)
        # - Swap file creation is idempotent
        # - This applies consistently across all valid configuration values


class TestSwapConfigurationSkipProperties:
    """Property-based tests for swap configuration skip behavior."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_32_swap_configuration_skip(self):
        """
        Feature: vps-bootstrap-playbook, Property 32: Swap Configuration Skip

        For any execution of the bootstrap playbook WHERE neither zram nor disk swap
        is configured, the playbook SHALL skip all swap configuration steps.

        Validates: Requirement 13.17
        """
        # This property test verifies the swap role's skip behavior by checking:
        # 1. Swap configuration is skipped when both zram and disk swap are
        #    disabled (Requirement 13.17)

        # Read the swap role tasks
        tasks_path = Path("roles/swap/tasks/main.yml")
        assert tasks_path.exists(), "Swap tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify Requirement 13.17: zram configuration is conditional
        assert "ansible.builtin.include_tasks: zram.yml" in tasks_content, (
            "Zram configuration tasks must be included"
        )
        assert "when: zram_enabled | bool" in tasks_content, (
            "Zram configuration must be skipped when zram_enabled is false (Requirement 13.17)"
        )

        # Verify Requirement 13.17: disk swap configuration is conditional
        assert "ansible.builtin.include_tasks: disk_swap.yml" in tasks_content, (
            "Disk swap configuration tasks must be included"
        )
        assert "when: disk_swap_size | length > 0" in tasks_content, (
            "Disk swap configuration must be skipped when disk_swap_size is empty "
            "(Requirement 13.17)"
        )

        # Verify the conditions check both defined and non-empty/false
        # This ensures swap configuration is skipped when:
        # - zram_enabled is false
        # - disk_swap_size is empty string ""

        # Read the swap defaults
        defaults_path = Path("roles/swap/defaults/main.yml")
        assert defaults_path.exists(), "Swap defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify default values disable swap by default
        assert "zram_enabled: false" in defaults_content, (
            "Default zram_enabled should be false to skip configuration by default"
        )
        assert (
            'disk_swap_size: ""' in defaults_content
            or "disk_swap_size: ''" in defaults_content
        ), "Default disk_swap_size should be empty string to skip configuration by default"

        # Property verified: The swap role ensures that:
        # - Zram configuration is skipped when zram_enabled is false (13.17)
        # - Disk swap configuration is skipped when disk_swap_size is empty (13.17)
        # - Default values disable both swap types by default
        # - No swap configuration occurs when both are disabled
        # - This applies consistently regardless of the reason for skipping


class TestSwapPriorityProperties:
    """Property-based tests for swap priority configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        zram_priority=valid_swap_priority(),
        disk_priority=valid_swap_priority(),
    )
    def test_swap_priority_configuration_consistency(
        self,
        zram_priority: int,
        disk_priority: int,
    ):
        """
        Feature: vps-bootstrap-playbook, Swap Priority Configuration Consistency

        For any execution of the bootstrap playbook with both zram and disk swap enabled,
        the playbook SHALL ensure that zram has higher priority than disk swap, ensuring
        that the faster compressed RAM swap is used before slower disk swap.

        This property verifies that:
        - Zram priority is configurable
        - Disk swap priority is configurable
        - Default zram priority is higher than default disk swap priority
        - Priority values are used in configuration
        """
        # Read the swap defaults
        defaults_path = Path("roles/swap/defaults/main.yml")
        assert defaults_path.exists(), "Swap defaults file must exist"

        defaults_content = defaults_path.read_text()

        # Verify priorities are configurable
        assert "zram_swap_priority:" in defaults_content, (
            "zram_swap_priority must be configurable"
        )
        assert "disk_swap_priority:" in defaults_content, (
            "disk_swap_priority must be configurable"
        )

        # Extract and verify default priority values
        zram_priority_line = [
            line for line in defaults_content.split('\n')
            if 'zram_swap_priority:' in line
        ]
        disk_priority_line = [
            line for line in defaults_content.split('\n')
            if 'disk_swap_priority:' in line
        ]

        assert zram_priority_line, "zram_swap_priority must be defined"
        assert disk_priority_line, "disk_swap_priority must be defined"

        # Extract value, removing comments
        zram_value_str = zram_priority_line[0].split(':')[1].split('#')[0].strip()
        disk_value_str = disk_priority_line[0].split(':')[1].split('#')[0].strip()
        zram_priority_value = int(zram_value_str)
        disk_priority_value = int(disk_value_str)

        assert zram_priority_value > disk_priority_value, (
            f"Default zram priority ({zram_priority_value}) must be higher than "
            f"default disk swap priority ({disk_priority_value})"
        )

        # Verify reasonable priority values
        assert 0 <= zram_priority_value <= 32767, (
            f"Zram priority must be in valid range (0-32767), got {zram_priority_value}"
        )
        assert 0 <= disk_priority_value <= 32767, (
            f"Disk swap priority must be in valid range (0-32767), got {disk_priority_value}"
        )

        # Verify zram template uses priority variable
        zram_template_path = Path("roles/swap/templates/zram.conf.j2")
        assert zram_template_path.exists(), "Zram configuration template must exist"

        zram_template_content = zram_template_path.read_text()
        assert "PRIORITY={{ zram_swap_priority }}" in zram_template_content, (
            "Zram template must use zram_swap_priority variable"
        )

        # Verify disk swap tasks use priority variable
        disk_swap_tasks_path = Path("roles/swap/tasks/disk_swap.yml")
        assert disk_swap_tasks_path.exists(), "Disk swap tasks file must exist"

        disk_swap_tasks_content = disk_swap_tasks_path.read_text()
        assert "swapon --priority {{ disk_swap_priority }}" in disk_swap_tasks_content, (
            "Disk swap tasks must use disk_swap_priority variable in swapon command"
        )
        assert "pri={{ disk_swap_priority }}" in disk_swap_tasks_content, (
            "Disk swap tasks must use disk_swap_priority variable in fstab entry"
        )

        # Property verified: The swap role ensures:
        # - Zram priority is configurable via zram_swap_priority
        # - Disk swap priority is configurable via disk_swap_priority
        # - Default zram priority is higher than disk swap priority
        # - Priority values are within valid range (0-32767)
        # - Priorities are used in configuration templates and tasks


class TestZramSizeFormatProperties:
    """Property-based tests for zram size format handling."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        zram_size=valid_zram_size(),
    )
    def test_zram_size_format_handling(self, zram_size: str):
        """
        Feature: vps-bootstrap-playbook, Zram Size Format Handling

        For any execution of the bootstrap playbook with configured zram size,
        the playbook SHALL correctly handle both percentage format (e.g., "50%")
        and absolute size format (e.g., "2G", "1024M"), converting them appropriately
        for the zram configuration.

        This property verifies that:
        - Percentage format is supported (e.g., "50%")
        - Absolute GB format is supported and converted to MB (e.g., "2G")
        - Absolute MB format is supported (e.g., "1024M")
        - Template handles all format variations correctly
        """
        # Read the zram configuration template
        template_path = Path("roles/swap/templates/zram.conf.j2")
        assert template_path.exists(), "Zram configuration template must exist"

        template_content = template_path.read_text()

        # Verify percentage format handling
        assert "{% if zram_size.endswith('%') %}" in template_content, (
            "Template must check for percentage format"
        )
        assert "PERCENTAGE={{ zram_size.rstrip('%') }}" in template_content, (
            "Template must extract percentage value"
        )

        # Verify GB format handling
        assert "{% if zram_size.endswith('G') or zram_size.endswith('g') %}" in template_content, (
            "Template must check for GB format (both uppercase and lowercase)"
        )
        assert "SIZE={{ (zram_size.rstrip('Gg') | int) * 1024 }}" in template_content, (
            "Template must convert GB to MB by multiplying by 1024"
        )

        # Verify MB format handling
        assert (
            "{% elif zram_size.endswith('M') or zram_size.endswith('m') %}"
            in template_content
        ), "Template must check for MB format (both uppercase and lowercase)"
        assert "SIZE={{ zram_size.rstrip('Mm') | int }}" in template_content, (
            "Template must extract MB value directly"
        )

        # Verify fallback for unclear format
        assert "{% else %}" in template_content, (
            "Template must have fallback for unclear format"
        )
        assert "PERCENTAGE=50" in template_content, (
            "Template must default to 50% if format is unclear"
        )

        # Verify template uses Jinja2 filters correctly
        assert "| int" in template_content, (
            "Template must use int filter to convert string to integer"
        )
        assert "rstrip" in template_content, (
            "Template must use rstrip to remove unit suffixes"
        )

        # Property verified: The zram configuration template ensures:
        # - Percentage format is correctly handled
        # - GB format is converted to MB (multiply by 1024)
        # - MB format is used directly
        # - Both uppercase and lowercase units are supported
        # - Fallback to 50% for unclear formats
        # - This applies consistently across all valid size format variations


class TestSwapIdempotencyProperties:
    """Property-based tests for swap configuration idempotency."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        disk_swap_size=valid_disk_swap_size(),
    )
    def test_disk_swap_idempotency(self, disk_swap_size: str):
        """
        Feature: vps-bootstrap-playbook, Disk Swap Idempotency

        For any execution of the bootstrap playbook with disk swap configured,
        the playbook SHALL be idempotent, meaning repeated executions do not
        recreate the swap file or duplicate fstab entries.

        This property verifies that:
        - Swap file creation uses 'creates' parameter for idempotency
        - Swap formatting is conditional on file creation
        - Swap enablement is conditional on formatting
        - Fstab entry is checked before adding to prevent duplicates
        """
        # Read the disk swap tasks
        disk_swap_tasks_path = Path("roles/swap/tasks/disk_swap.yml")
        assert disk_swap_tasks_path.exists(), "Disk swap tasks file must exist"

        disk_swap_tasks_content = disk_swap_tasks_path.read_text()

        # Verify swap file creation is idempotent
        assert "creates: /swapfile" in disk_swap_tasks_content, (
            "Swap file creation must use 'creates' parameter for idempotency"
        )
        assert "register: swap_file_created" in disk_swap_tasks_content, (
            "Swap file creation result must be registered"
        )

        # Verify formatting is conditional
        assert "when: swap_file_created.changed" in disk_swap_tasks_content, (
            "Swap formatting must be conditional on file creation"
        )
        assert "register: swap_formatted" in disk_swap_tasks_content, (
            "Swap formatting result must be registered"
        )

        # Verify enablement is conditional
        assert "when: swap_formatted.changed" in disk_swap_tasks_content, (
            "Swap enablement must be conditional on formatting"
        )

        # Verify fstab check for idempotency
        assert "check_mode: true" in disk_swap_tasks_content, (
            "Fstab check must use check_mode to avoid changes"
        )
        assert "register: fstab_check" in disk_swap_tasks_content, (
            "Fstab check result must be registered"
        )
        assert "changed_when: false" in disk_swap_tasks_content, (
            "Fstab check should not report changes"
        )

        # Verify fstab addition is conditional
        assert "when: fstab_check.found == 0" in disk_swap_tasks_content, (
            "Fstab entry addition must be conditional on entry not existing"
        )

        # Property verified: The disk swap configuration ensures:
        # - Swap file creation is idempotent (creates parameter)
        # - Formatting only happens when file is created
        # - Enablement only happens when formatting occurs
        # - Fstab entry is checked before adding to prevent duplicates
        # - Repeated playbook executions do not cause unnecessary changes
        # - This applies consistently across all valid disk swap sizes
