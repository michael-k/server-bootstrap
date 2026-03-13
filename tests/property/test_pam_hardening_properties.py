"""
Property-based tests for PAM hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the PAM hardening templates
and the users role tasks that deploy pam_faillock and pam_limits.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


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


@st.composite
def faillock_configurable_setting(draw):
    """Generate one of the configurable faillock.conf settings."""
    return draw(
        st.sampled_from(
            [
                ("deny", "pam_faillock_deny"),
                ("unlock_time", "pam_faillock_unlock_time"),
                ("fail_interval", "pam_faillock_fail_interval"),
            ]
        )
    )


class TestFaillockConfProperties:
    """Property-based tests for faillock.conf template."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        setting=faillock_configurable_setting(),
    )
    def test_faillock_conf_has_configurable_settings(
        self,
        setting: tuple,
    ):
        """
        Feature: vps-bootstrap-playbook, faillock.conf Configurable Settings

        The faillock.conf template SHALL contain deny, unlock_time, and
        fail_interval using their corresponding configurable variables.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock.conf.j2")
        assert template_path.exists(), "faillock.conf template must exist"

        content = template_path.read_text()

        setting_name, variable_name = setting
        assert setting_name in content, (
            f"faillock.conf must contain {setting_name}"
        )
        assert variable_name in content, (
            f"{setting_name} must use {variable_name} variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_faillock_conf_hardcodes_even_deny_root(self):
        """
        Feature: vps-bootstrap-playbook, faillock.conf Even Deny Root

        The faillock.conf template SHALL hardcode even_deny_root = true.
        Root lockout is security policy, not configurable.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock.conf.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("even_deny_root") and not stripped.startswith("#"):
                assert "true" in stripped, (
                    "even_deny_root must be set to true"
                )
                return
        pytest.fail("faillock.conf must contain an uncommented even_deny_root directive")

    @pytest.mark.property
    @pytest.mark.unit
    def test_faillock_conf_has_root_unlock_time(self):
        """
        Feature: vps-bootstrap-playbook, faillock.conf Root Unlock Time

        The faillock.conf template SHALL set root_unlock_time using the
        pam_faillock_unlock_time variable (same as regular users).

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock.conf.j2")
        content = template_path.read_text()

        assert "root_unlock_time" in content, (
            "faillock.conf must contain root_unlock_time"
        )
        assert "pam_faillock_unlock_time" in content, (
            "root_unlock_time must use pam_faillock_unlock_time variable"
        )


class TestFaillockPamProfileProperties:
    """Property-based tests for faillock pam-auth-update profile template."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_has_correct_priority(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Priority

        The faillock PAM profile SHALL set Priority to 512 to place it
        after pam_unix (priority 256) in the PAM stack.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        assert template_path.exists(), "Faillock PAM profile template must exist"

        content = template_path.read_text()

        assert "Priority: 512" in content, (
            "PAM profile must set Priority to 512"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_has_auth_sections(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Auth Sections

        The faillock PAM profile SHALL contain Auth-Type Primary with
        preauth and Auth-Final with authfail sections.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        content = template_path.read_text()

        assert "Auth-Type: Primary" in content, (
            "PAM profile must have Auth-Type: Primary"
        )
        assert "preauth" in content, (
            "PAM profile must contain preauth directive"
        )
        assert "Auth-Final:" in content, (
            "PAM profile must have Auth-Final section"
        )
        assert "authfail" in content, (
            "PAM profile must contain authfail directive"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_has_account_section(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Account Section

        The faillock PAM profile SHALL contain an Account section to reset
        the failure counter on successful login.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        content = template_path.read_text()

        assert "Account-Type: Additional" in content, (
            "PAM profile must have Account-Type: Additional"
        )
        assert "Account:" in content, (
            "PAM profile must have Account section"
        )
        assert "pam_faillock.so" in content, (
            "PAM profile Account section must reference pam_faillock.so"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_sets_default_yes(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Default

        The faillock PAM profile SHALL set Default to yes so
        pam-auth-update enables it automatically.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        content = template_path.read_text()

        assert "Default: yes" in content, (
            "PAM profile must set Default: yes"
        )
