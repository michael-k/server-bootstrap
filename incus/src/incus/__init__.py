"""Incus VM lifecycle management for integration testing.

This package provides tools for launching and managing Incus VMs in
automated test suites.  It is published from the ``server-bootstrap``
repository and meant to be installed as a dev dependency by downstream
projects.

Quick start::

    from incus.vm import IncusVM

    vm = IncusVM(image="bootstrap/open-13", ssh_port=2222, auto_launch=True)
    vm.wait_ready()

    result = vm.ssh("systemctl is-active nginx")
    assert result.returncode == 0

    vm.destroy()

Key modules:

``incus.vm``
    :class:`IncusVM` — launch, destroy, exec, SSH, port-knock, and
    transfer files to/from Incus VMs.  An ephemeral SSH keypair is
    generated automatically.

``incus.ansible``
    :func:`run_playbook` — run any Ansible playbook against a VM with
    auto-generated inventory and optional extra variables.

``incus.fixtures``
    Pytest fixtures (``clean_vm``) and helpers (``incus_available``)
    for integration tests.  Install with the ``[fixtures]`` extra.
"""

from incus.ssh import SSHKeyPair
from incus.vm import IncusVM

__all__ = ["IncusVM", "SSHKeyPair"]
