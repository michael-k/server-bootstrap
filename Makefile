.PHONY: help bootstrap verify test test-unit test-property test-integration clean python-lint python-lint-fix ansible-lint ansible-lint-fix

help:
	@echo "VPS Bootstrap Playbook - Available targets:"
	@echo "  bootstrap          Run the bootstrap playbook"
	@echo "  verify             Run the verification test suite"
	@echo "  test               Run all tests (unit, property, integration)"
	@echo "  test-unit          Run unit tests only"
	@echo "  test-property      Run property-based tests only"
	@echo "  test-integration   Run integration tests only"
	@echo "  python-lint        Check Python code with ruff"
	@echo "  python-lint-fix    Fix Python code issues with ruff"
	@echo "  ansible-lint       Check Ansible files with ansible-lint"
	@echo "  ansible-lint-fix   Fix Ansible files with ansible-lint"
	@echo "  clean              Remove generated files and caches"

bootstrap:
	@echo "Running VPS bootstrap playbook..."
	uv run ansible-playbook -i inventory/hosts.yml playbook.yml --ask-vault-pass

verify:
	@echo "Running verification test suite..."
	uv run ansible-playbook -i inventory/hosts.yml tests/verify_bootstrap.yml

test:
	@echo "Running all tests..."
	uv run pytest tests/

test-unit:
	@echo "Running unit tests..."
	uv run pytest tests/unit/

test-property:
	@echo "Running property-based tests..."
	uv run pytest tests/property/

test-integration:
	@echo "Running integration tests..."
	uv run pytest tests/integration/

python-lint:
	@echo "Checking Python code with ruff..."
	uv run ruff check tests/

python-lint-fix:
	@echo "Fixing Python code with ruff..."
	uv run ruff check --fix tests/

ansible-lint:
	@echo "Checking Ansible files with ansible-lint..."
	uv run ansible-lint $(ARGS)

ansible-lint-fix:
	@echo "Fixing Ansible files with ansible-lint..."
	uv run ansible-lint --fix $(ARGS)

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
