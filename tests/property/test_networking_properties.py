"""
Property-based tests for networking role in VPS Bootstrap Playbook.

These tests verify that the networking role correctly configures
static IPv6 via netplan when static_ipv6_address is set.
"""

from pathlib import Path

import pytest


class TestNetworkingDefaults:
    """Property-based tests for networking role default variables."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_static_ipv6_address(self):
        """
        The networking role defaults SHALL define static_ipv6_address
        as empty string (disabled by default).
        """
        defaults_path = Path("roles/networking/defaults/main.yml")
        assert defaults_path.exists(), "Networking defaults must exist"

        content = defaults_path.read_text()

        assert "static_ipv6_address:" in content, (
            "static_ipv6_address must be defined in defaults"
        )
        assert 'static_ipv6_address: ""' in content, (
            "static_ipv6_address must default to empty string"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_static_ipv6_gateway(self):
        """
        The networking role defaults SHALL define static_ipv6_gateway
        with a sensible default for IONOS VPS.
        """
        defaults_path = Path("roles/networking/defaults/main.yml")
        content = defaults_path.read_text()

        assert "static_ipv6_gateway:" in content, (
            "static_ipv6_gateway must be defined in defaults"
        )


class TestNetplanTemplateProperties:
    """Property-based tests for the netplan template."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_template_uses_dhcp4(self):
        """
        The netplan template SHALL enable DHCPv4.
        """
        template_path = Path("roles/networking/templates/50-cloud-init.yaml.j2")
        assert template_path.exists(), "Netplan template must exist"

        content = template_path.read_text()

        assert "dhcp4: true" in content, "Template must enable DHCPv4"

    @pytest.mark.property
    @pytest.mark.unit
    def test_template_uses_static_ipv6_address_variable(self):
        """
        The netplan template SHALL use the static_ipv6_address variable
        in the addresses list.
        """
        template_path = Path("roles/networking/templates/50-cloud-init.yaml.j2")
        content = template_path.read_text()

        assert "static_ipv6_address" in content, (
            "Template must reference static_ipv6_address variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_template_uses_static_ipv6_gateway_variable(self):
        """
        The netplan template SHALL use the static_ipv6_gateway variable
        for the default route.
        """
        template_path = Path("roles/networking/templates/50-cloud-init.yaml.j2")
        content = template_path.read_text()

        assert "static_ipv6_gateway" in content, (
            "Template must reference static_ipv6_gateway variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_template_matches_wired_interfaces(self):
        """
        The netplan template SHALL match wired ethernet interfaces (en*).
        """
        template_path = Path("roles/networking/templates/50-cloud-init.yaml.j2")
        content = template_path.read_text()

        assert 'name: "en*"' in content, "Template must match en* interfaces"


class TestNetworkingTaskProperties:
    """Property-based tests for networking role task structure."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_are_conditional_on_static_ipv6(self):
        """
        The networking role tasks SHALL only run when
        static_ipv6_address is set.
        """
        tasks_path = Path("roles/networking/tasks/main.yml")
        assert tasks_path.exists(), "Networking tasks must exist"

        content = tasks_path.read_text()

        assert "static_ipv6_address" in content, (
            "Tasks must be conditional on static_ipv6_address"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_netplan_config(self):
        """
        The networking role SHALL deploy the netplan template
        to /etc/netplan/.
        """
        tasks_path = Path("roles/networking/tasks/main.yml")
        content = tasks_path.read_text()

        assert "50-cloud-init.yaml.j2" in content, (
            "Tasks must reference the netplan template"
        )
        assert "/etc/netplan/" in content, (
            "Tasks must deploy to /etc/netplan/"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_use_handler_for_netplan_apply(self):
        """
        The networking role SHALL use a handler to run netplan apply
        when the config changes.
        """
        tasks_path = Path("roles/networking/tasks/main.yml")
        content = tasks_path.read_text()

        assert "notify: Apply netplan configuration" in content, (
            "Template deployment must notify handler"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_verify_ipv6_address(self):
        """
        The networking role SHALL verify that a global IPv6 address
        is assigned after configuration.
        """
        tasks_path = Path("roles/networking/tasks/main.yml")
        content = tasks_path.read_text()

        assert "Wait for public IPv6 address" in content, (
            "Tasks must wait for public IPv6 address"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_handler_runs_netplan_apply(self):
        """
        The networking handler SHALL run netplan apply.
        """
        handlers_path = Path("roles/networking/handlers/main.yml")
        assert handlers_path.exists(), "Networking handlers must exist"

        content = handlers_path.read_text()

        assert "netplan apply" in content, (
            "Handler must run netplan apply"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_netplan_config_has_restrictive_permissions(self):
        """
        The networking role SHALL deploy the netplan config with
        mode 0600 since it's a network configuration file.
        """
        tasks_path = Path("roles/networking/tasks/main.yml")
        content = tasks_path.read_text()

        assert '"0600"' in content or "'0600'" in content, (
            "Netplan config must have mode 0600"
        )


class TestNetworkingRoleOrderingProperties:
    """Property-based tests for networking role ordering in site.yml."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_networking_role_in_site_yml(self):
        """
        The networking role SHALL be listed in site.yml.
        """
        site_path = Path("site.yml")
        content = site_path.read_text()

        assert "role: networking" in content, (
            "networking role must be in site.yml"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_networking_role_runs_before_tailscale(self):
        """
        The networking role SHALL run before tailscale in site.yml
        so that IPv6 is configured before VPN setup.
        """
        site_path = Path("site.yml")
        content = site_path.read_text()

        networking_pos = content.index("role: networking")
        tailscale_pos = content.index("role: tailscale")

        assert networking_pos < tailscale_pos, (
            "networking role must run before tailscale"
        )
