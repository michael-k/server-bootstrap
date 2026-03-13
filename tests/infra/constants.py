"""Default constants for Incus VM integration testing."""


VM_NAME_PREFIX = "bootstrap-test-"

IMAGE_PREFIX = "images:debian/"

DEFAULT_DEBIAN_VERSION = "13"

VM_READY_TIMEOUT_SECONDS = 120

SSH_CONNECT_TIMEOUT_SECONDS = 10

SSH_POLL_INTERVAL_SECONDS = 2

DEFAULT_TEST_VARS: dict[str, str | int | bool] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    "manual_user_password": (
        "$6$rounds=656000$testsalt$KiWOExmGav5tkvgH6hLZmBGbrNMmGrinaOwrUUmXFcQmBxJmBLXd"
        "MOFwlVYpXqBERvMOmflOBxVGHfnYBvFYX."
    ),
    "manual_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "deploy_user_name": "ansible",
    "deploy_user_ssh_key_file": "",  # Set dynamically from VM's SSH key
    "ssh_port": 22,
    "target_hostname": "bootstrap-test",
    "tailscale_enabled": False,
    "swap_enabled": False,
}
