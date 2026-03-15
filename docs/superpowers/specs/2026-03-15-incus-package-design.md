# Incus Package Design

## Goal

Make `incus/` a reusable Python package so that other local Ansible projects can use it for their Incus VM integration tests, without duplicating VM lifecycle, SSH, fixture, or playbook execution code.

## Scope

### In scope

- Restructure `incus/` to `src/` layout with its own `pyproject.toml`
- Refactor `ansible.py` into a generic `run_playbook` function (no bootstrap-specific defaults)
- Split constants and fixtures into generic (package) and bootstrap-specific (server-bootstrap test tree)
- Guard bootstrap-specific CLI commands (`publish`, `images-clean`) behind a `site.yml` existence check
- Add `incus` as an editable path dependency in server-bootstrap's `pyproject.toml`
- Move bootstrap-specific wrappers (`run_bootstrap_playbook`, `run_verify_playbook`, `bootstrap_vm`, `swap_vm`, `DEFAULT_TEST_VARS`) into server-bootstrap's test conftest

### Out of scope

- Publishing to PyPI
- Extracting `incus/` to a separate repository
- Changes to the 3 consumer projects (they adopt the package independently)

## Package Structure

```
incus/
├── pyproject.toml
└── src/
    └── incus/
        ├── __init__.py         # Public API: IncusVM, SSHKeyPair
        ├── __main__.py         # CLI: create, list, destroy, ssh + guarded: publish, images-clean
        ├── vm.py               # IncusVM class
        ├── ssh.py              # SSHKeyPair class
        ├── ansible.py          # Generic run_playbook()
        ├── constants.py        # Generic constants (prefixes, timeouts)
        ├── fixtures.py         # Generic fixtures: clean_vm, incus_available()
        └── headscale.py        # HeadscaleServer (not part of public API)
```

Imports remain `from incus.vm import IncusVM` everywhere. The `src/` layout prevents accidental uninstalled imports.

## Refactoring Details

### `ansible.py`

The current `run_bootstrap_playbook` is split into a generic function and a project-specific wrapper.

**Generic (stays in package):**

`run_playbook(vm, playbook_path, extra_vars=None, roles=None, check_mode=False, user="root", timeout=600, cwd=None, roles_path=None)` — runs any playbook against a VM. Accepts explicit playbook path and vars. No default variable merging. No `WORKSPACE_ROOT` concept — the caller provides `cwd` and `roles_path` as needed.

Key changes from the current `run_bootstrap_playbook`:
- Invokes `ansible-playbook` directly (not `uv run ansible-playbook`) so the package works regardless of how consumers manage their Python environment.
- `cwd` parameter: working directory for the subprocess. Defaults to `None` (inherits from parent process).
- `roles_path` parameter: sets `ANSIBLE_ROLES_PATH` env var when running single-role playbooks. Replaces the hardcoded `WORKSPACE_ROOT / "roles"`.
- No `vm.ssh_port` mutation side-effect — the caller handles this if needed.

The existing `build_inventory`, `build_single_role_playbook`, and `_get_ssh_public_key_file` helper functions remain in the package as they are generic.

`WORKSPACE_ROOT` is removed from `ansible.py` entirely — it was bootstrap-specific.

**Moves to server-bootstrap `tests/integration/conftest.py`:**

`run_bootstrap_playbook(vm, extra_vars=None, **kwargs)` — thin wrapper that merges `DEFAULT_TEST_VARS`, injects SSH key paths, passes `cwd=WORKSPACE_ROOT` and `roles_path=WORKSPACE_ROOT / "roles"`, calls `run_playbook` with `site.yml`, and mutates `vm.ssh_port` on success.

`run_verify_playbook(vm, extra_vars=None, **kwargs)` — thin wrapper pointing at `tests/verify_bootstrap.yml`.

`WORKSPACE_ROOT` is defined in the conftest as `Path(__file__).resolve().parents[2]` (integration/ → tests/ → project root).

### `constants.py`

**Stays in package (generic):**
- `VM_NAME_PREFIX`, `IMAGE_PREFIX`, `DEFAULT_DEBIAN_VERSION`
- `VM_READY_TIMEOUT_SECONDS`, `SSH_CONNECT_TIMEOUT_SECONDS`, `SSH_POLL_INTERVAL_SECONDS`

**Moves to server-bootstrap `tests/integration/conftest.py`:**
- `DEFAULT_TEST_VARS`

**Stays in `__main__.py` (guarded, bootstrap-specific):**
- `IMAGE_ALIAS_PREFIX`, `IMAGE_VARIANTS`, `VM_STOP_TIMEOUT_SECONDS`

