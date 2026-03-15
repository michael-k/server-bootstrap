# Incus Image Publishing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `tests/infra/` to top-level `incus/` module and add image publishing so other projects can launch pre-bootstrapped VMs.

**Architecture:** Move the Incus VM management module to `incus/`, update all references, then add a `publish` CLI subcommand that bootstraps VMs with specific configs and publishes them as reusable Incus images.

**Tech Stack:** Python, Incus CLI, Ansible, pytest, Make

---

## Chunk 1: Module Migration

### Task 1: Move `tests/infra/` to `incus/` and fix internal imports

**Files:**
- Rename: `tests/infra/` → `incus/`
- Modify: `incus/__init__.py`
- Modify: `incus/vm.py`
- Modify: `incus/ansible.py`
- Modify: `incus/fixtures.py`
- Modify: `incus/headscale.py`
- Modify: `incus/__main__.py`
- No changes needed: `incus/ssh.py`, `incus/constants.py` (no internal `tests.infra` imports)

- [ ] **Step 1: Move the directory**

```bash
git mv tests/infra incus
```

- [ ] **Step 2: Fix internal imports in `incus/__init__.py`**

```python
from incus.headscale import HeadscaleServer
from incus.ssh import SSHKeyPair
from incus.vm import IncusVM

__all__ = ["HeadscaleServer", "IncusVM", "SSHKeyPair"]
```

- [ ] **Step 3: Fix internal imports in `incus/vm.py`**

Replace all `tests.infra.` with `incus.` in the import block (lines 13-19):

```python
from incus.constants import (
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_POLL_INTERVAL_SECONDS,
    VM_NAME_PREFIX,
    VM_READY_TIMEOUT_SECONDS,
)
from incus.ssh import SSHKeyPair
```

- [ ] **Step 4: Fix internal imports in `incus/ansible.py`**

Replace `tests.infra.` with `incus.` (lines 13, 16) and fix `WORKSPACE_ROOT` (line 18):

```python
from incus.constants import DEFAULT_TEST_VARS

if TYPE_CHECKING:
    from incus.vm import IncusVM

WORKSPACE_ROOT = Path(__file__).parent.parent
```

Note: `WORKSPACE_ROOT` changes from `.parent.parent.parent` (3 levels from `tests/infra/`) to `.parent.parent` (2 levels from `incus/`).

- [ ] **Step 5: Fix internal imports in `incus/fixtures.py`**

Replace `tests.infra.` with `incus.` (lines 10-12):

```python
from incus.ansible import run_bootstrap_playbook
from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from incus.vm import IncusVM
```

- [ ] **Step 6: Fix internal imports in `incus/headscale.py`**

Replace `tests.infra.` with `incus.` (line 10):

```python
from incus.vm import IncusVM
```

- [ ] **Step 7: Fix internal imports in `incus/__main__.py`**

Only two lines change — the `tests.infra` imports (lines 20-21). All other imports (`argparse`, `glob`, `json`, `os`, `subprocess`, `sys`, `tempfile`) remain untouched. Also update the module docstring.

```python
"""CLI entry point for Incus VM management.

Usage:
    uv run python -m incus create [--debian VERSION]
    uv run python -m incus list
    uv run python -m incus destroy <name>
    uv run python -m incus destroy --all
    uv run python -m incus ssh <name>
    uv run python -m incus publish [--debian VERSION]
"""

# ... (all other imports unchanged)

from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX, VM_NAME_PREFIX
from incus.vm import IncusVM
```

(The docstring update anticipates the `publish` command from Task 4; the `publish` implementation itself comes later.)

- [ ] **Step 8: Run unit tests to verify imports resolve**

Run: `make test-unit`
Expected: All tests FAIL because test files still import `tests.infra.*`

- [ ] **Step 9: Commit**

```bash
git add incus/ tests/
git commit -m "refactor: move tests/infra/ to top-level incus/ module"
```

### Task 2: Update test file imports

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_bootstrap_integration.py`
- Modify: `tests/integration/test_tailscale_integration.py`
- Modify: `tests/integration/test_single_role.py`
- Modify: `tests/unit/test_ansible_helpers.py`
- Modify: `tests/unit/test_incus_vm.py`
- Modify: `tests/unit/test_ssh_keypair.py`

- [ ] **Step 1: Update `tests/integration/conftest.py`**

Replace the entire file. The old `from tests.infra.fixtures import bootstrap_vm, clean_vm, swap_vm` is replaced by `pytest_plugins = ["incus.fixtures"]`, which tells pytest to auto-register all `@pytest.fixture` functions in that module — no explicit imports needed:

```python
"""Pytest configuration for integration tests."""


import pytest

