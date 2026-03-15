# Incus Image Publishing Design

## Goal

Provide two pre-built Incus VM images that other projects on this machine can use in their integration tests, avoiding the need to run the full bootstrap playbook each time.

## Scope

### In scope (this spec)

- Migrate `tests/infra/` to top-level `incus/` module
- Update all imports and Makefile targets to use the new module path
- Switch fixture discovery to `pytest_plugins` mechanism
- Add `publish` subcommand to `incus/__main__.py` that builds two images:
  - `bootstrap/knocking-{version}` — tailscale disabled, port-knocking enabled
  - `bootstrap/open-{version}` — tailscale and port-knocking both disabled
- Add `make images` and `make images-clean` targets

### Out of scope

- Uploading images to remote registries
- Automatic rebuild on playbook changes (images are rebuilt on-demand)
- Individual image targets (both images always built together)

## Image Definitions

| Alias | Tailscale | Port Knocking | Use Case |
|-------|-----------|---------------|----------|
| `bootstrap/knocking-{version}` | disabled | enabled | Test services behind port-knocking |
| `bootstrap/open-{version}` | disabled | disabled | Test services with direct SSH access |

`{version}` is the Debian version number (e.g. `13`). Both images default to Debian 13, overridable via `DEBIAN=` Make variable.

## Module Migration

Rename `tests/infra/` to `incus/` at the project root. The module contents are the same, with one path fix:

```
incus/
├── __init__.py
├── __main__.py        # CLI: python -m incus <action>
├── vm.py              # IncusVM class
├── ssh.py             # Ephemeral SSH keypairs
├── ansible.py         # Playbook execution helpers
├── constants.py       # Configuration constants
├── fixtures.py        # Pytest fixtures
└── headscale.py       # Headscale control server
```

### WORKSPACE_ROOT fix

`ansible.py` computes `WORKSPACE_ROOT = Path(__file__).parent.parent.parent` (three levels: `ansible.py → infra/ → tests/ → root`). After the move to `incus/`, this becomes two levels: `ansible.py → incus/ → root`. Update to `Path(__file__).parent.parent`.

### Import changes

All `tests.infra.*` imports become `incus.*` imports. Affected files:

- `incus/` internal imports (vm.py, ansible.py, fixtures.py, headscale.py, __main__.py, __init__.py)
- `tests/integration/conftest.py` — switch to `pytest_plugins = ["incus.fixtures"]` (the `pytest_addoption` hook for `--debian-version` stays in this file)
- `tests/integration/test_bootstrap_integration.py`
- `tests/integration/test_tailscale_integration.py`
- `tests/integration/test_single_role.py`
- `tests/unit/test_ansible_helpers.py`
- `tests/unit/test_incus_vm.py`
- `tests/unit/test_ssh_keypair.py`

### Makefile changes

- Existing `vm-*` targets change from `uv run -m tests.infra` to `uv run -m incus`.
- `python-lint` and `python-lint-fix` currently only lint `tests/`. Update to lint both `tests/` and `incus/`.

### pyproject.toml changes

The ruff `per-file-ignores` section may reference `tests/*` patterns. Ensure `incus/*` files that use `assert` (e.g. fixtures) get the same ignore rules.

## Image Build Process

The `publish` subcommand in `incus/__main__.py` builds both images sequentially. For each image:

1. Create a fresh VM from `images:debian/{version}`
2. Wait for VM ready (incus agent, SSH)
3. Run `site.yml` with the image-specific variables
4. Stop the VM (`incus stop` with a timeout; fall back to `incus stop --force` if it hangs)
5. Delete any existing image with the target alias
6. Publish: `incus publish {vm} --alias bootstrap/{variant}-{version}`
7. Delete the source VM

### Failure handling

If any step fails, destroy the source VM before aborting. If the first image fails, skip the second and exit with an error. This avoids leaving dangling VMs behind.

### Bootstrap variables per image

**knocking:**
```yaml
tailscale_enabled: false
firewall_port_knocking_enabled: true
```
Plus the standard test variables from `constants.py` (test user, SSH port, etc.).

**open:**
```yaml
tailscale_enabled: false
firewall_port_knocking_enabled: false
```
Plus the same standard test variables.

## Makefile Targets

```makefile
make images              # Build both images (always rebuilds)
make images-clean        # Delete all bootstrap/* images from local Incus store
```

`make images` accepts `DEBIAN=` (defaults to 13), matching the existing `vm-create` convention.

## What Doesn't Change

- All existing test behavior (fixtures, VM lifecycle, headscale)
- The Ansible roles and playbook
- The existing `vm-create`, `vm-list`, `vm-destroy`, `vm-ssh` CLI commands (just new import paths)
