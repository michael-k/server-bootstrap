# Incus Package Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `incus/` into a proper Python package with src/ layout so other projects can install it as a dependency.

**Architecture:** Split `incus/` into generic shared code (VM lifecycle, SSH, playbook runner, fixtures) and bootstrap-specific code (test vars, bootstrap fixtures, image publishing). The generic code becomes an installable package; bootstrap-specific code moves to server-bootstrap's test tree.

**Tech Stack:** Python, uv (build backend), pytest, Ansible CLI

---

## Chunk 1: Package Structure and Generic Code

### Task 1: Restructure to src/ layout and create pyproject.toml

**Files:**
- Move: `incus/*.py` → `incus/src/incus/*.py`
- Create: `incus/pyproject.toml`

- [ ] **Step 1: Create src/ layout**

```bash
mkdir -p incus/src/incus
git mv incus/__init__.py incus/src/incus/
git mv incus/__main__.py incus/src/incus/
git mv incus/vm.py incus/src/incus/
git mv incus/ssh.py incus/src/incus/
git mv incus/ansible.py incus/src/incus/
git mv incus/constants.py incus/src/incus/
git mv incus/fixtures.py incus/src/incus/
git mv incus/headscale.py incus/src/incus/
```

- [ ] **Step 2: Create `incus/pyproject.toml`**

```toml
[project]
name = "incus"
version = "0.1.0"
description = "Incus VM lifecycle management for integration testing"
requires-python = ">=3.14"
dependencies = [
    "pyyaml>=6.0",
]

[project.optional-dependencies]
fixtures = ["pytest>=9.0"]

[build-system]
requires = ["uv>=0.10.10"]
build-backend = "uv"
```

- [ ] **Step 3: Update root `pyproject.toml` to add incus as editable dependency**

Add `"incus[fixtures]"` to the dev dependency group and add a `[tool.uv.sources]` section:

```toml
[dependency-groups]
dev = [
  {include-group = "lint"},
  {include-group = "test"},
  "incus[fixtures]",
]

[tool.uv.sources]
incus = { path = "incus", editable = true }
```

Keep `pythonpath = ["."]` in `[tool.pytest.ini_options]` — it's still needed so test files can import from `tests.integration.helpers`.

Update ruff per-file-ignores from `"incus/*"` to `"incus/src/incus/*"`:

```toml
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]  # Allow assert in tests
"incus/src/incus/*" = ["S101"]  # Allow assert in fixtures/infra code
```

- [ ] **Step 4: Update Makefile lint paths**

Change `python-lint` and `python-lint-fix` from `incus/` to `incus/src/`:

```makefile
python-lint:
	@echo "Checking Python code with ruff..."
	uv run ruff check tests/ incus/src/

python-lint-fix:
	@echo "Fixing Python code with ruff..."
	uv run ruff check --fix tests/ incus/src/
```

- [ ] **Step 5: Run `uv sync` to install the editable package**

```bash
uv sync
```

Expected: Resolves dependencies, installs incus package in editable mode.

- [ ] **Step 6: Run linting and unit tests**

Run: `make python-lint && make test-unit`
Expected: All pass (imports still resolve via installed package).

- [ ] **Step 7: Commit**

```bash
git add incus/ pyproject.toml Makefile uv.lock
git commit -m "refactor: restructure incus/ to src/ layout with pyproject.toml"
```

### Task 2: Refactor `ansible.py` to generic `run_playbook`

**Files:**
- Modify: `incus/src/incus/ansible.py`

- [ ] **Step 1: Replace `ansible.py` contents**

Replace the entire file. The key changes:
- Remove `WORKSPACE_ROOT`
- Remove `DEFAULT_TEST_VARS` import
- Rename `run_bootstrap_playbook` → `run_playbook` with generic signature
- Remove `run_verify_playbook` entirely
- Use `ansible-playbook` directly instead of `uv run ansible-playbook`
- Add `cwd` and `roles_path` parameters
- Remove `vm.ssh_port` mutation side-effect

