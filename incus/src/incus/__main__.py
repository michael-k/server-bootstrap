"""CLI entry point for manual Incus VM management.

Usage:
    uv run python -m incus create [--debian VERSION]
    uv run python -m incus list
    uv run python -m incus destroy <name>
    uv run python -m incus destroy --all
    uv run python -m incus ssh <name>

Bootstrap-specific (only available when site.yml exists):
    uv run python -m incus publish [--debian VERSION]
    uv run python -m incus images-clean
"""


import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from incus.ansible import _get_ssh_public_key_file, run_playbook
from incus.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX, VM_NAME_PREFIX
from incus.vm import IncusVM

# --- Bootstrap-specific constants (only used by guarded commands) ---

_PUBLISH_VARS: dict[str, str | int | bool | list[int]] = {
    "manual_user_name": "testuser",
    # SHA-512 hash of "TestPassword123!" — test-only, not used for real servers
    "manual_user_password": (
        "$6$testsalt$5P2FnhrAYcA6OcEmW5HOdQx2s/g5RDF/pjLq9r43iwy.jOyY9Ap0uReLp0zSd"
        "/WR6.609JYtDYaQVnBIlY3zG/"
    ),
    "manual_user_ssh_key_file": "",  # Set dynamically
    "deploy_user_name": "ansible",
    "deploy_user_ssh_key_file": "",  # Set dynamically
    "ssh_port": 2222,
    "target_hostname": "bootstrap-test",
    "port_knocking_sequence": [7000, 8500, 9100],
    "tailscale_enabled": False,
    "swap_enabled": False,
    "login_policy_umask": "027",
    "login_policy_retries": 3,
    "login_policy_timeout": 30,
    "pam_faillock_deny": 5,
}

IMAGE_ALIAS_PREFIX = "bootstrap/"

IMAGE_VARIANTS: dict[str, dict[str, str | int | bool | list[int]]] = {
    "knocking": {
        "tailscale_enabled": False,
        "firewall_port_knocking_enabled": True,
    },
    "open": {
        "tailscale_enabled": False,
        "firewall_port_knocking_enabled": False,
    },
}

