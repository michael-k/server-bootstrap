# Agent Instructions

This document contains instructions for AI agents working on this project.

## Project Documentation

All project specifications live under [specs/](specs/). Start at
[specs/README.md](specs/README.md), the spec tree's entry point, and read
[specs/project/security-invariants.md](specs/project/security-invariants.md)
for the invariants every spec obeys.

`specs/` is the authoritative source of truth for this project: a mismatch
between a spec and the implementation is a bug in the implementation, not in
the spec.

The change process runs one way: edit the spec first, get it reviewed, then
bring the implementation to match. Never change behaviour and its spec in
opposite directions, and never adjust a spec to match code that has drifted
without saying so.

Do not explain a decision in a comment when a requirement already states
it — cite the requirement ID instead.

`make spec-check` is the gate — run it before committing.

## Command Execution Rules

### CRITICAL: Always Prefer `make` Targets

This project uses `uv` for Python dependency management and virtual environment isolation. All Python-related commands MUST be executed through the provided `make` targets when available, or through `uv run` as a fallback.

### ✅ CORRECT Command Patterns (in order of preference)

**1. Make targets (ALWAYS USE WHEN AVAILABLE):**
```bash
make bootstrap          # Run the bootstrap playbook
make verify            # Run verification tests
make test              # Run all tests
make test-unit         # Run unit tests
make test-property     # Run property-based tests
make test-integration  # Run integration tests
make python-lint       # Check Python code with ruff
make python-lint-fix   # Fix Python code issues with ruff
make python-typecheck  # Type-check Python code with ty
make ansible-lint      # Check Ansible files with ansible-lint
make ansible-lint-fix  # Fix Ansible files with ansible-lint
make clean             # Clean up generated files
```

**2. uv run (ONLY when no make target exists):**
```bash
# Use uv run for Python commands without make targets
uv run python -c "print('hello')"
uv run python script.py

# Use uv run for Ansible commands without make targets
uv run ansible-vault encrypt inventory/vault.yml
uv run ansible-vault edit inventory/vault.yml
uv run ansible-playbook --syntax-check playbook.yml
```

### ❌ INCORRECT Command Patterns (NEVER USE)

```bash
# WRONG - bypasses uv environment
python -c "print('hello')"
python3 script.py
pytest tests/
ansible-playbook playbook.yml
pip install package

# WRONG - direct virtual environment activation
source .venv/bin/activate
.venv/bin/python script.py

# WRONG - using uv run when make target exists
uv run pytest tests/              # Use: make test
uv run pytest tests/property/     # Use: make test-property
uv run ruff check tests/          # Use: make python-lint
uv run ruff check --fix tests/    # Use: make python-lint-fix
uv run ansible-lint               # Use: make ansible-lint
```

## Why This Matters

1. **Consistency**: Make targets provide a consistent interface across all environments
2. **Simplicity**: Shorter commands that are easier to remember and type
3. **Dependency Isolation**: `uv` ensures all dependencies are installed and isolated in a project-specific environment
4. **Reproducibility**: Commands use the exact versions specified in `pyproject.toml`
5. **No Manual Setup**: `uv run` automatically creates and manages the virtual environment
6. **Centralized Configuration**: Make targets can include additional flags and options consistently

## Common Command Translations

| ❌ Don't Use | ✅ Use Instead |
|-------------|---------------|
| `python -c "..."` | `uv run python -c "..."` |
| `python script.py` | `uv run script.py` |
| `pytest` | `make test` |
| `pytest tests/property/` | `make test-property` |
| `pytest tests/unit/` | `make test-unit` |
| `ruff check` | `make python-lint` |
| `ruff check --fix` | `make python-lint-fix` |
| `ty check` | `make python-typecheck` |
| `ansible-lint` | `make ansible-lint` |
| `ansible-playbook` | `make bootstrap` or `uv run ansible-playbook` |
| `ansible-vault` | `uv run ansible-vault` |
| `pip install` | `uv add` (to add dependencies) |

## Testing Commands

**ALWAYS use `make` targets for testing:**

```bash
# All tests
make test

# Property-based tests with Hypothesis
make test-property

# Unit tests
make test-unit

# Integration tests
make test-integration
```

**AVOID using `uv run pytest` directly** - the make targets are preferred for consistency.

## Linting Commands

**ALWAYS use `make` targets for linting:**

```bash
# Python linting with ruff
make python-lint

# Python auto-fix with ruff
make python-lint-fix

# Python type-checking with ty
make python-typecheck

# Ansible linting
make ansible-lint

# Ansible linting specific paths
make ansible-lint ARGS="roles/users/"

# Ansible auto-fix
make ansible-lint-fix

# Ansible auto-fix specific paths
make ansible-lint-fix ARGS="roles/users/"
```

**AVOID using `uv run ruff` or `uv run ansible-lint` directly** - the make targets are preferred for consistency.

## Ansible Commands

**Use `make` targets when available, otherwise use `uv run`:**

```bash
# Run bootstrap playbook
make bootstrap

# Verify configuration
make verify

# For other Ansible commands, use uv run:
# Encrypt secrets
uv run ansible-vault encrypt inventory/vault.yml

# Edit encrypted files
uv run ansible-vault edit inventory/vault.yml

# Check syntax
uv run ansible-playbook --syntax-check playbook.yml
```

## Exception: System Commands

Only pure system commands that don't involve Python or project dependencies can be run directly:

```bash
# These are OK - they're system commands, not Python
git status
git commit -m "message"
ls -la
cat file.txt
grep pattern file.txt
```

## Summary

**Golden Rules**:
1. **ALWAYS prefer `make` targets when they exist** - they provide consistency and simplicity
2. **NEVER use `pytest` or `ruff` directly** - always use `make test*` and `make python-lint*`
3. **NEVER use `ansible-lint` directly** - always use `make ansible-lint*`
4. If no `make` target exists, use `uv run` to ensure proper environment isolation
5. Never bypass the environment with direct `python`, `pytest`, `ruff`, or `ansible-*` commands
