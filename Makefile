.PHONY: help bootstrap verify test test-unit test-property test-integration clean

help:
	@echo "VPS Bootstrap Playbook - Available targets:"
	@echo "  bootstrap          Run the bootstrap playbook"
	@echo "  verify             Run the verification test suite"
	@echo "  test               Run all tests (unit, property, integration)"
	@echo "  test-unit          Run unit tests only"
	@echo "  test-property      Run property-based tests only"
	@echo "  test-integration   Run integration tests only"
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

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
