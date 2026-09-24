# Test Suite Documentation

This project uses pytest markers to organize and run different types of tests efficiently.
The requirements the suite has to meet are in `specs/testing/`; this file is the
how-to. Where the two disagree, the spec wins.

## Available Test Markers

`unit` and `integration` do not overlap, and together they are the whole
suite (TEST-1). The tests `property` selects are *all* also `unit` — it marks
a technique, not a third tier. `slow` currently selects exactly the same tests
as `integration`.

### `@pytest.mark.unit`
Tests that need no target host and no virtual machine (TEST-2). These tests verify logic by reading configuration files and templates without requiring actual system resources.

**Characteristics:**
- Fast execution (typically < 1 second per test)
- No network access required
- No VM, container or target host required
- Tests configuration files, templates, and role structure
- A few run a local external binary: the SSH-keypair tests call `ssh-keygen`,
  and the emergency-script edge-case tests execute the rendered script against
  temporary fixture files with a mocked `systemctl`. Neither reaches a host.

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

Always applied *together with* `unit`: a property test is a unit test that
also generates its inputs. `-m "property and not unit"` selects nothing.

**Characteristics:**
- Generates many test cases automatically
- Tests edge cases and boundary conditions
- Verifies correctness properties across input space

**Caveat, measured:** of the 187 tests in `tests/property/`, only 90 carry a
`@given` decorator at all — the other 97 are ordinary file assertions wearing
the marker. Of those 90, at least 61 never let an assertion depend on what
Hypothesis drew for them, so they run one fixed assertion 50 or 100 times. A
new property test should assert on what it draws (TEST-6); see
`specs/testing/requirements.md` for the measurement and the named cases.

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
- Runs against a Debian VM the suite launches itself (TEST-3), and skips
  rather than fails when Incus is unavailable (TEST-4)

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

**Caveat, measured:** that is the intent, not a description of the suite
today. Both integration modules apply `slow` alongside `integration` in a
module-level `pytestmark` and nothing else uses it, so `slow` and
`integration` select the identical 47 tests. `-m "not slow"` drops the whole
integration tier, not a handful of long tests.

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

# Only slow tests (currently the same 47 tests as -m integration)
uv run pytest -m slow
```

Each `make test-*` target differs from the others by nothing but the marker
expression it passes (TEST-5); `make test` passes none, so it is the only
target that would run a test carrying no tier marker.

## Current Test Organization

- `tests/unit/` - the `unit` tier: tests that need no target host and no
  virtual machine.
- `tests/property/` - tests marked `property`, which are part of the `unit`
  tier rather than a third one (see `@pytest.mark.property` above).
- `tests/integration/` - the `integration` tier: tests that run against a
  Debian VM the suite launches itself.

### Verification Playbook
- `verify_bootstrap.yml` - post-bootstrap checks that `make verify` runs
  against an already bootstrapped host, for example
  `Verify USR-1: manual access user exists with uid 1000`.

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

The marker system would enable efficient CI/CD pipelines. **This repository has
no CI** — there is no `.github/` directory and no workflow file anywhere in it.
The snippet below is an illustration of what the markers make possible, not a
description of anything that runs:

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

Hypothesis's example budget is set per test, by the `@settings()` decorator on
the test itself (TEST-7):

```python
@settings(max_examples=100)
@given(value=st.integers())
def test_my_property(value: int): ...
```

All 90 Hypothesis-driven tests in `tests/property/` carry one — 71 at
`max_examples=100` and 19 at `max_examples=50`. A test with no `@settings()`
would get Hypothesis's own built-in default, which is also 100.

`pyproject.toml` contains a `[tool.hypothesis] max_examples = 100` block. **It
is inert.** Hypothesis 6.151.9 contains no code that reads `pyproject.toml`,
and neither `conftest.py` in this repository registers or loads a settings
profile. The block sets nothing; it is left in place, annotated, because its
value coincides with the library default and removing it changes no behaviour
either way. Edit the decorators, not that block.

## Requirements Traceability

`specs/_traceability.md` maps each requirement to the files that cite its ID.
`make spec-check` regenerates it, and `make test-unit` fails when the
committed copy is out of date. This file is not scanned for citations, so an
ID written here is not a citation and this file is never listed in that index.
