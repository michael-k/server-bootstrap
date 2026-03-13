"""CLI entry point for manual Incus VM management.

Usage:
    uv run python -m tests.infra create [--debian VERSION]
    uv run python -m tests.infra list
    uv run python -m tests.infra destroy <name>
    uv run python -m tests.infra destroy --all
    uv run python -m tests.infra ssh <name>
"""


import argparse
import json
import os
import subprocess
import sys

from tests.infra.constants import DEFAULT_DEBIAN_VERSION, IMAGE_PREFIX, VM_NAME_PREFIX
from tests.infra.vm import IncusVM


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new test VM."""
    image = f"{IMAGE_PREFIX}{args.debian}"
    print(f"Creating VM with image {image}...")
    vm = IncusVM.create(image=image)
    print(f"VM '{vm.name}' launched. Waiting for SSH...")
    vm.wait_ready()
    print(f"VM '{vm.name}' ready.")
    print(f"  IP: {vm.ip_address}")
    print(f"  SSH: ssh -i {vm.ssh_key.private_key_path} root@{vm.ip_address}")
    print(f"  Destroy: make vm-destroy VM={vm.name}")

    # Save VM info for vm-ssh to find later
    info_path = vm.ssh_key.private_key_path.parent / "vm-info.json"
    info_path.write_text(json.dumps({
        "name": vm.name,
        "ip_address": vm.ip_address,
        "ssh_key": str(vm.ssh_key.private_key_path),
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
    import glob
    import tempfile

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

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "destroy": cmd_destroy,
        "ssh": cmd_ssh,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
