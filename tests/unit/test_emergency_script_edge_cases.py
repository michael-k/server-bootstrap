"""
Unit tests for emergency access script edge cases.

Tests the actual Jinja2 template by rendering it with test variables
and executing the resulting script to verify edge case behavior.

Tests cover:
- Script behavior with missing configuration files
- Service restart failures
- Idempotency in both modes

Requirements: EMRG-3, EMRG-4, EMRG-8, EMRG-9, EMRG-10, EMRG-13, EMRG-14.

Every test here replaces check_root with a no-op so the suite can run
unprivileged, so the script's root-privilege check is not exercised here. The fixtures are
hand-written miniatures of the files SSH and FW deploy, not those files.
"""

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit


@pytest.fixture
def jinja_env() -> Environment:
    """Create Jinja2 environment for rendering the template."""
    template_dir = Path(__file__).parent.parent.parent / "roles" / "emergency_access" / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)))


@pytest.fixture
def temp_test_dir() -> Generator[Path]:
    """Create a temporary directory for test execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_sshd_config(temp_test_dir: Path) -> Path:
    """Create a mock SSHD configuration file."""
    config_path = temp_test_dir / "sshd_config"
    config_content = """Port 22
ListenAddress 100.64.0.1
PasswordAuthentication no
PermitRootLogin no
"""
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def mock_nftables_config(temp_test_dir: Path) -> Path:
    """Create a mock NFTables configuration file."""
    config_path = temp_test_dir / "nftables.conf"
    config_content = """table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        iifname "tailscale0" tcp dport 22 accept
    }
}
"""
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def mock_systemctl_success(temp_test_dir: Path) -> Path:
    """Create a mock systemctl that always succeeds."""
    mock_path = temp_test_dir / "mock_systemctl"
    mock_content = """#!/bin/bash
exit 0
"""
    mock_path.write_text(mock_content)
    mock_path.chmod(0o755)
    return mock_path


@pytest.fixture
def mock_systemctl_failure(temp_test_dir: Path) -> Path:
    """Create a mock systemctl that always fails."""
    mock_path = temp_test_dir / "mock_systemctl"
    mock_content = """#!/bin/bash
