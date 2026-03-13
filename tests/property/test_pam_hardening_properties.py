"""
Property-based tests for PAM hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the PAM hardening templates
and the users role tasks that deploy pam_faillock and pam_limits.
"""

from pathlib import Path

import pytest


class TestPamHardeningDefaults:
    """Property-based tests for PAM hardening default variables."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_faillock_deny(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Faillock Deny

        The users role defaults SHALL define pam_faillock_deny.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        assert defaults_path.exists(), "Users defaults must exist"

        content = defaults_path.read_text()

        assert "pam_faillock_deny:" in content, (
            "pam_faillock_deny must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_faillock_unlock_time(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Faillock Unlock Time

        The users role defaults SHALL define pam_faillock_unlock_time.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_faillock_unlock_time:" in content, (
            "pam_faillock_unlock_time must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_faillock_fail_interval(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Faillock Fail Interval

        The users role defaults SHALL define pam_faillock_fail_interval.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_faillock_fail_interval:" in content, (
            "pam_faillock_fail_interval must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nproc(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nproc

        The users role defaults SHALL define pam_limits_nproc.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nproc:" in content, (
            "pam_limits_nproc must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nproc_root(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nproc Root

        The users role defaults SHALL define pam_limits_nproc_root.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nproc_root:" in content, (
            "pam_limits_nproc_root must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nofile(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nofile

        The users role defaults SHALL define pam_limits_nofile.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nofile:" in content, (
            "pam_limits_nofile must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nofile_root(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nofile Root

        The users role defaults SHALL define pam_limits_nofile_root.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nofile_root:" in content, (
            "pam_limits_nofile_root must be defined in defaults"
        )