VM_STOP_TIMEOUT_SECONDS = 60


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new test VM."""
    image = f"{IMAGE_PREFIX}{args.debian}"
    print(f"Creating VM with image {image}...")
    vm = IncusVM(image=image, auto_launch=True)
    print(f"VM '{vm.name}' launched. Waiting for SSH...")
    vm.wait_ready()
    print(f"VM '{vm.name}' ready.")
    print(f"  IP: {vm.ip_address}")
    print(f"  SSH: ssh -i {vm.private_key_path} root@{vm.ip_address}")
    print(f"  Destroy: make vm-destroy VM={vm.name}")

    # Save VM info for vm-ssh to find later
    info_path = vm.private_key_path.parent / "vm-info.json"
    info_path.write_text(json.dumps({
        "name": vm.name,
        "ip_address": vm.ip_address,
        "ssh_key": str(vm.private_key_path),
    }))


def cmd_list(args: argparse.Namespace) -> None:
    """List running test VMs."""
    result = subprocess.run(
        ["incus", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    vms = json.loads(result.stdout)
    test_vms = [v for v in vms if v["name"].startswith(VM_NAME_PREFIX)]

    if not test_vms:
        print("No test VMs running.")
        return

    for vm in test_vms:
        status = vm.get("status", "Unknown")
        ip = ""
        network = vm.get("state", {}).get("network", {})
        for iface_name, iface in network.items():
            if iface_name == "lo":
                continue
            for addr in iface.get("addresses", []):
                if addr.get("family") == "inet" and addr.get("scope") == "global":
                    ip = addr["address"]
                    break
        print(f"  {vm['name']}  {status}  {ip}")


def cmd_destroy(args: argparse.Namespace) -> None:
    """Destroy test VM(s)."""
    if args.all:
        result = subprocess.run(
            ["incus", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
        )
        vms = json.loads(result.stdout)
        test_vms = [v for v in vms if v["name"].startswith(VM_NAME_PREFIX)]

        if not test_vms:
            print("No test VMs to destroy.")
            return

        for vm in test_vms:
            name = vm["name"]
            print(f"Destroying {name}...")
            subprocess.run(
                ["incus", "delete", name, "--force"],
                capture_output=True,
                text=True,
                check=False,
            )
        print(f"Destroyed {len(test_vms)} test VM(s).")
    else:
        if not args.name:
            print("Error: specify a VM name or use --all", file=sys.stderr)
            sys.exit(1)
        print(f"Destroying {args.name}...")
        subprocess.run(
            ["incus", "delete", args.name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"Destroyed {args.name}.")


def cmd_ssh(args: argparse.Namespace) -> None:
    """SSH into a test VM."""
    patterns = [
        os.path.join(tempfile.gettempdir(), f"bootstrap-test-{args.name}*", "vm-info.json"),
        os.path.join(tempfile.gettempdir(), f"bootstrap-test-*{args.name}*", "vm-info.json"),
    ]

    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            with open(matches[0]) as f:
                info = json.loads(f.read())
            os.execvp("ssh", [
                "ssh",
                "-o", "PubkeyAuthentication=yes",
                "-o", "StrictHostKeyChecking=no",
                "-i", info["ssh_key"],
                f"root@{info['ip_address']}",
            ])

    # Fallback: use incus exec (works even without saved SSH key)
    print(f"No saved SSH key found for '{args.name}'. Using incus exec instead.")
    os.execvp("incus", ["incus", "exec", args.name, "--", "/bin/bash"])


def _delete_image(alias: str) -> None:
    """Delete an Incus image by alias, if it exists."""
    result = subprocess.run(
        ["incus", "image", "delete", alias],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print(f"  Deleted existing image '{alias}'.")


def _stop_vm(name: str) -> None:
    """Stop a VM, falling back to --force if graceful stop hangs."""
    result = subprocess.run(
        ["incus", "stop", name, f"--timeout={VM_STOP_TIMEOUT_SECONDS}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("  Graceful stop failed, forcing...")
        subprocess.run(
            ["incus", "stop", name, "--force"],
            capture_output=True,
            text=True,
            check=True,
        )


def cmd_publish(args: argparse.Namespace) -> None:
    """Build and publish bootstrapped VM images."""
    version = args.debian

    for variant, variant_vars in IMAGE_VARIANTS.items():
        alias = f"{IMAGE_ALIAS_PREFIX}{variant}-{version}"
        print(f"Building image '{alias}'...")

        image = f"{IMAGE_PREFIX}{version}"
        vm = IncusVM(image=image, name_hint=f"publish-{variant}", auto_launch=True)
        try:
            print(f"  Waiting for VM '{vm.name}'...")
            vm.wait_ready()

            pub_key_path = _get_ssh_public_key_file(vm)
            merged_vars = dict(_PUBLISH_VARS)
            merged_vars["manual_user_ssh_key_file"] = str(pub_key_path)
            merged_vars["deploy_user_ssh_key_file"] = str(pub_key_path)
            merged_vars.update(variant_vars)

            print("  Running bootstrap playbook...")
            result = run_playbook(
                vm,
                playbook_path=Path("site.yml"),
                extra_vars=merged_vars,
                cwd=Path.cwd(),
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Bootstrap failed for '{variant}'.\n"
                    f"stdout: {result.stdout[-3000:]}\n"
                    f"stderr: {result.stderr[-1000:]}"
                )

            print("  Stopping VM...")
            _stop_vm(vm.name)

            _delete_image(alias)

            print(f"  Publishing as '{alias}'...")
            subprocess.run(
                ["incus", "publish", vm.name, f"--alias={alias}"],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"  Published '{alias}'.")
        except Exception:
            print(f"  Error building '{variant}', cleaning up VM...")
            raise
        finally:
            vm.destroy()

    print("All images published.")


def cmd_images_clean(args: argparse.Namespace) -> None:
    """Delete all bootstrap/* images from the local Incus store."""
    result = subprocess.run(
        ["incus", "image", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    images = json.loads(result.stdout)
    deleted = 0
    for img in images:
        for a in img.get("aliases", []):
            if a.get("name", "").startswith(IMAGE_ALIAS_PREFIX):
                subprocess.run(
                    ["incus", "image", "delete", img["fingerprint"]],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                print(f"  Deleted {a['name']}")
                deleted += 1
                break
    if deleted:
        print(f"Deleted {deleted} image(s).")
    else:
        print("No bootstrap images found.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Incus VMs for integration testing",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new test VM")
    p_create.add_argument(
        "--debian", default=DEFAULT_DEBIAN_VERSION,
        help=f"Debian version (default: {DEFAULT_DEBIAN_VERSION})",
    )

    # list
    subparsers.add_parser("list", help="List running test VMs")

    # destroy
    p_destroy = subparsers.add_parser("destroy", help="Destroy test VM(s)")
    p_destroy.add_argument("name", nargs="?", help="VM name to destroy")
    p_destroy.add_argument("--all", action="store_true", help="Destroy all test VMs")

    # ssh
    p_ssh = subparsers.add_parser("ssh", help="SSH into a test VM")
    p_ssh.add_argument("name", help="VM name")

    commands: dict[str, object] = {
        "create": cmd_create,
        "list": cmd_list,
        "destroy": cmd_destroy,
        "ssh": cmd_ssh,
    }

    # Bootstrap-specific commands — only available when site.yml exists
    if Path("site.yml").exists():
        p_publish = subparsers.add_parser(
            "publish", help="Build and publish bootstrapped VM images",
        )
        p_publish.add_argument(
            "--debian", default=DEFAULT_DEBIAN_VERSION,
            help=f"Debian version (default: {DEFAULT_DEBIAN_VERSION})",
        )
        subparsers.add_parser("images-clean", help="Delete all bootstrap/* images")
        commands["publish"] = cmd_publish
        commands["images-clean"] = cmd_images_clean

    args = parser.parse_args()
    commands[args.command](args)


if __name__ == "__main__":
    main()
