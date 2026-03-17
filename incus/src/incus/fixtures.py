"""Pytest fixtures for Incus VM integration testing."""


import os
import shutil
import subprocess

import pytest

from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from incus.vm import IncusVM


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
    failed = getattr(request.session, "testsfailed", 0)
    errored = getattr(request.session, "testserrors", 0)
    return (failed + errored) > 0


def print_debug_info(vm: IncusVM) -> None:
    """Print connection info for a preserved VM."""
    print(
        f"\nVM '{vm.name}' preserved for debugging.\n"
        f"  SSH: ssh -i {vm.private_key_path} root@{vm.ip_address}\n"
        f"  Cleanup: make vm-destroy VM={vm.name}\n"
    )


@pytest.fixture(scope="session")
def clean_vm(request):
    """Fresh Debian VM without bootstrap applied."""
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM(image=image, auto_launch=True)
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