pytest_plugins = ["incus.fixtures"]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --debian-version CLI option."""
    parser.addoption(
        "--debian-version",
        action="store",
        default="13",
        help="Debian version for Incus VMs (default: 13, also: trixie, testing, sid)",
    )
```

- [ ] **Step 2: Update `tests/integration/test_bootstrap_integration.py`**

Replace imports (lines 25-26):

```python
from incus.ansible import run_bootstrap_playbook, run_verify_playbook
from incus.constants import SSH_CONNECT_TIMEOUT_SECONDS
```

- [ ] **Step 3: Update `tests/integration/test_tailscale_integration.py`**

Replace imports (lines 18-22):

```python
from incus.ansible import run_bootstrap_playbook
from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX
from incus.fixtures import incus_available, print_debug_info
from incus.headscale import HeadscaleServer
from incus.vm import IncusVM
```

- [ ] **Step 4: Update `tests/integration/test_single_role.py`**

Replace import (line 6):

```python
from incus.ansible import run_bootstrap_playbook
```

- [ ] **Step 5: Update `tests/unit/test_ansible_helpers.py`**

Replace all `tests.infra` with `incus` throughout the file. This includes the import block (line 9), all `@patch()` decorator strings, and the inline import (line 130).

Import:
```python
from incus.ansible import (
    build_inventory,
    build_single_role_playbook,
    run_bootstrap_playbook,
)
```

Patch string patterns to update (each appears one or more times):
- `"tests.infra.ansible._get_ssh_public_key_file"` → `"incus.ansible._get_ssh_public_key_file"` (lines 77, 96)
- `"tests.infra.ansible.subprocess.run"` → `"incus.ansible.subprocess.run"` (lines 78, 97, 119)

And the inline import (line 130):
```python
from incus.ansible import run_verify_playbook
```

- [ ] **Step 6: Update `tests/unit/test_incus_vm.py`**

Replace all `tests.infra` with `incus`. This includes the import (line 9) AND all `@patch()` strings and `with patch()` calls:

Import:
```python
from incus.vm import IncusVM
```

Patch strings to update:
- `"tests.infra.vm.subprocess.run"` → `"incus.vm.subprocess.run"`
- `"tests.infra.vm.SSHKeyPair.create"` → `"incus.vm.SSHKeyPair.create"`

- [ ] **Step 7: Update `tests/unit/test_ssh_keypair.py`**

Replace import (line 6):

```python
from incus.ssh import SSHKeyPair
```

- [ ] **Step 8: Run all unit tests**

Run: `make test-unit`
Expected: All unit tests PASS

- [ ] **Step 9: Commit**

```bash
git add tests/
git commit -m "refactor: update all test imports from tests.infra to incus"
```

### Task 3: Update Makefile and pyproject.toml

**Files:**
- Modify: `Makefile`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update Makefile vm-* targets**

Replace `tests.infra` with `incus` in lines 77, 81, 84, 88:

```makefile
vm-create:
	@echo "Creating test VM..."
	uv run python -m incus create --debian $(or $(DEBIAN),13)

vm-list:
	@echo "Test VMs:"
	uv run python -m incus list

vm-destroy:
	uv run python -m incus destroy $(if $(VM),$(VM),--all)

vm-ssh:
	@test -n "$(VM)" || (echo "Usage: make vm-ssh VM=<name>" && exit 1)
	uv run python -m incus ssh $(VM)
```

- [ ] **Step 2: Update Makefile lint targets to include `incus/`**

Update `python-lint` and `python-lint-fix` to lint both directories:

```makefile
python-lint:
	@echo "Checking Python code with ruff..."
	uv run ruff check tests/ incus/

python-lint-fix:
	@echo "Fixing Python code with ruff..."
	uv run ruff check --fix tests/ incus/
```

- [ ] **Step 3: Update pyproject.toml ruff per-file-ignores**

Add `incus/*` to the S101 ignore (line 65):

```toml
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]  # Allow assert in tests
"incus/*" = ["S101"]  # Allow assert in fixtures/infra code
```

- [ ] **Step 4: Run linting to verify**

Run: `make python-lint`
Expected: No errors

- [ ] **Step 5: Run full test suite**

Run: `make test-unit && make test-property`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add Makefile pyproject.toml
git commit -m "refactor: update Makefile and pyproject.toml for incus/ module"
```

## Chunk 2: Image Publishing

### Task 4: Add `publish` subcommand to `incus/__main__.py`

**Files:**
- Modify: `incus/__main__.py`
- Modify: `incus/constants.py`

- [ ] **Step 1: Add image definitions to `incus/constants.py`**

Append to the end of the file:

```python
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
```

- [ ] **Step 2: Add helper functions to `incus/__main__.py`**

Add the following imports at the top (alongside existing imports):

```python
from incus.ansible import run_bootstrap_playbook
from incus.constants import IMAGE_ALIAS_PREFIX, IMAGE_VARIANTS, VM_STOP_TIMEOUT_SECONDS
```

Add these helper functions before `cmd_publish`:

```python
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
        print(f"  Graceful stop failed, forcing...")
        subprocess.run(
            ["incus", "stop", name, "--force"],
            capture_output=True,
            text=True,
            check=True,
        )
```

- [ ] **Step 3: Add `cmd_publish` function**

```python
def cmd_publish(args: argparse.Namespace) -> None:
    """Build and publish bootstrapped VM images."""
    version = args.debian

    for variant, extra_vars in IMAGE_VARIANTS.items():
        alias = f"{IMAGE_ALIAS_PREFIX}{variant}-{version}"
        print(f"Building image '{alias}'...")

        image = f"{IMAGE_PREFIX}{version}"
        vm = IncusVM.create(image=image, name_hint=f"publish-{variant}")
        try:
            print(f"  Waiting for VM '{vm.name}'...")
            vm.wait_ready()

            print(f"  Running bootstrap playbook...")
            result = run_bootstrap_playbook(vm, extra_vars=dict(extra_vars))
            if result.returncode != 0:
                raise RuntimeError(
                    f"Bootstrap failed for '{variant}'.\n"
                    f"stdout: {result.stdout[-3000:]}\n"
                    f"stderr: {result.stderr[-1000:]}"
                )

            print(f"  Stopping VM...")
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
            # Always destroy the source VM (published image is independent)
            subprocess.run(
                ["incus", "delete", vm.name, "--force"],
                capture_output=True,
                text=True,
                check=False,
            )
            vm.ssh_key.cleanup()

    print("All images published.")
```

- [ ] **Step 4: Register the `publish` subcommand in `main()`**

Add after the `ssh` subparser block in the `main()` function:

```python
    # publish
    p_publish = subparsers.add_parser("publish", help="Build and publish bootstrapped VM images")
    p_publish.add_argument(
        "--debian", default=DEFAULT_DEBIAN_VERSION,
        help=f"Debian version (default: {DEFAULT_DEBIAN_VERSION})",
    )
```

And add to the commands dict:

```python
    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "destroy": cmd_destroy,
        "ssh": cmd_ssh,
        "publish": cmd_publish,
    }
```

- [ ] **Step 5: Run linting**

Run: `make python-lint`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add incus/constants.py incus/__main__.py
git commit -m "feat: add publish subcommand for building Incus VM images"
```

### Task 5: Add `make images` and `make images-clean` targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add targets to the `.PHONY` line**

Add `images` and `images-clean` to the `.PHONY` declaration on line 1.

- [ ] **Step 2: Add help text**

Add after the `vm-ssh` help line:

```makefile
	@echo "  images             Build bootstrapped VM images for other projects"
	@echo "  images-clean       Delete all bootstrap/* images from Incus"
```

- [ ] **Step 3: Add `cmd_images_clean` function to `incus/__main__.py`**

Add before the `main()` function:

```python
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
    if deleted:
        print(f"Deleted {deleted} image(s).")
    else:
        print("No bootstrap images found.")
```

Register it in `main()` — add the subparser:

```python
    # images-clean
    subparsers.add_parser("images-clean", help="Delete all bootstrap/* images")
```

And add to the commands dict:

```python
        "images-clean": cmd_images_clean,
```

- [ ] **Step 4: Add the Makefile targets**

Append to the Makefile:

```makefile
images:
	@echo "Building bootstrapped VM images..."
	uv run python -m incus publish --debian $(or $(DEBIAN),13)

images-clean:
	uv run python -m incus images-clean
```

- [ ] **Step 5: Run linting**

Run: `make python-lint`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add Makefile incus/__main__.py
git commit -m "feat: add make images and make images-clean targets"
```

### Task 6: Manual smoke test

- [ ] **Step 1: Build both images**

Run: `make images`
Expected: Both `bootstrap/knocking-13` and `bootstrap/open-13` are published without errors.

- [ ] **Step 2: Verify images exist**

Run: `incus image list bootstrap/`
Expected: Two images listed with aliases `bootstrap/knocking-13` and `bootstrap/open-13`.

- [ ] **Step 3: Launch a VM from each image to verify they work**

```bash
incus launch bootstrap/knocking-13 test-knocking --vm
incus launch bootstrap/open-13 test-open --vm
```

Wait for them to boot, then verify:
```bash
# Knocking image: nftables should have knock rules
incus exec test-knocking -- nft list ruleset | grep knock

# Open image: SSH should be directly accessible (no knock rules)
incus exec test-open -- nft list ruleset | grep -c knock  # should be 0
```

- [ ] **Step 4: Clean up test VMs and images**

```bash
incus delete test-knocking --force
incus delete test-open --force
make images-clean
```

- [ ] **Step 5: Commit any fixes discovered during smoke test**

Only if needed. If everything worked, no commit necessary.