```python
"""Ansible playbook execution helpers for Incus VM testing."""


import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from incus.vm import IncusVM


def build_inventory(vm: IncusVM, user: str = "root") -> str:
    """Generate a YAML inventory string pointing at the VM."""
    inventory = {
        "all": {
            "hosts": {
                "testvm": {
                    "ansible_host": vm.ip_address,
                    "ansible_user": user,
                    "ansible_port": vm.ssh_port,
                    "ansible_ssh_private_key_file": str(vm.ssh_key.private_key_path),
                    "ansible_ssh_common_args": (
                        "-o PubkeyAuthentication=yes "
                        "-o IdentitiesOnly=yes "
                        "-o StrictHostKeyChecking=no "
                        "-o UserKnownHostsFile=/dev/null"
                    ),
                }
            }
        }
    }
    return yaml.dump(inventory, default_flow_style=False)


def build_single_role_playbook(roles: str | list[str]) -> str:
    """Generate a minimal playbook YAML for testing specific roles."""
    if isinstance(roles, str):
        roles = [roles]

    playbook = [
        {
            "name": "Test single role",
            "hosts": "all",
            "become": True,
            "gather_facts": True,
            "roles": [{"role": r} for r in roles],
        }
    ]
    return yaml.dump(playbook, default_flow_style=False)


def _get_ssh_public_key_file(vm: IncusVM) -> Path:
    """Return the path to the VM's SSH public key file."""
    return vm.ssh_key.private_key_path.with_suffix(".pub")


def run_playbook(
    vm: IncusVM,
    playbook_path: str | Path,
    extra_vars: dict | None = None,
    roles: str | list[str] | None = None,
    check_mode: bool = False,
    user: str = "root",
    timeout: int = 600,
    cwd: str | Path | None = None,
    roles_path: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """Run an Ansible playbook against a VM.

    Args:
        vm: The target VM.
        playbook_path: Path to the playbook YAML file.
        extra_vars: Additional Ansible variables.
        roles: If provided, generate a temporary single-role playbook instead.
        check_mode: Run Ansible in check mode (--check).
        user: SSH user for the inventory.
        timeout: Subprocess timeout in seconds.
        cwd: Working directory for the ansible-playbook process.
        roles_path: Custom ANSIBLE_ROLES_PATH for single-role playbooks.
    """
    tmp_dir = tempfile.mkdtemp(prefix="incus-ansible-")
    tmp_path = Path(tmp_dir)

    inv_path = tmp_path / "inventory.yml"
    inv_path.write_text(build_inventory(vm, user=user))

    vars_path = None
    if extra_vars:
        vars_path = tmp_path / "extra_vars.json"
        vars_path.write_text(json.dumps(extra_vars))

    if roles:
        pb_path = tmp_path / "playbook.yml"
        pb_path.write_text(build_single_role_playbook(roles))
        actual_playbook = str(pb_path)
    else:
        actual_playbook = str(playbook_path)

    cmd = [
        "ansible-playbook",
        "-i", str(inv_path),
        actual_playbook,
    ]
    if extra_vars:
        cmd.extend(["-e", f"@{vars_path}"])
    if check_mode:
        cmd.append("--check")

    env = None
    if roles and roles_path:
        env = {**os.environ, "ANSIBLE_ROLES_PATH": str(roles_path)}

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            check=False,
            env=env,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: No errors on `incus/src/incus/ansible.py`. Test files will have import errors (expected — we fix those in Chunk 2).

- [ ] **Step 3: Commit**

```bash
git add incus/src/incus/ansible.py
git commit -m "refactor: replace run_bootstrap_playbook with generic run_playbook"
```

### Task 3: Clean up `constants.py`, `fixtures.py`, and `__init__.py`

**Files:**
- Modify: `incus/src/incus/constants.py`
- Modify: `incus/src/incus/fixtures.py`
- Modify: `incus/src/incus/__init__.py`

- [ ] **Step 1: Remove `DEFAULT_TEST_VARS` and image publishing constants from `constants.py`**

Replace with just the generic constants:

```python
"""Default constants for Incus VM testing."""


