"""
Property-based tests for sudo hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the sudo security defaults
template and the users role tasks that deploy sudo hardening.

Requirements: SUDO-4, SUDO-5, SUDO-6, SUDO-7, SUDO-8, SUDO-9, SUDO-10,
SUDO-11, SUDO-13
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


@st.composite
def sudo_security_directive(draw):
    """Generate one of the required sudo security directives."""
    return draw(
        st.sampled_from(
            ["env_reset", "secure_path", "use_pty", "log_year", "log_host"]
        )
    )


class TestSudoHardeningProperties:
    """Property-based tests for sudo hardening configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        directive=sudo_security_directive(),
    )
    def test_sudo_template_has_required_directives(
        self,
        directive: str,
    ):
        """
        Sudo Security Directives

        Checks that the sudo security template contains the drawn directive:
        `env_reset`, `secure_path`, `use_pty`, `log_year` or `log_host`.

        Validates: SUDO-5, SUDO-6, SUDO-8, SUDO-9
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        assert template_path.exists(), "Sudo security template must exist"

        content = template_path.read_text()

        assert directive in content, (
            f"Sudo security template must contain {directive} directive"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_sudo_template_has_secure_path(self):
        """
        Secure PATH

        Checks that the sudo security template names each of `/usr/local/sbin`,
        `/usr/local/bin`, `/usr/sbin`, `/usr/bin`, `/sbin` and `/bin`. It does not
        check that no other directory is on the path.

        Validates: SUDO-6
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        for directory in [
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
        ]:
            assert directory in content, f"secure_path must include {directory}"

    @pytest.mark.property
    @pytest.mark.unit
    def test_sudo_template_has_configurable_timeout(self):
        """
        Configurable Timeout

        Checks that the sudo security template references `sudo_timestamp_timeout`.

        Validates: SUDO-7
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        assert "sudo_timestamp_timeout" in content, (
            "Timeout must use sudo_timestamp_timeout variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_sudo_template_has_requiretty_with_exemption(self):
        """
        requiretty with Automation Account Exemption

        Checks that the sudo security template contains `requiretty` and
        `!requiretty`, and references `deploy_user_name`.

        Validates: SUDO-10
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        assert "requiretty" in content, "Template must contain requiretty directive"
        assert "!requiretty" in content, (
            "Template must exempt ansible user from requiretty"
        )
        assert "deploy_user_name" in content, (
            "TTY exemption must reference deploy_user_name variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_timeout(self):
        """
        Defaults Define Timeout

        Checks that the users role defaults define `sudo_timestamp_timeout`.

        Validates: SUDO-7
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        assert defaults_path.exists(), "Users defaults must exist"

        content = defaults_path.read_text()

        assert "sudo_timestamp_timeout:" in content, (
            "sudo_timestamp_timeout must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_create_wheel_group(self):
        """
        Tasks Create Wheel Group

        Checks that the users role tasks use the group module and mention `wheel`.

        Validates: SUDO-11
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        assert tasks_path.exists(), "Users tasks must exist"

        content = tasks_path.read_text()

        assert "wheel" in content, "Tasks must reference wheel group"
        assert "ansible.builtin.group:" in content, (
            "Tasks must use group module to create wheel"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_enable_pam_wheel(self):
        """
        Tasks Enable pam_wheel

        Checks that the users role tasks edit `/etc/pam.d/su` with lineinfile and
        mention `pam_wheel`.

        Validates: SUDO-13
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "pam_wheel" in content, (
            "Tasks must reference pam_wheel.so"
        )
        assert "/etc/pam.d/su" in content, (
            "Tasks must target /etc/pam.d/su"
        )
        assert "ansible.builtin.lineinfile:" in content, (
            "Tasks must use lineinfile module for pam_wheel"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_sudoers_with_validation(self):
        """
        Sudoers Deployed with Validation

        Checks that the users role tasks deploy `00-sudo-security` with the template
        module and mention `visudo`.

        Validates: SUDO-4
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "00-sudo-security" in content, (
            "Tasks must deploy 00-sudo-security file"
        )
        assert "visudo" in content, (
            "Sudoers file must be validated with visudo"
        )
        assert "ansible.builtin.template:" in content, (
            "Sudo security defaults must use template module"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_no_logfile_directive(self):
        """
        No logfile Directive

        Checks that no `Defaults` line in the sudo security template sets a
        `logfile`, so sudo keeps logging to syslog, which journald captures. It
        does not check that syslog logging works.

        Validates: SUDO-8
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("Defaults") and "logfile" in stripped:
                pytest.fail(
                    "Template must NOT contain a logfile directive — "
                    "sudo logs to syslog/journald by default"
                )