exit 1
"""
    mock_path.write_text(mock_content)
    mock_path.chmod(0o755)
    return mock_path


@pytest.fixture
def rendered_script(
    jinja_env: Environment,
    temp_test_dir: Path,
    mock_sshd_config: Path,
    mock_nftables_config: Path,
    mock_systemctl_success: Path,
) -> Path:
    """Render the actual Jinja2 template with test variables."""
    template = jinja_env.get_template("emergency-ssh-access.sh.j2")

    # Render with test variables
    rendered = template.render(
        emergency_access_ssh_port="22",
        emergency_access_tailscale_interface="tailscale0",
        emergency_access_tailscale_ipv4="100.64.0.1",
    )

    # Replace systemctl with mock and config paths with test paths
    rendered = rendered.replace("systemctl", str(mock_systemctl_success))
    rendered = rendered.replace('SSHD_CONFIG="/etc/ssh/sshd_config"',
                               f'SSHD_CONFIG="{mock_sshd_config}"')
    rendered = rendered.replace('NFTABLES_CONFIG="/etc/nftables.conf"',
                               f'NFTABLES_CONFIG="{mock_nftables_config}"')

    # Disable root check for testing by making it a no-op function
    rendered = rendered.replace(
        """check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}""",
        """check_root() {
    # Root check disabled for testing
    return 0
}"""
    )

    # Write the rendered script
    script_path = temp_test_dir / "emergency-ssh-access.sh"
    script_path.write_text(rendered)
    script_path.chmod(0o755)

    return script_path


class TestMissingConfigurationFiles:
    """EMRG-13: the script refuses to act when either file is absent."""

    def test_missing_sshd_config(
        self, rendered_script: Path, mock_sshd_config: Path
    ):
        """Test that script exits with error when SSHD config is missing."""
        mock_sshd_config.unlink()

        result = subprocess.run(
            [str(rendered_script)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "SSH configuration file not found" in result.stdout

    def test_missing_nftables_config(
        self, rendered_script: Path, mock_nftables_config: Path
    ):
        """Test that script exits with error when NFTables config is missing."""
        mock_nftables_config.unlink()

        result = subprocess.run(
            [str(rendered_script)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "NFTables configuration file not found" in result.stdout

    def test_missing_both_configs(
        self,
        rendered_script: Path,
        mock_sshd_config: Path,
        mock_nftables_config: Path,
    ):
        """Test that script exits with error when both config files are missing."""
        mock_sshd_config.unlink()
        mock_nftables_config.unlink()

        result = subprocess.run(
            [str(rendered_script)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "SSH configuration file not found" in result.stdout


class TestServiceRestartFailures:
    """EMRG-8: a failed restart or reload stops the script non-zero."""

    def test_sshd_restart_failure_unrestrict(
        self,
        jinja_env: Environment,
        temp_test_dir: Path,
        mock_sshd_config: Path,
        mock_nftables_config: Path,
        mock_systemctl_failure: Path,
    ):
        """Test that script exits with error when SSHD restart fails during unrestrict."""
        # Render script with failing systemctl
        template = jinja_env.get_template("emergency-ssh-access.sh.j2")
        rendered = template.render(
            emergency_access_ssh_port="22",
            emergency_access_tailscale_interface="tailscale0",
            emergency_access_tailscale_ipv4="100.64.0.1",
        )
        rendered = rendered.replace("systemctl", str(mock_systemctl_failure))
        rendered = rendered.replace('SSHD_CONFIG="/etc/ssh/sshd_config"',
                                   f'SSHD_CONFIG="{mock_sshd_config}"')
        rendered = rendered.replace('NFTABLES_CONFIG="/etc/nftables.conf"',
                                   f'NFTABLES_CONFIG="{mock_nftables_config}"')
        rendered = rendered.replace(
            """check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}""",
            """check_root() {
    # Root check disabled for testing
    return 0
}"""
        )

        script_path = temp_test_dir / "emergency-ssh-access-fail.sh"
        script_path.write_text(rendered)
        script_path.chmod(0o755)

        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "Failed to restart SSH daemon" in result.stdout

    def test_nftables_reload_failure_unrestrict(
        self,
        jinja_env: Environment,
        temp_test_dir: Path,
        mock_sshd_config: Path,
        mock_nftables_config: Path,
    ):
        """Test that script exits with error when NFTables reload fails during unrestrict."""
        # Create a mock systemctl that succeeds for sshd but fails for nftables
        mock_systemctl = temp_test_dir / "mock_systemctl_selective"
        mock_content = """#!/bin/bash
if [[ "$2" == "sshd" ]]; then
    exit 0
else
    exit 1