VM_NAME_PREFIX = "bootstrap-test-"

IMAGE_PREFIX = "images:debian/"

DEFAULT_DEBIAN_VERSION = "13"

VM_READY_TIMEOUT_SECONDS = 120

SSH_CONNECT_TIMEOUT_SECONDS = 10

SSH_POLL_INTERVAL_SECONDS = 2
```

- [ ] **Step 2: Remove `bootstrap_vm` and `swap_vm` from `fixtures.py`**

Replace with just the generic fixtures:

```python
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
        f"  SSH: ssh -i {vm.ssh_key.private_key_path} root@{vm.ip_address}\n"
        f"  Cleanup: make vm-destroy VM={vm.name}\n"
    )


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
```

- [ ] **Step 3: Update `__init__.py`**

Remove `HeadscaleServer` from exports:

```python
"""Incus VM lifecycle management for integration testing."""

from incus.ssh import SSHKeyPair
from incus.vm import IncusVM

__all__ = ["IncusVM", "SSHKeyPair"]
```

- [ ] **Step 4: Run linting**

Run: `make python-lint`
Expected: No errors on `incus/src/` files.

- [ ] **Step 5: Commit**

```bash
git add incus/src/incus/constants.py incus/src/incus/fixtures.py incus/src/incus/__init__.py
git commit -m "refactor: remove bootstrap-specific code from incus package"
```

### Task 4: Update `__main__.py` for guarded publish commands

**Files:**
- Modify: `incus/src/incus/__main__.py`

- [ ] **Step 1: Replace `__main__.py`**

Key changes:
- Remove `from incus.ansible import run_bootstrap_playbook`
- Remove imports of `IMAGE_ALIAS_PREFIX`, `IMAGE_VARIANTS`, `VM_STOP_TIMEOUT_SECONDS` from constants (they're now local)
- Add `from incus.ansible import run_playbook, _get_ssh_public_key_file`
- Define `_PUBLISH_VARS`, `IMAGE_ALIAS_PREFIX`, `IMAGE_VARIANTS`, `VM_STOP_TIMEOUT_SECONDS` locally
- `cmd_publish` calls `run_playbook` directly with merged vars
- Guard `publish` and `images-clean` behind `Path("site.yml").exists()`

```python
"""CLI entry point for Incus VM management.

Usage:
    uv run python -m incus create [--debian VERSION]
    uv run python -m incus list
    uv run python -m incus destroy <name>
    uv run python -m incus destroy --all
    uv run python -m incus ssh <name>

Bootstrap-specific (only available when site.yml exists):
    uv run python -m incus publish [--debian VERSION]
    uv run python -m incus images-clean
"""


import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from incus.ansible import _get_ssh_public_key_file, run_playbook
from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX, VM_NAME_PREFIX
from incus.vm import IncusVM

# --- Bootstrap-specific constants (only used by guarded commands) ---

_PUBLISH_VARS: dict[str, str | int | bool | list[int]] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    "manual_user_password": (
        "$6$testsalt$5P2FnhrAYcA6OcEmW5HOdQx2s/g5RDF/pjLq9r43iwy.jOyY9Ap0uReLp0zSd"
        "/WR6.609JYtDYaQVnBIlY3zG/"
    ),
    "manual_user_ssh_key_file": "",  # Set dynamically
    "deploy_user_name": "ansible",
    "deploy_user_ssh_key_file": "",  # Set dynamically
    "ssh_port": 22,
    "target_hostname": "bootstrap-test",
    "port_knocking_sequence": [7000, 8500, 9100],
    "tailscale_enabled": False,
    "swap_enabled": False,
    "login_policy_umask": "027",
    "login_policy_retries": 3,
    "login_policy_timeout": 30,
    "pam_faillock_deny": 5,
}

