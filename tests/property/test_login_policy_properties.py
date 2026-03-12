"""
Property-based tests for login policy hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the login policy templates
and the users role tasks that deploy login hardening.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


class TestLoginPolicyDefaults:
    """Property-based tests for login policy default variables."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_tmout(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define TMOUT

        The users role defaults SHALL define login_policy_tmout.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        assert defaults_path.exists(), "Users defaults must exist"

        content = defaults_path.read_text()

        assert "login_policy_tmout:" in content, (
            "login_policy_tmout must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_umask(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define UMASK

        The users role defaults SHALL define login_policy_umask.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "login_policy_umask:" in content, (
            "login_policy_umask must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_retries(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Login Retries

        The users role defaults SHALL define login_policy_retries.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "login_policy_retries:" in content, (
            "login_policy_retries must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_timeout(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Login Timeout

        The users role defaults SHALL define login_policy_timeout.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "login_policy_timeout:" in content, (
            "login_policy_timeout must be defined in defaults"
        )


class TestShellTimeoutProperties:
    """Property-based tests for shell idle timeout configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_shell_timeout_sets_tmout_variable(self):
        """
        Feature: vps-bootstrap-playbook, Shell Timeout Sets TMOUT

        The shell timeout template SHALL set the TMOUT variable
        using the login_policy_tmout variable.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/shell-timeout.sh.j2")
        assert template_path.exists(), "Shell timeout template must exist"

        content = template_path.read_text()

        assert "TMOUT=" in content, "Template must set TMOUT"
        assert "login_policy_tmout" in content, (
            "TMOUT must use login_policy_tmout variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_shell_timeout_is_readonly(self):
        """
        Feature: vps-bootstrap-playbook, Shell Timeout Is Readonly

        The shell timeout template SHALL mark TMOUT as readonly
        to prevent users from disabling the timeout.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/shell-timeout.sh.j2")
        content = template_path.read_text()

        assert "readonly TMOUT" in content, (
            "TMOUT must be marked readonly"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_shell_timeout_is_exported(self):
        """
        Feature: vps-bootstrap-playbook, Shell Timeout Is Exported

        The shell timeout template SHALL export TMOUT so it applies
        to child shells.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/shell-timeout.sh.j2")
        content = template_path.read_text()

        assert "export TMOUT" in content, (
            "TMOUT must be exported"
        )


@st.composite
def virtual_console_tty(draw):
    """Generate one of the expected virtual console TTYs."""
    return draw(st.sampled_from(["tty1", "tty2", "tty3", "tty4", "tty5", "tty6"]))


@st.composite
def serial_console_tty(draw):
    """Generate one of the expected serial console TTYs."""
    return draw(st.sampled_from(["ttyS0", "ttyS1"]))


class TestSecurettyProperties:
    """Property-based tests for console TTY restrictions."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tty=virtual_console_tty(),
    )
    def test_securetty_lists_virtual_console_ttys(
        self,
        tty: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Securetty Virtual Console TTYs

        The securetty template SHALL list tty1 through tty6
        for KVM/physical console access.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/securetty.j2")
        assert template_path.exists(), "Securetty template must exist"

        content = template_path.read_text()

        # Check for the TTY as a whole line (not substring of another word)
        lines = [line.strip() for line in content.split("\n")]
        assert tty in lines, (
            f"Securetty must list {tty} for virtual console access"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tty=serial_console_tty(),
    )
    def test_securetty_lists_serial_console_ttys(
        self,
        tty: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Securetty Serial Console TTYs

        The securetty template SHALL list ttyS0 and ttyS1
        for serial console access.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/securetty.j2")
        content = template_path.read_text()

        lines = [line.strip() for line in content.split("\n")]
        assert tty in lines, (
            f"Securetty must list {tty} for serial console access"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_securetty_does_not_list_pseudo_terminals(self):
        """
        Feature: vps-bootstrap-playbook, Securetty No Pseudo-Terminals

        The securetty template SHALL NOT contain pts/ entries.
        Root should not be able to log in via pseudo-terminals.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/securetty.j2")
        content = template_path.read_text()

        assert "pts/" not in content, (
            "Securetty must NOT list pseudo-terminal entries (pts/)"
        )


@st.composite
def hardened_login_defs_setting(draw):
    """Generate one of the hardened login.defs settings with expected values."""
    return draw(
        st.sampled_from(
            [
                ("UMASK", "login_policy_umask"),
                ("LOGIN_RETRIES", "login_policy_retries"),
                ("LOGIN_TIMEOUT", "login_policy_timeout"),
            ]
        )
    )


class TestLoginDefsProperties:
    """Property-based tests for /etc/login.defs template."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        setting=hardened_login_defs_setting(),
    )
    def test_login_defs_has_hardened_settings(
        self,
        setting: tuple,
    ):
        """
        Feature: vps-bootstrap-playbook, login.defs Hardened Settings

        The login.defs template SHALL contain all hardened settings
        using their corresponding configurable variables.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        assert template_path.exists(), "login.defs template must exist"

        content = template_path.read_text()

        setting_name, variable_name = setting
        assert setting_name in content, (
            f"login.defs must contain {setting_name}"
        )
        assert variable_name in content, (
            f"{setting_name} must use {variable_name} variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_enables_ok_login_logging(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Successful Login Logging

        The login.defs template SHALL set LOG_OK_LOGINS to yes
        to log successful console logins.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        # Find the LOG_OK_LOGINS line (not commented)
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("LOG_OK_LOGINS") and not stripped.startswith("#"):
                assert "yes" in stripped, (
                    "LOG_OK_LOGINS must be set to yes"
                )
                return
        pytest.fail("login.defs must contain an uncommented LOG_OK_LOGINS directive")

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_preserves_uid_ranges(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Preserves UID Ranges

        The login.defs template SHALL preserve Debian's default UID
        ranges (UID_MIN 1000, UID_MAX 60000) to avoid breaking user creation.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "UID_MIN" in content, "login.defs must define UID_MIN"
        assert "UID_MAX" in content, "login.defs must define UID_MAX"
        assert "1000" in content, "UID_MIN must be 1000"
        assert "60000" in content, "UID_MAX must be 60000"

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_preserves_encrypt_method(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Preserves Encryption

        The login.defs template SHALL preserve ENCRYPT_METHOD YESCRYPT
        to maintain password hashing compatibility.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "ENCRYPT_METHOD" in content, (
            "login.defs must define ENCRYPT_METHOD"
        )
        assert "YESCRYPT" in content, (
            "ENCRYPT_METHOD must be YESCRYPT"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_preserves_home_mode(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Preserves HOME_MODE

        The login.defs template SHALL preserve HOME_MODE 0700
        for secure home directory permissions.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "HOME_MODE" in content, "login.defs must define HOME_MODE"
        assert "0700" in content, "HOME_MODE must be 0700"