fi
"""
        mock_systemctl.write_text(mock_content)
        mock_systemctl.chmod(0o755)

        # Render script with selective systemctl
        template = jinja_env.get_template("emergency-ssh-access.sh.j2")
        rendered = template.render(
            emergency_access_ssh_port="22",
            emergency_access_tailscale_interface="tailscale0",
            emergency_access_tailscale_ipv4="100.64.0.1",
        )
        rendered = rendered.replace("systemctl", str(mock_systemctl))
        rendered = rendered.replace('SSHD_CONFIG="/etc/ssh/sshd_config"',
                                   f'SSHD_CONFIG="{mock_sshd_config}"')
        rendered = rendered.replace('NFTABLES_CONFIG="/etc/nftables.conf"',
                                   f'NFTABLES_CONFIG="{mock_nftables_config}"')
        rendered = rendered.replace(
            """check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}""",
            """check_root() {
    # Root check disabled for testing
    return 0
}"""
        )

        script_path = temp_test_dir / "emergency-ssh-access-nft-fail.sh"
        script_path.write_text(rendered)
        script_path.chmod(0o755)

        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "Failed to reload NFTables rules" in result.stdout


class TestIdempotency:
    """EMRG-9: neither direction changes anything when already in state."""

    def test_unrestrict_idempotency(
        self,
        rendered_script: Path,
        mock_sshd_config: Path,
        mock_nftables_config: Path,
    ):
        """EMRG-3, EMRG-9: unrestrict reaches its target state, then no-ops."""
        # First run: should make changes
        result1 = subprocess.run(
            [str(rendered_script)],
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0
        assert "SUCCESS" in result1.stdout

        # Verify configuration changes
        sshd_content = mock_sshd_config.read_text()
        assert "ListenAddress 0.0.0.0" in sshd_content
        assert "ListenAddress ::" in sshd_content

        nftables_content = mock_nftables_config.read_text()
        assert 'tcp dport 22 accept' in nftables_content
        assert 'iifname "tailscale0" tcp dport 22 accept' not in nftables_content

        # Second run: should detect no changes needed
        result2 = subprocess.run(
            [str(rendered_script)],
            capture_output=True,
            text=True,
        )
        assert result2.returncode == 0
        assert "already unrestricted" in result2.stdout
        assert "No changes needed" in result2.stdout

    def test_restore_idempotency(
        self,
        rendered_script: Path,
        mock_sshd_config: Path,
        mock_nftables_config: Path,
    ):
        """EMRG-4, EMRG-9: restore reaches its target state, then no-ops."""
        # First unrestrict to change state
        subprocess.run([str(rendered_script)], capture_output=True)

        # First restore: should make changes
        result1 = subprocess.run(
            [str(rendered_script), "--restore"],
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0

        # Verify configuration is in restricted state
        sshd_content = mock_sshd_config.read_text()
        assert "ListenAddress 100.64.0.1" in sshd_content
        assert "ListenAddress 0.0.0.0" not in sshd_content

        nftables_content = mock_nftables_config.read_text()
        assert 'iifname "tailscale0" tcp dport 22 accept' in nftables_content

        # Second restore: should detect no changes needed
        result2 = subprocess.run(
            [str(rendered_script), "--restore"],
            capture_output=True,
            text=True,
        )
        assert result2.returncode == 0
        assert "already restricted" in result2.stdout
        assert "No changes needed" in result2.stdout

    def test_alternating_modes_idempotency(
        self,
        rendered_script: Path,
        mock_sshd_config: Path,
        mock_nftables_config: Path,
    ):
        """EMRG-9: alternating the two directions does not diverge."""
        # Run unrestrict
        result1 = subprocess.run([str(rendered_script)], capture_output=True, text=True)
        assert result1.returncode == 0

        # Run unrestrict again (should be idempotent)
        result2 = subprocess.run([str(rendered_script)], capture_output=True, text=True)
        assert result2.returncode == 0
        assert "already unrestricted" in result2.stdout

        # Run restore
        result3 = subprocess.run(
            [str(rendered_script), "--restore"], capture_output=True, text=True
        )
        assert result3.returncode == 0

        # Run restore again (should be idempotent)
        result4 = subprocess.run(
            [str(rendered_script), "--restore"], capture_output=True, text=True
        )
        assert result4.returncode == 0
        assert "already restricted" in result4.stdout

        # Run unrestrict again
        result5 = subprocess.run([str(rendered_script)], capture_output=True, text=True)
        assert result5.returncode == 0

        # Verify final state is unrestricted
        sshd_content = mock_sshd_config.read_text()
        assert "ListenAddress 0.0.0.0" in sshd_content


class TestConfigurationBackups:
    """EMRG-10: both files are copied before any change, and only then."""

    def test_backup_created_on_unrestrict(
        self,
        rendered_script: Path,
        temp_test_dir: Path,
    ):
        """Test that backup files are created when unrestricting."""
        result = subprocess.run([str(rendered_script)], capture_output=True, text=True)
        assert result.returncode == 0

        # Check that backup files were created
        backup_files = list(temp_test_dir.glob("*.backup.*"))
        assert len(backup_files) >= 2

    def test_no_backup_on_idempotent_run(
        self,
        rendered_script: Path,
        temp_test_dir: Path,
    ):
        """EMRG-9, EMRG-10: an idempotent run takes no backup."""
        # First run to establish state
        subprocess.run([str(rendered_script)], capture_output=True)

        # Count existing backups
        initial_backups = len(list(temp_test_dir.glob("*.backup.*")))

        # Second run (idempotent)
        result = subprocess.run([str(rendered_script)], capture_output=True, text=True)
        assert result.returncode == 0
        assert "already unrestricted" in result.stdout

        # Verify no new backups were created
        final_backups = len(list(temp_test_dir.glob("*.backup.*")))
        assert final_backups == initial_backups


class TestInvalidArguments:
    """EMRG-14: anything but no arguments or exactly --restore is refused."""

    def test_invalid_argument(self, rendered_script: Path):
        """Test that script exits with error for invalid arguments."""
        result = subprocess.run(
            [str(rendered_script), "--invalid"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "Invalid arguments" in result.stdout
        assert "Usage:" in result.stdout

    def test_multiple_arguments(self, rendered_script: Path):
        """Test that script exits with error for multiple arguments."""
        result = subprocess.run(
            [str(rendered_script), "--restore", "--extra"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "Invalid arguments" in result.stdout