IMAGE_ALIAS_PREFIX = "bootstrap/"

IMAGE_VARIANTS: dict[str, dict[str, str | int | bool | list[int]]] = {
    "knocking": {
        "tailscale_enabled": False,
        "firewall_port_knocking_enabled": True,
    },
    "open": {
        "tailscale_enabled": False,
        "firewall_port_knocking_enabled": False,
    },
}

VM_STOP_TIMEOUT_SECONDS = 60


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new test VM."""
    image = f"{IMAGE_PREFIX}{args.debian}"
    print(f"Creating VM with image {image}...")
    vm = IncusVM.create(image=image)
    print(f"VM '{vm.name}' launched. Waiting for SSH...")
    vm.wait_ready()
    print(f"VM '{vm.name}' ready.")
    print(f"  IP: {vm.ip_address}")
    print(f"  SSH: ssh -i {vm.ssh_key.private_key_path} root@{vm.ip_address}")
    print(f"  Destroy: make vm-destroy VM={vm.name}")

    # Save VM info for vm-ssh to find later
    info_path = vm.ssh_key.private_key_path.parent / "vm-info.json"
    info_path.write_text(json.dumps({
        "name": vm.name,
        "ip_address": vm.ip_address,
        "ssh_key": str(vm.ssh_key.private_key_path),
    }))


def cmd_list(args: argparse.Namespace) -> None:
    """List running test VMs."""
    result = subprocess.run(
        ["incus", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    vms = json.loads(result.stdout)
    test_vms = [v for v in vms if v["name"].startswith(VM_NAME_PREFIX)]

    if not test_vms:
        print("No test VMs running.")
        return

    for vm in test_vms:
        status = vm.get("status", "Unknown")
        ip = ""
        network = vm.get("state", {}).get("network", {})
        for iface_name, iface in network.items():
            if iface_name == "lo":
                continue
            for addr in iface.get("addresses", []):
                if addr.get("family") == "inet" and addr.get("scope") == "global":
                    ip = addr["address"]
                    break
        print(f"  {vm['name']}  {status}  {ip}")


def cmd_destroy(args: argparse.Namespace) -> None:
    """Destroy test VM(s)."""
    if args.all:
        result = subprocess.run(
            ["incus", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
        )
        vms = json.loads(result.stdout)
        test_vms = [v for v in vms if v["name"].startswith(VM_NAME_PREFIX)]

        if not test_vms:
            print("No test VMs to destroy.")
            return

        for vm in test_vms:
            name = vm["name"]
            print(f"Destroying {name}...")
            subprocess.run(
                ["incus", "delete", name, "--force"],
                capture_output=True,
                text=True,
                check=False,
            )
        print(f"Destroyed {len(test_vms)} test VM(s).")
    else:
        if not args.name:
            print("Error: specify a VM name or use --all", file=sys.stderr)
            sys.exit(1)
        print(f"Destroying {args.name}...")
        subprocess.run(
            ["incus", "delete", args.name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"Destroyed {args.name}.")


def cmd_ssh(args: argparse.Namespace) -> None:
    """SSH into a test VM."""
    patterns = [
        os.path.join(tempfile.gettempdir(), f"bootstrap-test-{args.name}*", "vm-info.json"),
        os.path.join(tempfile.gettempdir(), f"bootstrap-test-*{args.name}*", "vm-info.json"),
    ]

    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            with open(matches[0]) as f:
                info = json.loads(f.read())
            os.execvp("ssh", [
                "ssh",
                "-o", "PubkeyAuthentication=yes",
                "-o", "StrictHostKeyChecking=no",
                "-i", info["ssh_key"],
                f"root@{info['ip_address']}",
            ])

    # Fallback: use incus exec (works even without saved SSH key)
    print(f"No saved SSH key found for '{args.name}'. Using incus exec instead.")
    os.execvp("incus", ["incus", "exec", args.name, "--", "/bin/bash"])


def _delete_image(alias: str) -> None:
    """Delete an Incus image by alias, if it exists."""
    result = subprocess.run(
        ["incus", "image", "delete", alias],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print(f"  Deleted existing image '{alias}'.")


def _stop_vm(name: str) -> None:
    """Stop a VM, falling back to --force if graceful stop hangs."""
    result = subprocess.run(
        ["incus", "stop", name, f"--timeout={VM_STOP_TIMEOUT_SECONDS}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("  Graceful stop failed, forcing...")
        subprocess.run(
            ["incus", "stop", name, "--force"],
            capture_output=True,
            text=True,
            check=True,
        )


def cmd_publish(args: argparse.Namespace) -> None:
    """Build and publish bootstrapped VM images."""
    version = args.debian

    for variant, variant_vars in IMAGE_VARIANTS.items():
        alias = f"{IMAGE_ALIAS_PREFIX}{variant}-{version}"
        print(f"Building image '{alias}'...")

        image = f"{IMAGE_PREFIX}{version}"
        vm = IncusVM.create(image=image, name_hint=f"publish-{variant}")
        try:
            print(f"  Waiting for VM '{vm.name}'...")
            vm.wait_ready()

            pub_key_path = _get_ssh_public_key_file(vm)
            merged_vars = dict(_PUBLISH_VARS)
            merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
            merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
            merged_vars.update(variant_vars)

            print("  Running bootstrap playbook...")
            result = run_playbook(
                vm,
                playbook_path=Path("site.yml"),
                extra_vars=merged_vars,
                cwd=Path.cwd(),
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Bootstrap failed for '{variant}'.\n"
                    f"stdout: {result.stdout[-3000:]}\n"
                    f"stderr: {result.stderr[-1000:]}"
                )

            print("  Stopping VM...")
            _stop_vm(vm.name)

            _delete_image(alias)

            print(f"  Publishing as '{alias}'...")
            subprocess.run(
                ["incus", "publish", vm.name, f"--alias={alias}"],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"  Published '{alias}'.")
        except Exception:
            print(f"  Error building '{variant}', cleaning up VM...")
            raise
        finally:
            subprocess.run(
                ["incus", "delete", vm.name, "--force"],
                capture_output=True,
                text=True,
                check=False,
            )
            vm.ssh_key.cleanup()

    print("All images published.")


def cmd_images_clean(args: argparse.Namespace) -> None:
    """Delete all bootstrap/* images from the local Incus store."""
    result = subprocess.run(
        ["incus", "image", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    images = json.loads(result.stdout)
    deleted = 0
    for img in images:
        for a in img.get("aliases", []):
            if a.get("name", "").startswith(IMAGE_ALIAS_PREFIX):
                subprocess.run(
                    ["incus", "image", "delete", img["fingerprint"]],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                print(f"  Deleted {a['name']}")
                deleted += 1
                break
    if deleted:
        print(f"Deleted {deleted} image(s).")
    else:
        print("No bootstrap images found.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Incus VMs for integration testing",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new test VM")
    p_create.add_argument(
        "--debian", default=DEFAULT_DEBIAN_VERSION,
        help=f"Debian version (default: {DEFAULT_DEBIAN_VERSION})",
    )

    # list
    subparsers.add_parser("list", help="List running test VMs")

    # destroy
    p_destroy = subparsers.add_parser("destroy", help="Destroy test VM(s)")
    p_destroy.add_argument("name", nargs="?", help="VM name to destroy")
    p_destroy.add_argument("--all", action="store_true", help="Destroy all test VMs")

    # ssh
    p_ssh = subparsers.add_parser("ssh", help="SSH into a test VM")
    p_ssh.add_argument("name", help="VM name")

    commands: dict[str, object] = {
        "create": cmd_create,
        "list": cmd_list,
        "destroy": cmd_destroy,
        "ssh": cmd_ssh,
    }

    # Bootstrap-specific commands — only available when site.yml exists
    if Path("site.yml").exists():
        p_publish = subparsers.add_parser(
            "publish", help="Build and publish bootstrapped VM images",
        )
        p_publish.add_argument(
            "--debian", default=DEFAULT_DEBIAN_VERSION,
            help=f"Debian version (default: {DEFAULT_DEBIAN_VERSION})",
        )
        subparsers.add_parser("images-clean", help="Delete all bootstrap/* images")
        commands["publish"] = cmd_publish
        commands["images-clean"] = cmd_images_clean

    args = parser.parse_args()
    commands[args.command](args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run linting**

Run: `make python-lint`
Expected: No errors on `incus/src/` files.

- [ ] **Step 3: Commit**

```bash
git add incus/src/incus/__main__.py
git commit -m "refactor: guard publish commands and use generic run_playbook"
```

## Chunk 2: Server-Bootstrap Integration

### Task 5: Move bootstrap-specific code to conftest and helpers

**Files:**
- Modify: `tests/integration/conftest.py`
- Create: `tests/integration/helpers.py`

The bootstrap-specific functions (`run_bootstrap_playbook`, `run_verify_playbook`, `DEFAULT_TEST_VARS`, `WORKSPACE_ROOT`) go into `tests/integration/helpers.py` — a regular module that can be imported by both conftest and test files. The fixtures (`bootstrap_vm`, `swap_vm`) stay in conftest since they must be there for pytest discovery.

Note: `conftest.py` is special to pytest and cannot be imported via `from tests.integration.conftest import ...` without `__init__.py` files. Using a separate `helpers.py` avoids this problem entirely.

- [ ] **Step 1: Create `tests/integration/helpers.py`**

This module contains the bootstrap-specific wrappers and constants.

```python
"""Bootstrap-specific playbook wrappers and test constants.

These are server-bootstrap specific and not part of the shared incus package.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from incus.ansible import _get_ssh_public_key_file, run_playbook
from incus.vm import IncusVM

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TEST_VARS: dict[str, str | int | bool | list[int]] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    # Generated with: openssl passwd -6 -salt testsalt 'TestPassword123!'
    "manual_user_password": (
        "$6$testsalt$5P2FnhrAYcA6OcEmW5HOdQx2s/g5RDF/pjLq9r43iwy.jOyY9Ap0uReLp0zSd"
        "/WR6.609JYtDYaQVnBIlY3zG/"
    ),
    "manual_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "deploy_user_name": "ansible",
    "deploy_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "ssh_port": 22,
    "target_hostname": "bootstrap-test",
    "port_knocking_sequence": [7000, 8500, 9100],
    "tailscale_enabled": False,
    "swap_enabled": False,
    # Login policy defaults (must match roles/users/defaults/main.yml)
    "login_policy_umask": "027",
    "login_policy_retries": 3,
    "login_policy_timeout": 30,
    # PAM hardening defaults (must match roles/users/defaults/main.yml)
    "pam_faillock_deny": 5,
}


def run_bootstrap_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    limit_to_role: str | list[str] | None = None,
    timeout: int = 600,
    check_mode: bool = False,
    user: str = "root",
) -> subprocess.CompletedProcess:
    """Run site.yml (or a single role) against the VM."""
    pub_key_path = _get_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    result = run_playbook(
        vm,
        playbook_path=WORKSPACE_ROOT / "site.yml",
        extra_vars=merged_vars,
        roles=limit_to_role,
        check_mode=check_mode,
        user=user,
        timeout=timeout,
        cwd=WORKSPACE_ROOT,
        roles_path=WORKSPACE_ROOT / "roles",
    )

    # Update the VM's SSH port to match what the playbook configured
    if result.returncode == 0:
        ssh_port = merged_vars.get("ssh_port", 22)
        vm.ssh_port = ssh_port if isinstance(ssh_port, int) else int(ssh_port)  # type: ignore[arg-type]

    return result


def run_verify_playbook(
    vm: IncusVM,
    extra_vars: dict | None = None,
    timeout: int = 300,
    user: str = "ansible",
) -> subprocess.CompletedProcess:
    """Run verify_bootstrap.yml against the VM."""
    pub_key_path = _get_ssh_public_key_file(vm)

    merged_vars = dict(DEFAULT_TEST_VARS)
    merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
    merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
    if extra_vars:
        merged_vars.update(extra_vars)

    return run_playbook(
        vm,
        playbook_path=WORKSPACE_ROOT / "tests" / "verify_bootstrap.yml",
        extra_vars=merged_vars,
        user=user,
        timeout=timeout,
        cwd=WORKSPACE_ROOT,
    )
```

- [ ] **Step 2: Replace `tests/integration/conftest.py`**

The conftest now imports from helpers and the generic fixtures, and defines only the bootstrap-specific fixtures:

```python
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


@pytest.fixture(scope="session")
def bootstrap_vm(request):
    """Fresh Debian VM with bootstrap playbook already applied."""
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

    if _should_keep_vm(request):
        print_debug_info(vm)
    else:
        vm.destroy()
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/helpers.py tests/integration/conftest.py
git commit -m "refactor: move bootstrap-specific helpers and fixtures to test tree"
```

### Task 6: Update integration test imports

**Files:**
- Modify: `tests/integration/test_bootstrap_integration.py`
- Modify: `tests/integration/test_single_role.py`
- Modify: `tests/integration/test_tailscale_integration.py`

- [ ] **Step 1: Update `test_bootstrap_integration.py` imports (lines 25-26)**

Replace:
```python
from incus.ansible import run_bootstrap_playbook, run_verify_playbook
from incus.constants import SSH_CONNECT_TIMEOUT_SECONDS
```

With:
```python
from incus.constants import SSH_CONNECT_TIMEOUT_SECONDS
from tests.integration.helpers import run_bootstrap_playbook, run_verify_playbook
```

- [ ] **Step 2: Update `test_single_role.py` import (line 6)**

Replace:
```python
from incus.ansible import run_bootstrap_playbook
```

With:
```python
from tests.integration.helpers import run_bootstrap_playbook
```

- [ ] **Step 3: Update `test_tailscale_integration.py` import (line 18)**

Replace:
```python
from incus.ansible import run_bootstrap_playbook
```

With:
```python
from tests.integration.helpers import run_bootstrap_playbook
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "refactor: update integration test imports for conftest wrappers"
```

### Task 7: Update unit tests

**Files:**
- Modify: `tests/unit/test_ansible_helpers.py`

- [ ] **Step 1: Replace `tests/unit/test_ansible_helpers.py`**

Remove `TestRunBootstrapPlaybook` and `TestRunVerifyPlaybook` classes (they tested bootstrap-specific functions that are now in conftest). Replace with tests for the generic `run_playbook`:

```python
"""Unit tests for Ansible playbook execution helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from incus.ansible import (
    build_inventory,
    build_single_role_playbook,
    run_playbook,
)

pytestmark = pytest.mark.unit


class TestBuildInventory:
    def test_generates_valid_yaml_inventory(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 22
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm)
        inv = yaml.safe_load(content)

        assert "all" in inv
        host_vars = inv["all"]["hosts"]["testvm"]
        assert host_vars["ansible_host"] == "10.0.0.42"
        assert host_vars["ansible_ssh_private_key_file"] == "/tmp/fake/id_ed25519"
        assert host_vars["ansible_user"] == "root"
        assert host_vars["ansible_port"] == 22

    def test_uses_vm_ssh_port(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 2222
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm)
        inv = yaml.safe_load(content)
        assert inv["all"]["hosts"]["testvm"]["ansible_port"] == 2222

    def test_uses_custom_user(self):
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 22
        vm.ssh_key = MagicMock(private_key_path="/tmp/fake/id_ed25519")

        content = build_inventory(vm, user="ansible")
        inv = yaml.safe_load(content)
        assert inv["all"]["hosts"]["testvm"]["ansible_user"] == "ansible"


class TestBuildSingleRolePlaybook:
    def test_generates_playbook_with_single_role(self):
        content = build_single_role_playbook("ssh_hardening")
        playbook = yaml.safe_load(content)

        assert len(playbook) == 1
        play = playbook[0]
        assert play["become"] is True
        assert {"role": "ssh_hardening"} in play["roles"]

    def test_generates_playbook_with_role_list(self):
        content = build_single_role_playbook(["users", "ssh_hardening"])
        playbook = yaml.safe_load(content)

        play = playbook[0]
        assert len(play["roles"]) == 2
        assert {"role": "users"} in play["roles"]
        assert {"role": "ssh_hardening"} in play["roles"]


class TestRunPlaybook:
    @patch("incus.ansible.subprocess.run")
    def test_runs_ansible_playbook_directly(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 22
        vm.ssh_key = MagicMock(private_key_path=Path("/tmp/fake/id_ed25519"))

        run_playbook(vm, playbook_path=Path("/tmp/site.yml"))

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ansible-playbook"
        cmd_str = " ".join(str(c) for c in cmd)
        assert "/tmp/site.yml" in cmd_str

    @patch("incus.ansible.subprocess.run")
    def test_passes_extra_vars_via_json_file(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 22
        vm.ssh_key = MagicMock(private_key_path=Path("/tmp/fake/id_ed25519"))

        run_playbook(vm, playbook_path=Path("/tmp/site.yml"), extra_vars={"ssh_port": 2222})

        cmd = mock_run.call_args[0][0]
        extra_var_args = [c for c in cmd if str(c).startswith("@")]
        assert len(extra_var_args) == 1
        assert "-e" in cmd

    @patch("incus.ansible.subprocess.run")
    def test_passes_cwd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 22
        vm.ssh_key = MagicMock(private_key_path=Path("/tmp/fake/id_ed25519"))

        run_playbook(vm, playbook_path=Path("/tmp/site.yml"), cwd="/some/dir")

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == "/some/dir"

    @patch("incus.ansible.subprocess.run")
    def test_does_not_mutate_vm_ssh_port(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        vm = MagicMock()
        vm.ip_address = "10.0.0.42"
        vm.ssh_port = 22
        vm.ssh_key = MagicMock(private_key_path=Path("/tmp/fake/id_ed25519"))

        run_playbook(vm, playbook_path=Path("/tmp/site.yml"), extra_vars={"ssh_port": 2222})

        # run_playbook should NOT mutate vm.ssh_port — that's the caller's job
        assert vm.ssh_port == 22
```

- [ ] **Step 2: Run linting and tests**

Run: `make python-lint && make test-unit`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_ansible_helpers.py
git commit -m "refactor: update unit tests for generic run_playbook"
```

### Task 8: Run full test suite and verify

- [ ] **Step 1: Run linting**

Run: `make python-lint`
Expected: No errors.

- [ ] **Step 2: Run unit and property tests**

Run: `make test-unit && make test-property`
Expected: All pass.

- [ ] **Step 3: Verify `make images` still works**

Run: `make images`
Expected: Both `bootstrap/knocking-13` and `bootstrap/open-13` published. This validates that the guarded `publish` command and `_PUBLISH_VARS` work correctly with the generic `run_playbook`.

- [ ] **Step 4: Clean up test images**

```bash
make images-clean
```

- [ ] **Step 5: Commit any fixes discovered**

Only if needed.
