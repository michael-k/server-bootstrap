# Sudo Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden sudo configuration with environment sanitization, logging, timeouts, and restrict `su` to wheel group members.

**Architecture:** Extend the existing `users` role with a sudoers security defaults template, wheel group management, and a PAM change for `su`. No new roles.

**Tech Stack:** Ansible, sudoers, PAM (pam_wheel.so), Pytest + Hypothesis.

**Spec:** `docs/superpowers/specs/2026-03-12-sudo-hardening-design.md`

---

## Chunk 1: Users Role Changes

### Task 1: Add sudo hardening default variable

**Files:**
- Modify: `roles/users/defaults/main.yml`

- [ ] **Step 1: Add sudo_timestamp_timeout to defaults**

Append after the last line (line 24, `authorized_keys_mode: "0600"`):

```yaml

# Sudo hardening
sudo_timestamp_timeout: 5
```

- [ ] **Step 2: Verify ansible-lint passes**

Run: `make ansible-lint ARGS="roles/users/"`
Expected: PASS (0 errors)

- [ ] **Step 3: Commit**

```bash
git add roles/users/defaults/main.yml
git commit -m "feat: add sudo timestamp timeout default"
```

---

### Task 2: Create sudo security defaults template

**Files:**
- Create: `roles/users/templates/00-sudo-security.j2`

- [ ] **Step 1: Create the template**

Create `roles/users/templates/00-sudo-security.j2` with this exact content:

```
# Sudo security defaults — deployed by Ansible

# Environment sanitization — prevent LD_PRELOAD, PATH injection
Defaults    env_reset
Defaults    env_clean
Defaults    secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Credential caching
Defaults    timestamp_timeout={{ sudo_timestamp_timeout }}

# Logging — enhance syslog entries (sudo logs to AUTH facility by default,
# which journald captures automatically)
Defaults    log_year
Defaults    log_host

# Security restrictions
Defaults    use_pty
Defaults    requiretty
Defaults:{{ ansible_user_name }}    !requiretty
```

- [ ] **Step 2: Verify ansible-lint passes**

Run: `make ansible-lint ARGS="roles/users/"`
Expected: PASS (0 errors)

- [ ] **Step 3: Commit**

```bash
git add roles/users/templates/00-sudo-security.j2
git commit -m "feat: add sudo security defaults template"
```

---

### Task 3: Add sudo hardening tasks to users role

**Files:**
- Modify: `roles/users/tasks/main.yml`

- [ ] **Step 1: Append new tasks after existing content**

Append the following after the last existing task ("Grant passwordless sudo privileges to Ansible user", ending at line 126):

```yaml

# Sudo Hardening
# Harden sudo with environment sanitization, logging, timeouts, and su restriction

- name: Create wheel group for su restriction
  ansible.builtin.group:
    name: wheel
    state: present
  tags:
    - users
    - sudo

- name: Add manual user to wheel group
  ansible.builtin.user:
    name: "{{ manual_user_name }}"
    groups: wheel
    append: true
  tags:
    - users
    - manual_user
    - sudo

- name: Deploy sudo security defaults
  ansible.builtin.template:
    src: 00-sudo-security.j2
    dest: /etc/sudoers.d/00-sudo-security
    owner: root
    group: root
    mode: "0440"
    validate: "visudo -cf %s"
  tags:
    - users
    - sudo

- name: Restrict su to wheel group members
  ansible.builtin.lineinfile:
    path: /etc/pam.d/su
    regexp: '^\s*#?\s*auth\s+required\s+pam_wheel\.so'
    line: "auth       required   pam_wheel.so"
    state: present
  tags:
    - users
    - sudo
```

- [ ] **Step 2: Verify ansible-lint passes**

Run: `make ansible-lint ARGS="roles/users/"`
Expected: PASS (0 errors)

- [ ] **Step 3: Commit**

```bash
git add roles/users/tasks/main.yml
git commit -m "feat: add sudo hardening and su restriction tasks"
```

---

## Chunk 2: Tests and Documentation

### Task 4: Add property tests

