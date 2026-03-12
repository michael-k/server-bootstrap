"""
Property-based tests for login policy hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the login policy templates
and the users role tasks that deploy login hardening.
"""

from pathlib import Path

import pytest


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
