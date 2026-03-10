# Test Suite Documentation

This project uses pytest markers to organize and run different types of tests efficiently.

## Available Test Markers

### `@pytest.mark.unit`
Fast tests with no external dependencies. These tests verify logic by reading configuration files and templates without requiring actual system resources.

**Characteristics:**
- Fast execution (< 1 second per test)
- No network access required
- No VM or container required
- Tests configuration files, templates, and role structure

**Example:**
```python
@pytest.mark.property
@pytest.mark.unit
def test_ssh_config_properties():
    # Reads and validates SSH config template
    pass
```

### `@pytest.mark.property`
Property-based tests using Hypothesis. These tests verify universal properties that should hold for all valid inputs.

**Characteristics:**
- Generates many test cases automatically
- Tests edge cases and boundary conditions
- Verifies correctness properties across input space

**Example:**
```python
@pytest.mark.property
@pytest.mark.unit
@given(username=valid_username())
def test_user_creation_property(username: str):
    # Verifies property holds for any valid username
    pass
```

### `@pytest.mark.integration`
Tests that require actual system resources like VMs, containers, or real network connections.

**Characteristics:**
- Slow execution (seconds to minutes)
- Requires test infrastructure
- Tests actual system behavior
- May modify system state

**Example:**
```python
@pytest.mark.integration
@pytest.mark.slow
def test_actual_user_creation():
    # Runs Ansible playbook and verifies user exists
    pass
```

### `@pytest.mark.slow`
Tests that take significant time to execute, regardless of type.

**Characteristics:**
- Execution time > 5 seconds
- Often combined with integration tests
- Useful for CI/CD optimization

## Running Tests

### Run all tests
```bash
make test
```

### Run only unit tests (fast)
```bash
make test-unit
```

### Run only property-based tests
```bash
make test-property
```

### Run only integration tests (slow, requires infrastructure)
```bash
make test-integration
```

### Run specific marker combinations
```bash
# Property tests that are also unit tests
uv run pytest -m "property and unit"

# All tests except integration
uv run pytest -m "not integration"

# Only slow tests
uv run pytest -m slow

# Property tests that are NOT unit tests
uv run pytest -m "property and not unit"
```

## Current Test Organization

### Property Tests (all marked with `@pytest.mark.property` and `@pytest.mark.unit`)
- `tests/property/test_ssh_hardening_properties.py` - SSH daemon configuration properties
- `tests/property/test_system_updates_properties.py` - Package update properties
- `tests/property/test_tailscale_properties.py` - Tailscale VPN properties
- `tests/property/test_user_properties.py` - User management properties

### Integration Tests
- `tests/integration/` - (empty, ready for integration tests)

### Unit Tests
- `tests/unit/` - (empty, ready for traditional unit tests)

## Adding New Tests

### Property-based unit test
```python
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

@pytest.mark.property
@pytest.mark.unit
@settings(max_examples=100)
@given(value=st.integers())
def test_my_property(value: int):
    # Test implementation
    pass
```

### Integration test
```python
import pytest

@pytest.mark.integration
@pytest.mark.slow
def test_actual_deployment():
    # Test implementation that requires real infrastructure
    pass
```

### Mixed property + integration test
```python
import pytest
from hypothesis import given
from hypothesis import strategies as st

@pytest.mark.property
@pytest.mark.integration
@pytest.mark.slow
@given(config=valid_config())
def test_deployment_property(config):
    # Property test that requires actual system
    pass
```

## CI/CD Optimization

The marker system enables efficient CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - run: make test-unit  # Run fast tests first
  
  integration-tests:
    runs-on: ubuntu-latest
    needs: fast-tests  # Only run if fast tests pass
    steps:
      - run: make test-integration  # Run slow tests later
```

## Best Practices

1. **Mark all tests appropriately** - Every test should have at least one marker
2. **Combine markers when relevant** - A test can be both `@pytest.mark.property` and `@pytest.mark.unit`
3. **Use `unit` for fast tests** - If it doesn't need real infrastructure, mark it as `unit`
4. **Use `integration` for real system tests** - If it needs VMs, containers, or network, mark it as `integration`
5. **Use `slow` for long-running tests** - Help developers and CI systems optimize test runs
6. **Run fast tests during development** - Use `make test-unit` for quick feedback
7. **Run all tests before committing** - Use `make test` to ensure everything passes

## Hypothesis Configuration

Property-based tests use Hypothesis with the following configuration (in `pyproject.toml`):

```toml
[tool.hypothesis]
max_examples = 100
```

This means each property test will run 100 different generated test cases by default. You can override this per-test using `@settings(max_examples=N)`.
