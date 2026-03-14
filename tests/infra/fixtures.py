"""Pytest fixtures for Incus VM integration testing."""


import os
import shutil
import subprocess

import pytest

from tests.infra.ansible import run_bootstrap_playbook
from tests.infra.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from tests.infra.vm import IncusVM


def incus_available() -> bool:
    """Check if Incus CLI is available and daemon is running."""
    if not shutil.which("incus"):
        return False
    result = subprocess.run(
        ["incus", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _should_keep(request: pytest.FixtureRequest) -> bool:
    """Check if VMs should be preserved on failure."""
    if not os.environ.get("KEEP_VM_ON_FAIL"):
        return False
    # Check if any test in the session failed or errored
    failed = getattr(request.session, "testsfailed", 0)
    errored = getattr(request.session, "testserrors", 0)
    return (failed + errored) > 0


def print_debug_info(vm: IncusVM) -> None:
    """Print connection info for a preserved VM."""
    print(
        f"\nVM '{vm.name}' preserved for debugging.\n"
        f"  SSH: ssh -i {vm.ssh_key.private_key_path} root@{vm.ip_address}\n"
        f"  Cleanup: make vm-destroy VM={vm.name}\n"
    )


@pytest.fixture(scope="session")
def bootstrap_vm(request):
    """Fresh Debian VM with bootstrap playbook already applied.

    Session-scoped: shared across all tests that use this fixture.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM.create(image=image)
    try:
        vm.wait_ready()
        result = run_bootstrap_playbook(vm)
        if result.returncode != 0:
            raise RuntimeError(
                f"Bootstrap playbook failed on VM '{vm.name}'.\n"
                f"stdout: {result.stdout[-3000:]}\n"
                f"stderr: {result.stderr[-1000:]}"
            )
    except Exception:
        if os.environ.get("KEEP_VM_ON_FAIL"):
            print_debug_info(vm)
        else:
            vm.destroy()
        raise

    yield vm

    if _should_keep(request):
        print_debug_info(vm)
    else:
        vm.destroy()


@pytest.fixture(scope="session")
def swap_vm(request):
    """Fresh Debian VM with bootstrap applied and swap enabled (zram + disk).

    Session-scoped: shared across all swap integration tests.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM.create(image=image)
    try:
        vm.wait_ready()
        result = run_bootstrap_playbook(vm, extra_vars={
            "zram_enabled": True,
            "zram_size": "50%",
            "disk_swap_size": "512M",
        })
        if result.returncode != 0:
            raise RuntimeError(
                f"Bootstrap playbook (swap) failed on VM '{vm.name}'.\n"
                f"stdout: {result.stdout[-3000:]}\n"
                f"stderr: {result.stderr[-1000:]}"
            )
    except Exception:
        if os.environ.get("KEEP_VM_ON_FAIL"):
            print_debug_info(vm)
        else:
            vm.destroy()
        raise

    yield vm

    if _should_keep(request):
        print_debug_info(vm)
    else:
        vm.destroy()


@pytest.fixture(scope="session")
def clean_vm(request):
    """Fresh Debian VM without bootstrap applied.

    Session-scoped: shared across tests that need to control which roles run.
    """
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM.create(image=image)
    try:
        vm.wait_ready()
    except Exception:
        if os.environ.get("KEEP_VM_ON_FAIL"):
            print_debug_info(vm)
        else:
            vm.destroy()
        raise

    yield vm

    if _should_keep(request):
        print_debug_info(vm)
    else:
        vm.destroy()
