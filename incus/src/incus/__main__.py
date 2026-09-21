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

INCUS-16: ``create``, ``list``, ``destroy`` and ``ssh`` are registered
wherever this module is run, outside every conditional.

INCUS-11: ``publish`` and ``images-clean`` are registered only where the
bootstrap playbook is present.  The guard's subject is the *process's working
directory*: ``Path("site.yml")`` resolves against the CWD, not against this
package and not against a repository root, so the same installation offers
different commands depending on where it was invoked.  What ``publish`` and
``images-clean`` themselves do belongs to IMG, not to INCUS.

IMG-12 is violated and IMG-11 is unenforced, for one structural reason:
nothing between the bootstrap run and ``incus publish`` removes anything from
the machine.  A published image therefore carries the SSH host private keys
and the ``/etc/machine-id`` of the machine it was built on, so every machine
launched from one image offers the same host key -- that is IMG-12, and it is
a violation.  IMG-11 asks for no shell history, and there is very likely none,
because every build command arrives over a non-interactive transport; nothing
in the build enforces it, so it holds by accident and would break silently.
Recorded in specs/image-publishing, not fixed.

Nothing tests this module.  No test in this repository imports it or any of
its ``cmd_*`` functions, and ``make python-typecheck`` reports
``call-non-callable`` on the dispatch at the bottom of ``main()``, because
the two guarded entries are added to ``commands`` after it is annotated
``dict[str, object]``.  Recorded in specs/incus-tooling, not fixed.

INCUS-1 is violated in ``cmd_ssh``, whose two glob patterns spell
``bootstrap-test-`` out literally instead of reading ``VM_NAME_PREFIX`` --
which ``cmd_list`` and ``cmd_destroy`` do read -- so changing that constant
would break ``ssh`` alone.
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

# IMG-13: the one fixed set of bootstrap variables every published image is
# built from.  Nothing reaches it -- no parameter, no environment variable and
# no configuration hook -- which is what lets a consumer read an image's
# guarantees off this project's own requirements.  Two of the fourteen entries
# are read by nothing under roles/, site.yml or inventory/: ``target_hostname``
# (the hostname tasks read ``system_hostname``) and ``swap_enabled`` (the swap
# role is gated on ``zram_enabled`` and ``disk_swap_size``).  Both are inert
# and both are left as found.
#
# IMG-10 is violated by the hash below.  It is a credential that lives in the
# repository, with its plaintext in the comment above it, and roles/users
# writes it to /etc/shadow for an account it also grants unrestricted sudo --
# so it is in every published image, on a path sshd never consults.  Recorded
# in specs/image-publishing, not fixed.
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

# IMG-5: the single namespace every published image shares.  Nothing else
# records that a published image exists, so this prefix is what makes them a
# set -- what a consumer lists by and what ``images-clean`` deletes by.  Note
# that ``BASE_IMAGE_PREFIX`` in constants.py starts with it too, which is why
# IMG-9 records that ``images-clean`` also removes the toolkit's cache.
IMAGE_ALIAS_PREFIX = "bootstrap/"

# IMG-7: one image per variant, built on every run.  There is no argument for
# selecting a subset and nothing is skipped when an image already exists,
# because two images documented as differing in one variable must not be able
# to drift apart across a playbook change.
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
    """Build and publish bootstrapped VM images.

    IMG-1: each variant's machine is published as an image on the local Incus
    daemon once the bootstrap run against it has succeeded.
    """
    version = args.debian

    for variant, variant_vars in IMAGE_VARIANTS.items():
        # IMG-6: the alias carries the variant, so a consumer picks a
        # knock-gated or a directly reachable image by name.
        # IMG-14: it carries the Debian version too, so two releases can sit on
        # one daemon without overwriting each other.
        alias = f"{IMAGE_ALIAS_PREFIX}{variant}-{version}"
        print(f"Building image '{alias}'...")

        # IMG-2: this asks for upstream Debian, but INCUS-2's launch swaps
        # the prefix for the cached bootstrap/internal-base-<version> image --
        # upstream Debian plus openssh-server, curl and ``PermitRootLogin
        # yes``.  That layer, and then wait_ready()'s _setup_ssh below, both
        # configure the machine before the playbook does, so a published image
        # is base layer + readiness wait + playbook, NOT upstream Debian plus
        # the playbook.  Both PermitRootLogin edits are walked back by
        # roles/ssh_hardening; the key _setup_ssh writes is not (IMG-12).
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

            # IMG-2: the bootstrapped state is reached by applying the
            # project's own playbook rather than any substitute for it.  A
            # shortcut that reproduced the same files would be correct only
            # for as long as somebody kept it in step with site.yml, and would
            # fail silently when it stopped being.  What the base layer and
            # wait_ready() put on the machine before this call is not a
            # substitute for the playbook; it is recorded at the image line
            # above and judged by IMG-10 and IMG-12.
            print("  Running bootstrap playbook...")
            result = run_playbook(
                vm,
                playbook_path=Path("site.yml"),
                extra_vars=merged_vars,
                cwd=Path.cwd(),
            )
            # IMG-3: a partially applied playbook is exactly the state that
            # looks bootstrapped and is not, so it publishes nothing.  Raising
            # here also skips the alias deletion below, which is what leaves
            # the previously published image in place, and aborts the loop, so
            # the remaining variants are not built either.
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
            # IMG-4: the build machine never outlives the build.  A ``finally``
            # rather than a success-path call, so it also covers IMG-3's
            # RuntimeError and any failure in the readiness wait, the playbook
            # run, the stop, the alias deletion or the publish.  It does NOT
            # cover the launch: auto_launch=True launches inside IncusVM's
            # __post_init__, so that happens at the construction above, one
            # line before this ``try`` opens, and a failure there leaves ``vm``
            # unbound and destroy() uncalled.  Recorded in
            # specs/image-publishing, not fixed -- moving the construction into
            # the try is a behaviour change.  INCUS-13 force-deletes the
            # machine; INCUS-8 is why this also removes the ephemeral private
            # key from the controller.
            vm.destroy()

    print("All images published.")


def cmd_images_clean(args: argparse.Namespace) -> None:
    """Delete all bootstrap/* images from the local Incus store.

    IMG-9: one command clears the whole publishing namespace, which is the
    only handle there is -- nothing tracks which images a run published.

    It also deletes the toolkit's ``bootstrap/internal-base-<version>`` cache,
    because ``BASE_IMAGE_PREFIX`` starts with ``IMAGE_ALIAS_PREFIX`` and the
    test below is a ``startswith``.  The help string "Delete all bootstrap/*
    images" is literally accurate, which is why that is easy to miss.  The
    cost is a rebuild -- a VM launch and an ``apt-get install`` over the
    network -- on the next launch from an upstream image.
    """
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
        # IMG-8: the Debian version is the caller's choice, so a consumer
        # preparing for the next release does not have to wait for this
        # repository.  Makefile's `images` target always passes one, and the
        # literal it passes is a second, independent copy of this default.
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