**Files:**
- Create: `tests/property/test_sudo_hardening_properties.py`

- [ ] **Step 1: Create the property test file**

Create `tests/property/test_sudo_hardening_properties.py`:

```python
"""
Property-based tests for sudo hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the sudo security defaults
template and the users role tasks that deploy sudo hardening.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


@st.composite
def sudo_security_directive(draw):
    """Generate one of the required sudo security directives."""
    return draw(
        st.sampled_from(
            ["env_reset", "env_clean", "secure_path", "use_pty", "log_year", "log_host"]
        )
    )


class TestSudoHardeningProperties:
    """Property-based tests for sudo hardening configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        directive=sudo_security_directive(),
    )
    def test_property_63_sudo_template_has_required_directives(
        self,
        directive: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Property 63: Sudo Security Directives

        The sudo security defaults template SHALL contain all required
        hardening directives: env_reset, env_clean, secure_path, use_pty,
        log_year, and log_host.

        Validates: Sudo hardening design spec
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        assert template_path.exists(), "Sudo security template must exist"

        content = template_path.read_text()

        assert directive in content, (
            f"Sudo security template must contain {directive} directive"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_64_sudo_template_has_secure_path(self):
        """
        Feature: vps-bootstrap-playbook, Property 64: Secure PATH

        The sudo security template SHALL define a secure_path containing
        only standard system binary directories.

        Validates: Sudo hardening design spec
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        for directory in [
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
        ]:
            assert directory in content, f"secure_path must include {directory}"

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_65_sudo_template_has_configurable_timeout(self):
        """
        Feature: vps-bootstrap-playbook, Property 65: Configurable Timeout

        The sudo security template SHALL reference the sudo_timestamp_timeout
        variable for credential caching, not a hardcoded value.

        Validates: Sudo hardening design spec
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        assert "sudo_timestamp_timeout" in content, (
            "Timeout must use sudo_timestamp_timeout variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_66_sudo_template_has_requiretty_with_exemption(self):
        """
        Feature: vps-bootstrap-playbook, Property 66: requiretty with Ansible Exemption

        The sudo security template SHALL require a TTY for sudo usage
        AND exempt the ansible user from this requirement.

        Validates: Sudo hardening design spec
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        assert "requiretty" in content, "Template must contain requiretty directive"
        assert "!requiretty" in content, (
            "Template must exempt ansible user from requiretty"
        )
        assert "ansible_user_name" in content, (
            "TTY exemption must reference ansible_user_name variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_67_defaults_define_timeout(self):
        """
        Feature: vps-bootstrap-playbook, Property 67: Defaults Define Timeout

        The users role defaults SHALL define sudo_timestamp_timeout.

        Validates: Sudo hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        assert defaults_path.exists(), "Users defaults must exist"

        content = defaults_path.read_text()

        assert "sudo_timestamp_timeout:" in content, (
            "sudo_timestamp_timeout must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_68_tasks_create_wheel_group(self):
        """
        Feature: vps-bootstrap-playbook, Property 68: Tasks Create Wheel Group

        The users role tasks SHALL create the wheel group for su restriction.

        Validates: Sudo hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        assert tasks_path.exists(), "Users tasks must exist"

        content = tasks_path.read_text()

        assert "wheel" in content, "Tasks must reference wheel group"
        assert "ansible.builtin.group:" in content, (
            "Tasks must use group module to create wheel"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_69_tasks_enable_pam_wheel(self):
        """
        Feature: vps-bootstrap-playbook, Property 69: Tasks Enable pam_wheel

        The users role tasks SHALL enable pam_wheel.so in /etc/pam.d/su.

        Validates: Sudo hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "pam_wheel" in content, (
            "Tasks must reference pam_wheel.so"
        )
        assert "/etc/pam.d/su" in content, (
            "Tasks must target /etc/pam.d/su"
        )
        assert "ansible.builtin.lineinfile:" in content, (
            "Tasks must use lineinfile module for pam_wheel"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_70_tasks_deploy_sudoers_with_validation(self):
        """
        Feature: vps-bootstrap-playbook, Property 70: Sudoers Deployed with Validation

        The sudo security defaults file SHALL be deployed using the template
        module with visudo validation to prevent syntax errors from breaking sudo.

        Validates: Sudo hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "00-sudo-security" in content, (
            "Tasks must deploy 00-sudo-security file"
        )
        assert "visudo" in content, (
            "Sudoers file must be validated with visudo"
        )
        assert "ansible.builtin.template:" in content, (
            "Sudo security defaults must use template module"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_property_71_no_logfile_directive(self):
        """
        Feature: vps-bootstrap-playbook, Property 71: No logfile Directive

        The sudo security template SHALL NOT contain a logfile directive.
        Sudo logs to syslog (AUTH facility) by default, which journald captures.
        A separate logfile is redundant.

        Validates: Sudo hardening design spec
        """
        template_path = Path("roles/users/templates/00-sudo-security.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("Defaults") and "logfile" in stripped:
                pytest.fail(
                    "Template must NOT contain a logfile directive — "
                    "sudo logs to syslog/journald by default"
                )
```

