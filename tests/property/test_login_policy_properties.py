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
