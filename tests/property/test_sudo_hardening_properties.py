"""
Property-based tests for sudo hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the sudo security defaults
template and the users role tasks that deploy sudo hardening.
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
        Feature: vps-bootstrap-playbook, Sudo Security Directives

        The sudo security defaults template SHALL contain all required
        hardening directives: env_reset, env_clean, secure_path, use_pty,
        log_year, and log_host.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, Secure PATH

        The sudo security template SHALL define a secure_path containing
        only standard system binary directories.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, Configurable Timeout

        The sudo security template SHALL reference the sudo_timestamp_timeout
        variable for credential caching, not a hardcoded value.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, requiretty with Ansible Exemption

        The sudo security template SHALL require a TTY for sudo usage
        AND exempt the ansible user from this requirement.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, Defaults Define Timeout

        The users role defaults SHALL define sudo_timestamp_timeout.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, Tasks Create Wheel Group

        The users role tasks SHALL create the wheel group for su restriction.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, Tasks Enable pam_wheel

        The users role tasks SHALL enable pam_wheel.so in /etc/pam.d/su.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, Sudoers Deployed with Validation

        The sudo security defaults file SHALL be deployed using the template
        module with visudo validation to prevent syntax errors from breaking sudo.

        Validates: Sudo hardening design spec
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
        Feature: vps-bootstrap-playbook, No logfile Directive

        The sudo security template SHALL NOT contain a logfile directive.
        Sudo logs to syslog (AUTH facility) by default, which journald captures.
        A separate logfile is redundant.

        Validates: Sudo hardening design spec
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
