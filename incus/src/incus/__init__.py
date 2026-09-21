"""Incus VM lifecycle management for integration testing.

This package provides tools for launching and managing Incus VMs in
automated test suites.  It lives in the ``server-bootstrap`` repository and
is **not published to any index**: downstream projects install it as a dev
dependency by local path or by git URL (see README.md).  As of 2026-09-21 the
name ``incus`` on PyPI also belongs to an unrelated project, so ``uv add
incus`` does not fail -- it installs something else entirely.

:class:`IncusVM` is the one object a caller holds per machine: INCUS-2
launches it, INCUS-12 waits for it to accept SSH, INCUS-13 force-deletes it,
and INCUS-14 generates its name and access key.
INCUS-7: :class:`SSHKeyPair` is the throwaway keypair each machine gets --
one per machine unless the caller supplies its own.

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
    generated automatically.  Also :func:`ensure_base_image`, which builds
    and caches the pre-baked base image a raw Debian image is swapped for.

``incus.ssh``
    :class:`SSHKeyPair` — generate and clean up the ephemeral ed25519
    keypair used to reach a VM.

``incus.ansible``
    :func:`run_playbook` — run any Ansible playbook against a VM with
    auto-generated inventory and optional extra variables.

``incus.fixtures``
    Pytest fixtures (``clean_vm``) and helpers (``incus_available``)
    for integration tests.  Install with the ``[fixtures]`` extra.

``incus.constants``
    Name prefixes, the default image and the timeouts the rest of the
    package reads.  Four of its seven values are specific to
    ``server-bootstrap`` rather than generic; see specs/incus-tooling.

``incus.headscale``
    :class:`HeadscaleServer` — drives a headscale control server on a VM.
    Not part of this package's public API and deliberately absent from
    ``__all__``; import it directly if you need it.

``incus.__main__``
    The ``python -m incus`` command line: ``create``, ``list``, ``destroy``
    and ``ssh``, plus bootstrap-specific commands that appear only when the
    working directory holds a ``site.yml``.
"""

from incus.ssh import SSHKeyPair
from incus.vm import IncusVM

__all__ = ["IncusVM", "SSHKeyPair"]
