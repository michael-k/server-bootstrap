# Agent Instructions

This document contains instructions for AI agents working on this project.

## Command Execution Rules

### CRITICAL: Always Use `uv run` or `make`

This project uses `uv` for Python dependency management and virtual environment isolation. All Python-related commands MUST be executed through `uv run` or the provided `make` targets.

### ✅ CORRECT Command Patterns

**Python execution:**
```bash
# Use uv run for Python commands
uv run python -c "print('hello')"
uv run python script.py
uv run pytest tests/

# Use uv run for installed tools
uv run ansible-playbook playbook.yml
uv run ansible-vault encrypt vault.yml
uv run pytest --hypothesis-show-statistics
```

**Make targets (preferred when available):**
```bash
make bootstrap          # Run the bootstrap playbook
make verify            # Run verification tests
make test              # Run all tests
make test-unit         # Run unit tests
make test-property     # Run property-based tests
make test-integration  # Run integration tests
make clean             # Clean up generated files
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
```

## Why This Matters

1. **Dependency Isolation**: `uv` ensures all dependencies are installed and isolated in a project-specific environment
2. **Reproducibility**: Commands run through `uv run` use the exact versions specified in `pyproject.toml`
3. **Consistency**: All developers and CI/CD pipelines use identical environments
4. **No Manual Setup**: `uv run` automatically creates and manages the virtual environment

## Common Command Translations

| ❌ Don't Use | ✅ Use Instead |
|-------------|---------------|
| `python -c "..."` | `uv run python -c "..."` |
| `python script.py` | `uv run script.py` |
| `pytest` | `uv run pytest` or `make test` |
| `ansible-playbook` | `uv run ansible-playbook` or `make bootstrap` |
| `ansible-vault` | `uv run ansible-vault` |
| `pip install` | `uv add` (to add dependencies) |

## Testing Commands

Always use `uv run` or `make` for testing:

```bash
# Property-based tests with Hypothesis
uv run pytest tests/property/ -v
make test-property

# Unit tests
uv run pytest tests/unit/ -v
make test-unit

# Integration tests
uv run pytest tests/integration/ -v
make test-integration

# All tests
uv run pytest tests/
make test
```

## Ansible Commands

All Ansible commands must use `uv run`:

```bash
# Run playbook
uv run ansible-playbook -i inventory/hosts.yml playbook.yml
make bootstrap

# Verify configuration
uv run ansible-playbook -i inventory/hosts.yml tests/verify_bootstrap.yml
make verify

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

**Golden Rule**: If it's Python-related or uses a tool from `pyproject.toml`, prefix it with `uv run` or use a `make` target.
