Provide an ansible playbook that prepares a fresh VPS for regular
Ansible management. This playbook is run once, manually, against a
brand-new server — typically using the root password or initial SSH
key provided by the VPS provider. It must:

1. **Create a dedicated user for manual access** with sudo privileges
   and a password.
   - sudo must be available when accessing the machine directly, eg.
     via a KVM console.
   - The user must have access to the host via SSH with key
     authentication.
   - The user must have the uid 1000.
   - The username must be configurable.
   - The password shall be provided during workflow run.
2. **Create a dedicated Ansible user** with sudo privileges and no
   password (sudo via SSH key only).
   - The ansible user must have the uid 1999.
   - The username must be configurable.
3. **Deploy the operator's SSH public keys** to the users'
   `authorized_keys`. The public key path should be a variable per
   user.
4. **Harden SSHD**:
   - Disable password authentication.
   - Disable root login.
   - Restrict authentication to public key only.
   - Restrict key exchange algorithms to modern curves.
   - Restrict ciphers to authenticated encryption only.
   - Restrict MACs to ETM variants.
   - Disable X11 forwarding, TCP forwarding, agent forwarding, and
     tunneling.
   - Restrict SSH access to the two dedicated users only
     (`AllowUsers`).
   - Let SSH listen on a custom port, if defined, instead of the
     default port 22.
   - Other configurations that make SSH more secure.
5. **If activated, install and configure Tailscale**:
   - Install the Tailscale package from the official repository.
   - Authenticate to the tailnet using a pre-auth key (stored in vault).
   - The solution must work with a custom control server (headscale).
   - Enable and start the Tailscale service.
6. **If tailscale is activated, restrict SSH to the Tailscale
   interface only**: Once Tailscale is up and confirmed working,
   reconfigure SSHD to listen only on the Tailscale IP address (not on
   the public interface). This means that after bootstrap completes,
   all subsequent Ansible runs and manual SSH access must go through
   the tailnet.
7. **Set the hostname** to `server_hostname`, if configured.
8. **Run basic apt update/upgrade** to bring the system to current
   patch level.
9. **Firewall**: Configure nftables (not UFW, not iptables) to allow
   only the necessary ports, for both IPv4 and IPv6. If tailscale is
   configured, SSH's port must be restricted to tailscale's interface.
10. **If tailscale is activated, deploy a script that removes SSH
   restrictions.**
   - The script should be in /root/.
   - When invoked, it must configure SSH and the firewall so that SSH
     is accessible via the public interface.
   - The scripts purpose is to open SSH via a KVM console in case of
     issues with tailscale.
   - The script should accept an argument to put the restrictions back
     in place. When running that script first without that argument
     and then again with that argument, the original state must be
     restored.
   - The script should be idempotent (safe to re-run).
11. **Create a test suite** that verifies that
    - the server is configured correctly,
    - that SSH is secured, and
    - that no additional ports are open.
12. Add a readme with concise instructions
    - which ansible variables to set,
    - how to create secrets (eg. SSH keys)
    - how to manage secrets in vault,
    - how to run the playbook, and
    - how to run the tests.

The playbook can assume that the target machines are all running
Debian stable.

The bootstrap playbook must be designed to be run exactly once. It
should be idempotent (safe to re-run), but the README must clearly
document that this is the initial setup step and other playbooks
should take over afterwards.

The project should have a `pyproject.toml` and a `Makefile`. The
`Makefile` should use `uv run ansible-playbook -i … ….yml` and
`uv run ansible-vault` internally.
