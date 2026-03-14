"""Pytest configuration for integration tests."""


import pytest

# Import fixtures so pytest discovers them
from tests.infra.fixtures import bootstrap_vm, clean_vm, swap_vm  # noqa: F401


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --debian-version CLI option."""
    parser.addoption(
        "--debian-version",
        action="store",
        default="13",
        help="Debian version for Incus VMs (default: 13, also: trixie, testing, sid)",
    )
