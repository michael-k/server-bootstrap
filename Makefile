.PHONY: help bootstrap verify test test-unit test-property test-integration clean lint python-lint python-lint-fix python-typecheck ansible-lint ansible-lint-fix vm-create vm-list vm-destroy vm-ssh images images-clean

help:
	@echo "VPS Bootstrap Playbook - Available targets:"
	@echo "  bootstrap          Run the bootstrap playbook"
	@echo "  verify             Run the verification test suite"
	@echo "  test               Run all tests (unit, property, integration)"
	@echo "  test-unit          Run unit tests only"
	@echo "  test-property      Run property-based tests only"
	@echo "  test-integration   Run integration tests only"
	@echo "  lint               Run all linters (python-lint, python-typecheck, ansible-lint)"
	@echo "  python-lint        Check Python code with ruff"
	@echo "  python-lint-fix    Fix Python code issues with ruff"
	@echo "  python-typecheck   Type-check Python code with ty"
	@echo "  ansible-lint       Check Ansible files with ansible-lint"
	@echo "  ansible-lint-fix   Fix Ansible files with ansible-lint"
	@echo "  clean              Remove generated files and caches"
	@echo "  vm-create          Create a test VM (DEBIAN=13|testing)"
	@echo "  vm-list            List running test VMs"
	@echo "  vm-destroy         Destroy test VM(s) (VM=name or all)"
	@echo "  vm-ssh             SSH into a test VM (VM=name)"
	@echo "  images             Build bootstrapped VM images for other projects"
	@echo "  images-clean       Delete all bootstrap/* images from Incus"

INVENTORY ?= inventory/hosts.yml
LIMIT ?=
VAULT_PASSWORD_FILE ?=
VAULT_ARGS = $(if $(VAULT_PASSWORD_FILE),--vault-password-file $(VAULT_PASSWORD_FILE),--ask-vault-pass)

bootstrap:
	@echo "Running VPS bootstrap playbook..."
	uv run ansible-playbook -i $(INVENTORY) site.yml $(VAULT_ARGS) $(if $(LIMIT),--limit $(LIMIT))

verify:
	@echo "Running verification test suite..."
	uv run ansible-playbook -i $(INVENTORY) tests/verify_bootstrap.yml $(if $(LIMIT),--limit $(LIMIT))

test:
	@echo "Running all tests..."
	uv run pytest $(ARGS)

test-unit:
	@echo "Running unit tests..."
	uv run pytest -m unit $(ARGS)

test-property:
	@echo "Running property-based tests..."
	uv run pytest -m property $(ARGS)

test-integration:
	@echo "Running integration tests..."
	uv run pytest -m integration $(ARGS)

lint: python-lint python-typecheck ansible-lint

python-lint:
	@echo "Checking Python code with ruff..."
	uv run ruff check tests/ incus/src/

python-lint-fix:
	@echo "Fixing Python code with ruff..."
	uv run ruff check --fix tests/ incus/src/

python-typecheck:
	@echo "Type-checking Python code with ty..."
	uv run ty check

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

images:
	@echo "Building bootstrapped VM images..."
	uv run python -m incus publish --debian $(or $(DEBIAN),13)

images-clean:
	uv run python -m incus images-clean