- [ ] **Step 2: Run property tests**

Run: `make test-property`
Expected: PASS — all tests including new sudo hardening tests

- [ ] **Step 3: Run python linting**

Run: `make python-lint`
Expected: PASS (0 errors)

- [ ] **Step 4: Commit**

```bash
git add tests/property/test_sudo_hardening_properties.py
git commit -m "test: add sudo hardening property tests"
```

---

### Task 5: Add verification checks

**Files:**
- Modify: `tests/verify_bootstrap.yml`

- [ ] **Step 1: Add sudo hardening verification blocks**

Insert after the existing "Test 14.4: Verify Ansible user has passwordless sudo privileges" block (around line 103) and before the SSH CONFIGURATION VERIFICATION section header:

```yaml

    # ==============================================================================
    # SUDO HARDENING VERIFICATION
    # ==============================================================================

    - name: "Verify sudo security defaults are deployed"
      block:
        - name: Check sudo security defaults file exists
          ansible.builtin.stat:
            path: /etc/sudoers.d/00-sudo-security
          register: sudo_security_file

        - name: Read sudo security defaults
          ansible.builtin.slurp:
            path: /etc/sudoers.d/00-sudo-security
          register: sudo_security_content
          when: sudo_security_file.stat.exists

        - name: Verify sudo security directives
          ansible.builtin.assert:
            that:
              - sudo_security_file.stat.exists
              - sudo_security_content.content | b64decode is search('env_reset')
              - sudo_security_content.content | b64decode is search('secure_path')
              - sudo_security_content.content | b64decode is search('use_pty')
              - sudo_security_content.content | b64decode is search('requiretty')
            fail_msg: "Sudo security defaults are missing or incomplete"
            success_msg: "✓ Sudo security defaults are properly configured"

    - name: "Verify wheel group and su restriction"
      block:
        - name: Check wheel group exists
          ansible.builtin.command: getent group wheel
          register: wheel_group
          changed_when: false

        - name: Check manual user is in wheel group
          ansible.builtin.command: "id -nG {{ manual_user_name }}"
          register: manual_user_groups_check
          changed_when: false

        - name: Check pam_wheel is enabled
          ansible.builtin.command: grep -E '^\s*auth\s+required\s+pam_wheel\.so' /etc/pam.d/su
          register: pam_wheel_check
          changed_when: false

        - name: Verify wheel group and su restriction
          ansible.builtin.assert:
            that:
              - wheel_group.rc == 0
              - "'wheel' in manual_user_groups_check.stdout"
              - pam_wheel_check.rc == 0
            fail_msg: "Wheel group or su restriction is not properly configured"
            success_msg: "✓ Wheel group exists, manual user is a member, su restricted to wheel"
```

- [ ] **Step 2: Update the verification summary**

Find the verification summary task (the one that lists all verified items) and add a line for sudo hardening. After the line `"  ✓ User accounts and sudo privileges"`, add:

