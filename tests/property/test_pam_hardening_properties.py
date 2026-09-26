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
        Defaults Define Faillock Deny

        Checks that the users role defaults define `pam_faillock_deny`.

        Validates: PAM-2
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
        Defaults Define Faillock Unlock Time

        Checks that the users role defaults define `pam_faillock_unlock_time`.

        Validates: PAM-3
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
        Defaults Define Faillock Fail Interval

        Checks that the users role defaults define `pam_faillock_fail_interval`.

        Validates: PAM-4
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
        Defaults Define nproc Limit

        Checks that the users role defaults define `pam_limits_nproc`.

        Validates: PAM-10
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
        Defaults Define Root nproc Limit

        Checks that the users role defaults define `pam_limits_nproc_root`.

        Validates: PAM-11
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
        Defaults Define nofile Limit

        Checks that the users role defaults define `pam_limits_nofile`.

        Validates: PAM-12
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
        Defaults Define Root nofile Limit

        Checks that the users role defaults define `pam_limits_nofile_root`.

        Validates: PAM-13
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
        faillock.conf Configurable Settings

        Checks that the faillock.conf template contains the drawn setting
        (`deny`, `unlock_time` or `fail_interval`) and the variable it is rendered
        from.

        Validates: PAM-2, PAM-3, PAM-4
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
        faillock.conf Hardcodes even_deny_root

        Checks that the faillock.conf template has an uncommented `even_deny_root`
        line set to true. Root lockout is security policy, not configurable.

        Validates: PAM-5
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
        faillock.conf Root Unlock Time

        Checks that the faillock.conf template contains `root_unlock_time` and
        references `pam_faillock_unlock_time`.

        Validates: PAM-5
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
    """Property-based tests for faillock pam-auth-update profile templates.

    Faillock requires two pam-auth-update profiles because preauth must run
    before pam_unix (priority > 256) and authfail must run after it
    (priority < 256).  A single profile cannot wrap around another module.
    """

    @pytest.mark.property
    @pytest.mark.unit
    def test_preauth_profile_has_higher_priority_than_unix(self):
        """
        Preauth Profile Priority

        Checks that the preauth profile template sets `Priority: 512`, above
        pam_unix's 256, so it runs before password authentication.

        Validates: PAM-6
        """
        template_path = Path("roles/users/templates/faillock-preauth-pam-config.j2")
        assert template_path.exists(), "Faillock preauth profile template must exist"

        content = template_path.read_text()

        assert "Priority: 512" in content, (
            "Preauth profile must set Priority to 512"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_authfail_profile_has_lower_priority_than_unix(self):
        """
        Authfail Profile Priority

        Checks that the authfail profile template sets `Priority: 128`, below
        pam_unix's 256, so it runs after password authentication.

        Validates: PAM-7
        """
        template_path = Path("roles/users/templates/faillock-authfail-pam-config.j2")
        assert template_path.exists(), "Faillock authfail profile template must exist"

        content = template_path.read_text()

        assert "Priority: 128" in content, (
            "Authfail profile must set Priority to 128"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_preauth_profile_contains_preauth_directive(self):
        """
        Preauth Profile Directive

        Checks that the preauth profile template has `Auth-Type: Primary`, an
        `Auth-Initial:` section and a `preauth` directive.

        Validates: PAM-6
        """
        template_path = Path("roles/users/templates/faillock-preauth-pam-config.j2")
        content = template_path.read_text()

        assert "Auth-Type: Primary" in content, (
            "Preauth profile must have Auth-Type: Primary"
        )
        assert "preauth" in content, (
            "Preauth profile must contain preauth directive"
        )
        assert "Auth-Initial:" in content, (
            "Preauth profile must have Auth-Initial section"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_authfail_profile_contains_authfail_directive(self):
        """
        Authfail Profile Directive

        Checks that the authfail profile template has `Auth-Type: Primary`, an
        `Auth-Initial:` section and an `authfail` directive.

        Validates: PAM-7
        """
        template_path = Path("roles/users/templates/faillock-authfail-pam-config.j2")
        content = template_path.read_text()

        assert "Auth-Type: Primary" in content, (
            "Authfail profile must have Auth-Type: Primary"
        )
        assert "authfail" in content, (
            "Authfail profile must contain authfail directive"
        )
        assert "Auth-Initial:" in content, (
            "Authfail profile must have Auth-Initial section"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_authfail_profile_has_account_section(self):
        """
        Authfail Profile Account Section

        Checks that the authfail profile template has `Account-Type: Additional`
        and an `Account:` section, which reset the failure counter on successful
        login.

        Validates: PAM-17
        """
        template_path = Path("roles/users/templates/faillock-authfail-pam-config.j2")
        content = template_path.read_text()

        assert "Account-Type: Additional" in content, (
            "Authfail profile must have Account-Type: Additional"
        )
        assert "Account:" in content, (
            "Authfail profile must have Account section"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_both_profiles_set_default_yes(self):
        """
        Faillock Profiles Enabled by Default

        Checks that both faillock profile templates set `Default: yes`, so
        pam-auth-update enables them.

        Validates: PAM-6, PAM-7
        """
        for name in ("faillock-preauth-pam-config.j2", "faillock-authfail-pam-config.j2"):
            template_path = Path(f"roles/users/templates/{name}")
            content = template_path.read_text()

            assert "Default: yes" in content, (
                f"{name} must set Default: yes"
            )


@st.composite
def resource_limit_type(draw):
    """Generate one of the resource limit types."""
    return draw(st.sampled_from(["nproc", "nofile", "core"]))


class TestResourceLimitsProperties:
    """Property-based tests for resource limits template."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        limit_type=resource_limit_type(),
    )
    def test_limits_template_contains_all_limit_types(
        self,
        limit_type: str,
    ):
        """
        Resource Limits Types

        Checks that the resource limits template mentions the drawn limit type:
        `nproc`, `nofile` or `core`.

        Validates: PAM-10, PAM-11, PAM-12, PAM-13, PAM-14
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        assert template_path.exists(), "Resource limits template must exist"

        content = template_path.read_text()

        assert limit_type in content, (
            f"Resource limits must contain {limit_type} limit"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_hardcodes_core_zero(self):
        """
        Resource Limits Hardcode core to 0

        Checks that the first uncommented line of the resource limits template
        that mentions `core` contains `0`.

        Validates: PAM-14
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped.startswith("#") and "core" in stripped:
                assert "0" in stripped, (
                    "core limit must be set to 0"
                )
                return
        pytest.fail("Resource limits must contain an uncommented core limit line")

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_has_separate_root_nproc(self):
        """
        Resource Limits Separate Root nproc

        Checks that the resource limits template references both
        `pam_limits_nproc` and `pam_limits_nproc_root`.

        Validates: PAM-10, PAM-11
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        assert "pam_limits_nproc_root" in content, (
            "Resource limits must use pam_limits_nproc_root variable for root"
        )
        assert "pam_limits_nproc" in content, (
            "Resource limits must use pam_limits_nproc variable for regular users"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_has_separate_root_nofile(self):
        """
        Resource Limits Separate Root nofile

        Checks that the resource limits template references both
        `pam_limits_nofile` and `pam_limits_nofile_root`.

        Validates: PAM-12, PAM-13
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        assert "pam_limits_nofile_root" in content, (
            "Resource limits must use pam_limits_nofile_root variable for root"
        )
        assert "pam_limits_nofile" in content, (
            "Resource limits must use pam_limits_nofile variable for regular users"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_uses_hard_limits_only(self):
        """
        Resource Limits Hard Only

        Checks that every non-blank, uncommented line of the resource limits
        template says `hard` and none says `soft`.

        Validates: PAM-15
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                assert "hard" in stripped, (
                    f"All limit lines must use 'hard' type, got: {stripped}"
                )
                assert "soft" not in stripped, (
                    f"Limit lines must NOT use 'soft' type, got: {stripped}"
                )


class TestPamHardeningTasksProperties:
    """Property-based tests for PAM hardening deployment tasks."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_faillock_conf(self):
        """
        Tasks Deploy faillock.conf

        Checks that the users role tasks deploy `faillock.conf.j2` to
        `/etc/security/faillock.conf`.

        Validates: PAM-1
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        assert tasks_path.exists(), "Users tasks must exist"

        content = tasks_path.read_text()

        assert "faillock.conf.j2" in content, (
            "Tasks must reference faillock.conf.j2 template"
        )
        assert "dest: /etc/security/faillock.conf" in content, (
            "Tasks must deploy to /etc/security/faillock.conf"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_faillock_pam_profiles(self):
        """
        Tasks Deploy Faillock PAM Profiles

        Checks that the users role tasks deploy the preauth and authfail profile
        templates to `/usr/share/pam-configs/faillock-preauth` and
        `/usr/share/pam-configs/faillock-authfail`.

        Validates: PAM-6, PAM-7
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "faillock-preauth-pam-config.j2" in content, (
            "Tasks must reference faillock-preauth-pam-config.j2 template"
        )
        assert "dest: /usr/share/pam-configs/faillock-preauth" in content, (
            "Tasks must deploy to /usr/share/pam-configs/faillock-preauth"
        )
        assert "faillock-authfail-pam-config.j2" in content, (
            "Tasks must reference faillock-authfail-pam-config.j2 template"
        )
        assert "dest: /usr/share/pam-configs/faillock-authfail" in content, (
            "Tasks must deploy to /usr/share/pam-configs/faillock-authfail"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_enable_faillock_via_pam_auth_update(self):
        """
        Faillock Enabled via pam-auth-update

        Checks that the users role's tasks or handlers mention `pam-auth-update`.

        Validates: PAM-9
        """
        handlers_path = Path("roles/users/handlers/main.yml")
        tasks_path = Path("roles/users/tasks/main.yml")

        handlers_content = ""
        if handlers_path.exists():
            handlers_content = handlers_path.read_text()

        tasks_content = tasks_path.read_text()
        combined = handlers_content + tasks_content

        assert "pam-auth-update" in combined, (
            "Role must run pam-auth-update to enable faillock"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_resource_limits(self):
        """
        Tasks Deploy Resource Limits

        Checks that the users role tasks deploy `50-hardening.conf.j2` to
        `/etc/security/limits.d/50-hardening.conf`.

        Validates: PAM-16
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "50-hardening.conf.j2" in content, (
            "Tasks must reference 50-hardening.conf.j2 template"
        )
        assert "dest: /etc/security/limits.d/50-hardening.conf" in content, (
            "Tasks must deploy to /etc/security/limits.d/50-hardening.conf"
        )
