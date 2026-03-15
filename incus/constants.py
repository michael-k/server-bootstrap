"""Default constants for Incus VM integration testing."""


VM_NAME_PREFIX = "bootstrap-test-"

IMAGE_PREFIX = "images:debian/"

DEFAULT_DEBIAN_VERSION = "13"

VM_READY_TIMEOUT_SECONDS = 120

SSH_CONNECT_TIMEOUT_SECONDS = 10

SSH_POLL_INTERVAL_SECONDS = 2

DEFAULT_TEST_VARS: dict[str, str | int | bool | list[int]] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    # Generated with: openssl passwd -6 -salt testsalt 'TestPassword123!'
    "manual_user_password": (
        "$6$testsalt$5P2FnhrAYcA6OcEmW5HOdQx2s/g5RDF/pjLq9r43iwy.jOyY9Ap0uReLp0zSd"
        "/WR6.609JYtDYaQVnBIlY3zG/"
    ),
    "manual_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "deploy_user_name": "ansible",
    "deploy_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "ssh_port": 22,
    "target_hostname": "bootstrap-test",
    "port_knocking_sequence": [7000, 8500, 9100],
    "tailscale_enabled": False,
    "swap_enabled": False,
    # Login policy defaults (must match roles/users/defaults/main.yml)
    "login_policy_umask": "027",
    "login_policy_retries": 3,
    "login_policy_timeout": 30,
    # PAM hardening defaults (must match roles/users/defaults/main.yml)
    "pam_faillock_deny": 5,
}