```
              - "  ✓ Sudo hardening (env sanitization, logging, timeouts, su restriction)"
```

- [ ] **Step 3: Verify ansible-lint passes**

Run: `make ansible-lint`
Expected: PASS (0 errors)

- [ ] **Step 4: Commit**

```bash
git add tests/verify_bootstrap.yml
git commit -m "test: add sudo hardening verification checks"
```

---

### Task 6: Create admin documentation

**Files:**
- Create: `docs/sudo-hardening.md`

- [ ] **Step 1: Write the documentation**

Create `docs/sudo-hardening.md`:

```markdown
# Sudo Hardening

The bootstrap playbook applies security defaults to sudo and restricts `su` to members of the `wheel` group.

## What Gets Configured

### Sudo Security Defaults

Deployed to `/etc/sudoers.d/00-sudo-security`:

- **Environment sanitization** — `env_reset` and `env_clean` strip dangerous variables (LD_PRELOAD, PATH injection). `secure_path` hardcodes PATH to system directories.
- **Credential caching** — `timestamp_timeout=5` re-prompts for the password after 5 minutes of inactivity. Only affects the manual user (the ansible user has passwordless sudo).
- **Logging** — `log_year` and `log_host` enhance syslog entries with the year and hostname. Sudo logs to syslog's AUTH facility by default, which journald captures.
- **PTY allocation** — `use_pty` allocates a pseudo-terminal for all sudo commands.
- **TTY requirement** — `requiretty` requires a real terminal for sudo. The ansible user is exempted so that Ansible's `become: true` continues to work.

### `su` Restriction

Only members of the `wheel` group can use `su`. The manual user is added to `wheel`; the ansible user is not.

## Querying Sudo Logs

Sudo logs to journald via syslog's AUTH facility:

```bash
# All sudo activity
journalctl SYSLOG_IDENTIFIER=sudo

# Today's sudo activity
journalctl SYSLOG_IDENTIFIER=sudo --since today

# Sudo activity by a specific user
journalctl SYSLOG_IDENTIFIER=sudo _COMM=sudo | grep "admin"

# Follow sudo logs in real time
journalctl SYSLOG_IDENTIFIER=sudo -f
```

## Customizing the Timeout

Edit `sudo_timestamp_timeout` in your inventory:

```yaml
sudo_timestamp_timeout: 10  # 10 minutes instead of the default 5
```

Set to `0` to require the password on every sudo invocation.

## Verifying the Configuration

On the server:

```bash
# Check sudo security defaults
sudo cat /etc/sudoers.d/00-sudo-security

# Check wheel group membership
getent group wheel

# Check su restriction
grep pam_wheel /etc/pam.d/su
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/sudo-hardening.md
git commit -m "docs: add sudo hardening admin instructions"
```

---

### Task 7: Run full test suite and lint

**Files:** None (validation only)

- [ ] **Step 1: Run all property tests**

Run: `make test-property`
Expected: PASS — all tests pass

- [ ] **Step 2: Run python linting**

Run: `make python-lint`
Expected: PASS (0 errors)

- [ ] **Step 3: Run ansible linting on full project**

Run: `make ansible-lint`
Expected: PASS (0 errors)

- [ ] **Step 4: Fix any issues found, then commit**

If failures, fix and commit. If all pass, move to next task.

---

### Task 8: Final review

**Files:** None (review checkpoint)

- [ ] **Step 1: Review all changes**

Run: `git log --oneline` and `git diff HEAD~N` to review all commits.

- [ ] **Step 2: Verify the changes are complete**

Confirm:
- `roles/users/defaults/main.yml` has `sudo_timestamp_timeout`
- `roles/users/templates/00-sudo-security.j2` exists with all directives
- `roles/users/tasks/main.yml` has wheel group, sudo security, and pam_wheel tasks
- `tests/property/test_sudo_hardening_properties.py` has `TestSudoHardeningProperties` class
- `tests/verify_bootstrap.yml` has sudo hardening verification blocks
- `docs/sudo-hardening.md` exists with admin instructions and journalctl queries
