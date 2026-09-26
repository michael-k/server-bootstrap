"""
Property-based tests for login policy hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the login policy templates
and the users role tasks that deploy login hardening.

Requirements: LOGIN-1, LOGIN-2, LOGIN-3, LOGIN-4, LOGIN-5, LOGIN-6, LOGIN-7,
LOGIN-8, LOGIN-9
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
        Defaults Define TMOUT

        Checks that the users role defaults define `login_policy_tmout`.

        Validates: LOGIN-5
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
        Defaults Define UMASK

        Checks that the users role defaults define `login_policy_umask`.

        Validates: LOGIN-7
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
        Defaults Define Login Retries

        Checks that the users role defaults define `login_policy_retries`.

        Validates: LOGIN-8
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
        Defaults Define Login Timeout

        Checks that the users role defaults define `login_policy_timeout`.

        Validates: LOGIN-9
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
        Shell Timeout Sets TMOUT

        Checks that the shell timeout template sets `TMOUT=` and references
        `login_policy_tmout`.

        Validates: LOGIN-5
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
        Shell Timeout Is Readonly

        Checks that the shell timeout template contains `readonly TMOUT`. That
        stops the shell that sourced it from reassigning or unsetting it later in
        the same session — advisory, not a guarantee that no shell ever runs
        without the timeout (see the login-policy design's Key decisions for what
        readonly does not cover).

        Validates: LOGIN-6
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
        Shell Timeout Is Exported

        Checks that the shell timeout template contains `export TMOUT`.

        Validates: LOGIN-5
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
        Securetty Virtual Console TTYs

        Checks that the securetty template lists the drawn TTY, one of tty1 to
        tty6, on a line of its own.

        Validates: LOGIN-4
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
        Securetty Serial Console TTYs

        Checks that the securetty template lists the drawn serial TTY, ttyS0 or
        ttyS1, on a line of its own.

        Validates: LOGIN-4
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
        Securetty No Pseudo-Terminals

        Checks that the securetty template contains no `pts/` entry.

        Validates: LOGIN-4
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
        login.defs Hardened Settings

        Checks that the login.defs template contains the drawn setting (`UMASK`,
        `LOGIN_RETRIES` or `LOGIN_TIMEOUT`) and the variable it is rendered from.

        Validates: LOGIN-7, LOGIN-8, LOGIN-9
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
        login.defs Successful Login Logging

        Checks that the login.defs template has an uncommented `LOG_OK_LOGINS`
        line set to yes.

        Validates: LOGIN-2
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
        login.defs Preserves UID Ranges

        Checks that the login.defs template mentions `UID_MIN`, `UID_MAX`, `1000`
        and `60000`, Debian's default UID range.

        Validates: LOGIN-1
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
        login.defs Preserves Encryption

        Checks that the login.defs template mentions `ENCRYPT_METHOD` and
        `YESCRYPT`, Debian's default.

        Validates: LOGIN-1
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
        login.defs Preserves HOME_MODE

        Checks that the login.defs template mentions `HOME_MODE` and `0700`.

        Validates: LOGIN-1
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "HOME_MODE" in content, "login.defs must define HOME_MODE"
        assert "0700" in content, "HOME_MODE must be 0700"


class TestLoginPolicyTasksProperties:
    """Property-based tests for login policy deployment tasks."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_login_defs(self):
        """
        Tasks Deploy login.defs

        Checks that the users role tasks deploy `login.defs.j2` to
        `/etc/login.defs`.

        Validates: LOGIN-1
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        assert tasks_path.exists(), "Users tasks must exist"

        content = tasks_path.read_text()

        assert "login.defs.j2" in content, (
            "Tasks must reference login.defs.j2 template"
        )
        assert "dest: /etc/login.defs" in content, (
            "Tasks must deploy to /etc/login.defs"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_securetty(self):
        """
        Tasks Deploy securetty

        Checks that the users role tasks deploy `securetty.j2` to `/etc/securetty`.

        Validates: LOGIN-4
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "securetty.j2" in content, (
            "Tasks must reference securetty.j2 template"
        )
        assert "dest: /etc/securetty" in content, (
            "Tasks must deploy to /etc/securetty"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_shell_timeout(self):
        """
        Tasks Deploy Shell Timeout

        Checks that the users role tasks deploy `shell-timeout.sh.j2` to
        `/etc/profile.d/shell-timeout.sh`.

        Validates: LOGIN-5
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "shell-timeout.sh.j2" in content, (
            "Tasks must reference shell-timeout.sh.j2 template"
        )
        assert "dest: /etc/profile.d/shell-timeout.sh" in content, (
            "Tasks must deploy to /etc/profile.d/shell-timeout.sh"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_ensure_pam_securetty(self):
        """
        Tasks Ensure pam_securetty

        Checks that the users role tasks edit `/etc/pam.d/login` with lineinfile
        and mention `pam_securetty`.

        Validates: LOGIN-3
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "pam_securetty" in content, (
            "Tasks must reference pam_securetty.so"
        )
        assert "/etc/pam.d/login" in content, (
            "Tasks must target /etc/pam.d/login"
        )
        assert "ansible.builtin.lineinfile:" in content, (
            "Tasks must use lineinfile module for pam_securetty"
        )