### `fixtures.py`

**Stays in package (generic):**
- `incus_available()`, `clean_vm`, `_should_keep()`, `print_debug_info()`

**Moves to server-bootstrap `tests/integration/conftest.py`:**
- `bootstrap_vm`, `swap_vm` (these depend on `run_bootstrap_playbook` and `DEFAULT_TEST_VARS`)

Consumers register generic fixtures via direct import in their conftest (`from incus.fixtures import clean_vm  # noqa: F401`). Server-bootstrap's `tests/integration/conftest.py` imports the generic fixtures this way and defines `bootstrap_vm`/`swap_vm` locally in the same file.

### `__init__.py`

Exports `IncusVM` and `SSHKeyPair` in `__all__`. Both the `HeadscaleServer` import line and its `__all__` entry are removed from `__init__.py`. It remains importable via `from incus.headscale import HeadscaleServer` for server-bootstrap's tailscale tests.

### `__main__.py` CLI Guarding

The `publish` and `images-clean` subcommands are only registered when running from within server-bootstrap. The guard checks for `site.yml` relative to the current working directory:

```python
if Path("site.yml").exists():
    # register publish, images-clean subparsers
```

`cmd_publish` calls the generic `run_playbook` directly. It does not depend on `run_bootstrap_playbook`. The full set of bootstrap variables needed for image publishing (user names, password hashes, SSH key paths, port knocking sequence, hostname, etc. — the same 13+ keys currently in `DEFAULT_TEST_VARS`) are defined as a `_PUBLISH_VARS` dict in `__main__.py` alongside the existing `IMAGE_VARIANTS` constants. These are bootstrap-specific and only used by the guarded commands. The image variant overrides (`tailscale_enabled`, `firewall_port_knocking_enabled`) are merged on top of `_PUBLISH_VARS` before calling `run_playbook`.

## Server-Bootstrap Integration

### `pyproject.toml` Changes

Add `incus` as an editable dev dependency:

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

### pytest Configuration

Remove `pythonpath = ["."]` from pytest config (package is installed via editable install, not via path hacking).

### Test Import Changes

- `run_bootstrap_playbook` and `run_verify_playbook` are imported from the local conftest (or a local helper module), not from `incus.ansible`
- `IncusVM`, `SSHKeyPair`, `clean_vm`, `incus_available` continue to import from `incus.*`
- `DEFAULT_TEST_VARS` imports from the local conftest
- `HeadscaleServer` continues to import from `incus.headscale`

## `incus/pyproject.toml`

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

The `src/` layout is auto-detected by `uv build`. Base dependency: only `pyyaml` (for inventory/playbook YAML generation). The `fixtures` extra adds `pytest` for projects that use `incus.fixtures`. Consumers install with `uv add --dev "incus[fixtures]"` to get pytest fixtures, or plain `incus` for just `IncusVM` and `run_playbook`.

## Consumer Usage

Other projects add the package and use it:

```bash
# Local path
uv add --dev --editable --path ../server-bootstrap/incus

# Or from git
uv add --dev "incus @ git+https://github.com/michael-k/server-bootstrap.git#subdirectory=incus"
```

Consumer test code:

```python
from incus.vm import IncusVM
from incus.ansible import run_playbook
from incus.fixtures import clean_vm  # noqa: F401 (or via pytest_plugins)

def test_my_role(clean_vm):
    result = run_playbook(clean_vm, playbook_path=Path("site.yml"), extra_vars={...})
    assert result.returncode == 0
```

## Makefile Updates

The `python-lint` and `python-lint-fix` targets change from `tests/ incus/` to `tests/ incus/src/` to reflect the new source location. The ruff `per-file-ignores` in the root `pyproject.toml` also updates from `"incus/*"` to `"incus/src/incus/*"`.

## Unit Test Updates

`tests/unit/test_ansible_helpers.py` imports `run_bootstrap_playbook` and `run_verify_playbook` from `incus.ansible`. After the refactor these functions move out of the package. The unit tests must be updated to test the generic `run_playbook` function instead, or to test the wrappers from conftest.

## What Doesn't Change

- `IncusVM` API (create, destroy, exec, ssh, knock, wait_ready, etc.)
- `SSHKeyPair` API
- CLI commands: `uv run python -m incus create/list/destroy/ssh`
- `make images` / `make images-clean` in server-bootstrap
- Image aliases: `bootstrap/knocking-13`, `bootstrap/open-13`
