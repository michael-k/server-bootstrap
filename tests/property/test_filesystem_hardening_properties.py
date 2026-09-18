"""
Property-based tests for filesystem hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the filesystem_hardening role
which mounts /tmp, /dev/shm, and /var/tmp with noexec, nosuid, nodev options.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# Strategies for generating mount-related test data
@st.composite
def required_mount_option(draw):
    """Generate one of the required security mount options."""
    return draw(st.sampled_from(["noexec", "nosuid", "nodev"]))


@st.composite
def hardened_mountpoint(draw):
    """Generate one of the three hardened mountpoints."""
    return draw(st.sampled_from(["/tmp", "/dev/shm", "/var/tmp"]))


class TestFilesystemHardeningProperties:
    """Property-based tests for filesystem mount hardening."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_tmp_mount_has_required_options(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, /tmp Mount Hardening

        For any execution of the bootstrap playbook, /tmp SHALL be mounted
        with noexec, nosuid, and nodev options via a systemd bind-mount unit.

        Validates: FS-1
        """
        template_path = Path("roles/filesystem_hardening/templates/tmp.mount.j2")
        assert template_path.exists(), "tmp.mount.j2 template must exist"

        content = template_path.read_text()

        # Verify required option is present in Options= line
        assert mount_option in content, (
            f"/tmp mount unit must include {mount_option} option"
        )

        # Verify it's a bind mount (not tmpfs — avoids RAM pressure)
        assert "Type=none" in content, "/tmp must use Type=none for bind mount"
        assert "bind" in content, "/tmp must use bind mount option"

        # Verify explicit rw
        assert "rw" in content, "/tmp mount options must explicitly include rw"

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_dev_shm_override_has_required_options(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, /dev/shm Mount Hardening

        For any execution of the bootstrap playbook, /dev/shm SHALL be mounted
        with noexec, nosuid, and nodev options via a systemd drop-in override.

        Validates: FS-3
        """
        template_path = Path(
            "roles/filesystem_hardening/templates/dev-shm.mount.conf.j2"
        )
        assert template_path.exists(), "dev-shm.mount.conf.j2 template must exist"

        content = template_path.read_text()

        # Verify required option is present
        assert mount_option in content, (
            f"/dev/shm drop-in must include {mount_option} option"
        )

        # Verify explicit rw (since drop-in replaces all options)
        assert "rw" in content, (
            "/dev/shm drop-in must explicitly include rw since Options= is a full replacement"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_var_tmp_mount_has_required_options(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, /var/tmp Mount Hardening

        For any execution of the bootstrap playbook, /var/tmp SHALL be mounted
        with noexec, nosuid, and nodev options as a bind-mount to /tmp.

        Validates: FS-2
        """
        template_path = Path("roles/filesystem_hardening/templates/var-tmp.mount.j2")
        assert template_path.exists(), "var-tmp.mount.j2 template must exist"

        content = template_path.read_text()

        # Verify required option is present
        assert mount_option in content, (
            f"/var/tmp mount unit must include {mount_option} option"
        )

        # Verify bind-mount to /tmp
        assert "What=/tmp" in content, "/var/tmp must bind-mount to /tmp"
        assert "Where=/var/tmp" in content, "/var/tmp must mount at /var/tmp"
        assert "Type=none" in content, "/var/tmp must use Type=none for bind mount"
        assert "bind" in content, "/var/tmp must use bind mount option"

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_var_tmp_depends_on_tmp_mount(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, /var/tmp Depends on /tmp

        For any execution of the bootstrap playbook, the var-tmp.mount unit
        SHALL declare a dependency on tmp.mount via After= and Requires=.

        Validates: FS-2
        """
        template_path = Path("roles/filesystem_hardening/templates/var-tmp.mount.j2")
        assert template_path.exists(), "var-tmp.mount.j2 template must exist"

        content = template_path.read_text()

        assert "After=tmp.mount" in content, (
            "var-tmp.mount must order After=tmp.mount"
        )
        assert "Requires=tmp.mount" in content, (
            "var-tmp.mount must declare Requires=tmp.mount"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mountpoint=hardened_mountpoint(),
    )
    def test_tasks_deploy_all_mount_units(
        self,
        mountpoint: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy All Mount Units

        For any execution of the bootstrap playbook, the filesystem_hardening
        tasks SHALL deploy systemd units for all three hardened mountpoints.

        Validates: FS-1, FS-2, FS-3, FS-4
        """
        tasks_path = Path("roles/filesystem_hardening/tasks/main.yml")
        assert tasks_path.exists(), "Tasks file must exist"

        tasks_content = tasks_path.read_text()

        # Verify template module is used
        assert "ansible.builtin.template:" in tasks_content, (
            "Mount units must be deployed using template module"
        )

        # Verify correct destinations
        if mountpoint == "/tmp":
            assert "dest: /etc/systemd/system/tmp.mount" in tasks_content, (
                "tmp.mount must be deployed to /etc/systemd/system/"
            )
        elif mountpoint == "/dev/shm":
            assert (
                "dest: /etc/systemd/system/dev-shm.mount.d/hardening.conf"
                in tasks_content
            ), "/dev/shm override must be deployed as drop-in conf"
        elif mountpoint == "/var/tmp":
            assert "dest: /etc/systemd/system/var-tmp.mount" in tasks_content, (
                "var-tmp.mount must be deployed to /etc/systemd/system/"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_no_default_dependencies_override(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, No DefaultDependencies Override

        For any execution of the bootstrap playbook, mount units SHALL NOT set
        DefaultDependencies=no, to preserve systemd's implicit boot ordering
        (After=sysinit.target) that ensures root FS is mounted rw first.

        Validates: FS-1, FS-2
        """
        for template_name in ["tmp.mount.j2", "var-tmp.mount.j2"]:
            template_path = Path(
                f"roles/filesystem_hardening/templates/{template_name}"
            )
            assert template_path.exists(), f"{template_name} must exist"

            content = template_path.read_text()
            assert "DefaultDependencies=no" not in content, (
                f"{template_name} must NOT set DefaultDependencies=no "
                "(would break boot ordering — root FS may not be rw yet)"
            )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_handler_triggers_daemon_reload(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Handler Triggers Daemon Reload

        For any execution of the bootstrap playbook, unit file changes SHALL
        trigger a systemd daemon-reload via the handler.

        Validates: FS-4
        """
        # Verify handler exists
        handler_path = Path("roles/filesystem_hardening/handlers/main.yml")
        assert handler_path.exists(), "Handlers file must exist"

        handler_content = handler_path.read_text()
        assert "daemon_reload: true" in handler_content, (
            "Handler must trigger daemon_reload"
        )

        # Verify tasks notify the handler
        tasks_path = Path("roles/filesystem_hardening/tasks/main.yml")
        tasks_content = tasks_path.read_text()
        assert "notify: Reload systemd daemon" in tasks_content, (
            "Template tasks must notify the Reload systemd daemon handler"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_dev_shm_is_dropin_not_full_unit(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, /dev/shm Uses Drop-in Override

        For any execution of the bootstrap playbook, /dev/shm hardening SHALL
        use a drop-in conf file (not a full unit replacement) to preserve the
        base unit's Type/What/Where while only changing Options.

        Validates: FS-3
        """
        tasks_path = Path("roles/filesystem_hardening/tasks/main.yml")
        tasks_content = tasks_path.read_text()

        # Must create the drop-in directory
        assert "dev-shm.mount.d" in tasks_content, (
            "Tasks must create the dev-shm.mount.d drop-in directory"
        )
        assert "state: directory" in tasks_content, (
            "Drop-in directory must be created with state: directory"
        )

        # Drop-in conf should only contain [Mount] Options, not full unit
        template_path = Path(
            "roles/filesystem_hardening/templates/dev-shm.mount.conf.j2"
        )
        content = template_path.read_text()

        assert "[Mount]" in content, "Drop-in must have [Mount] section"
        assert "[Unit]" not in content, (
            "Drop-in must NOT have [Unit] section (it's not a full unit)"
        )
        assert "[Install]" not in content, (
            "Drop-in must NOT have [Install] section (it's not a full unit)"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        mount_option=required_mount_option(),
    )
    def test_negative_missing_option_detected(
        self,
        mount_option: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Missing Option Detection

        Verify that the testing approach can detect a missing security option.
        If an options line does NOT contain a required option, the assertion fails.

        Validates: FS-1, FS-2, FS-3 (negative test)
        """
        # Simulate an options line missing one required option
        all_options = {"noexec", "nosuid", "nodev"}
        missing_one = all_options - {mount_option}
        bad_options_line = f"Options=bind,rw,{','.join(missing_one)}"

        # Verify our detection approach works
        assert mount_option not in bad_options_line, (
            f"Sanity check: {mount_option} should not be in '{bad_options_line}'"
        )

        # And verify a correct line passes
        good_options_line = f"Options=bind,rw,{','.join(all_options)}"
        assert mount_option in good_options_line, (
            f"Sanity check: {mount_option} should be in '{good_options_line}'"
        )
