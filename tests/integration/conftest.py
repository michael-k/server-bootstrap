"""Pytest configuration and bootstrap-specific fixtures for integration tests."""


import os

import pytest

from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from incus.fixtures import clean_vm, incus_available, print_debug_info  # noqa: F401
from incus.vm import IncusVM
from tests.integration.helpers import run_bootstrap_playbook


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --debian-version CLI option."""
    parser.addoption(
        "--debian-version",
        action="store",
        default="13",
        help="Debian version for Incus VMs (default: 13, also: trixie, testing, sid)",
    )


def _should_keep_vm(request: pytest.FixtureRequest) -> bool:
    """Check if VMs should be preserved on failure."""
    if not os.environ.get("KEEP_VM_ON_FAIL"):
        return False
    failed = getattr(request.session, "testsfailed", 0)
    errored = getattr(request.session, "testserrors", 0)
    return (failed + errored) > 0


@pytest.fixture(scope="class")
def isolated_vm(request):
    """Fresh Debian VM scoped to a single test class."""
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

    if _should_keep_vm(request):
        print_debug_info(vm)
    else:
        vm.destroy()


@pytest.fixture(scope="session")
def bootstrap_vm(request):
    """Fresh Debian VM with bootstrap playbook already applied."""
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM(image=image, auto_launch=True)
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

    if _should_keep_vm(request):
        print_debug_info(vm)
    else:
        vm.destroy()


@pytest.fixture(scope="session")
def swap_vm(request):
    """Fresh Debian VM with bootstrap applied and swap enabled."""
    if not incus_available():
        pytest.skip("Incus not available")

    version = request.config.getoption("--debian-version", DEFAULT_DEBIAN_VERSION)
    image = f"{IMAGE_PREFIX}{version}"

    vm = IncusVM(image=image, auto_launch=True)
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

    if _should_keep_vm(request):
        print_debug_info(vm)
    else:
        vm.destroy()
