# Login Policy Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden system-wide login defaults with shell idle timeout (TMOUT), console TTY restrictions (/etc/securetty), and tighter /etc/login.defs settings.

**Architecture:** Extend the existing `users` role with three new templates (shell-timeout.sh.j2, securetty.j2, login.defs.j2) and four new tasks. All configurable values flow through role defaults. Property tests validate templates before deployment.

**Tech Stack:** Ansible (templates, lineinfile), Pytest + Hypothesis (property tests), Jinja2

**Spec:** `docs/superpowers/specs/2026-03-12-login-policy-design.md`

---

## Chunk 1: Defaults and Templates

### Task 1: Add Login Policy Defaults

**Files:**
- Modify: `roles/users/defaults/main.yml`
- Test: `tests/property/test_login_policy_properties.py`

- [ ] **Step 1: Write the failing test**

Create `tests/property/test_login_policy_properties.py`:

```python
"""
Property-based tests for login policy hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the login policy templates
and the users role tasks that deploy login hardening.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


class TestLoginPolicyDefaults:
    """Property-based tests for login policy default variables."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_tmout(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define TMOUT

        The users role defaults SHALL define login_policy_tmout.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        assert defaults_path.exists(), "Users defaults must exist"

        content = defaults_path.read_text()

        assert "login_policy_tmout:" in content, (
            "login_policy_tmout must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_umask(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define UMASK

        The users role defaults SHALL define login_policy_umask.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "login_policy_umask:" in content, (
            "login_policy_umask must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_retries(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Login Retries

        The users role defaults SHALL define login_policy_retries.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "login_policy_retries:" in content, (
            "login_policy_retries must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_timeout(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Login Timeout

        The users role defaults SHALL define login_policy_timeout.

        Validates: Login policy hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "login_policy_timeout:" in content, (
            "login_policy_timeout must be defined in defaults"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — `login_policy_tmout` not found in defaults

- [ ] **Step 3: Add login policy defaults**

Append to `roles/users/defaults/main.yml` after line 27 (`sudo_timestamp_timeout: 5`):

```yaml

# Login policy hardening
login_policy_tmout: 600
login_policy_umask: "027"
login_policy_retries: 3
login_policy_timeout: 30
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS — all 4 defaults tests pass

- [ ] **Step 5: Lint**

Run: `make python-lint && make ansible-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/defaults/main.yml tests/property/test_login_policy_properties.py
git commit -m "feat: add login policy hardening defaults and initial property tests"
```

---

### Task 2: Create Shell Timeout Template

**Files:**
- Create: `roles/users/templates/shell-timeout.sh.j2`
- Modify: `tests/property/test_login_policy_properties.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/property/test_login_policy_properties.py`:

```python


class TestShellTimeoutProperties:
    """Property-based tests for shell idle timeout configuration."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_shell_timeout_sets_tmout_variable(self):
        """
        Feature: vps-bootstrap-playbook, Shell Timeout Sets TMOUT

        The shell timeout template SHALL set the TMOUT variable
        using the login_policy_tmout variable.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/shell-timeout.sh.j2")
        assert template_path.exists(), "Shell timeout template must exist"

        content = template_path.read_text()

        assert "TMOUT=" in content, "Template must set TMOUT"
        assert "login_policy_tmout" in content, (
            "TMOUT must use login_policy_tmout variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_shell_timeout_is_readonly(self):
        """
        Feature: vps-bootstrap-playbook, Shell Timeout Is Readonly

        The shell timeout template SHALL mark TMOUT as readonly
        to prevent users from disabling the timeout.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/shell-timeout.sh.j2")
        content = template_path.read_text()

        assert "readonly TMOUT" in content, (
            "TMOUT must be marked readonly"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_shell_timeout_is_exported(self):
        """
        Feature: vps-bootstrap-playbook, Shell Timeout Is Exported

        The shell timeout template SHALL export TMOUT so it applies
        to child shells.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/shell-timeout.sh.j2")
        content = template_path.read_text()

        assert "export TMOUT" in content, (
            "TMOUT must be exported"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — shell-timeout.sh.j2 does not exist

- [ ] **Step 3: Create the template**

Create `roles/users/templates/shell-timeout.sh.j2`:

```bash
# Shell idle timeout — deployed by Ansible
# Logs out idle interactive shells after the configured timeout.
# Only affects shells waiting at the prompt, not running commands.
TMOUT={{ login_policy_tmout }}
readonly TMOUT
export TMOUT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/templates/shell-timeout.sh.j2 tests/property/test_login_policy_properties.py
git commit -m "feat: add shell idle timeout template (TMOUT)"
```

---

### Task 3: Create Securetty Template

**Files:**
- Create: `roles/users/templates/securetty.j2`
- Modify: `tests/property/test_login_policy_properties.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/property/test_login_policy_properties.py`:

```python


@st.composite
def virtual_console_tty(draw):
    """Generate one of the expected virtual console TTYs."""
    return draw(st.sampled_from(["tty1", "tty2", "tty3", "tty4", "tty5", "tty6"]))


@st.composite
def serial_console_tty(draw):
    """Generate one of the expected serial console TTYs."""
    return draw(st.sampled_from(["ttyS0", "ttyS1"]))


class TestSecurettyProperties:
    """Property-based tests for console TTY restrictions."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tty=virtual_console_tty(),
    )
    def test_securetty_lists_virtual_console_ttys(
        self,
        tty: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Securetty Virtual Console TTYs

        The securetty template SHALL list tty1 through tty6
        for KVM/physical console access.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/securetty.j2")
        assert template_path.exists(), "Securetty template must exist"

        content = template_path.read_text()

        # Check for the TTY as a whole line (not substring of another word)
        lines = [line.strip() for line in content.split("\n")]
        assert tty in lines, (
            f"Securetty must list {tty} for virtual console access"
        )

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        tty=serial_console_tty(),
    )
    def test_securetty_lists_serial_console_ttys(
        self,
        tty: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Securetty Serial Console TTYs

        The securetty template SHALL list ttyS0 and ttyS1
        for serial console access.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/securetty.j2")
        content = template_path.read_text()

        lines = [line.strip() for line in content.split("\n")]
        assert tty in lines, (
            f"Securetty must list {tty} for serial console access"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_securetty_does_not_list_pseudo_terminals(self):
        """
        Feature: vps-bootstrap-playbook, Securetty No Pseudo-Terminals

        The securetty template SHALL NOT contain pts/ entries.
        Root should not be able to log in via pseudo-terminals.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/securetty.j2")
        content = template_path.read_text()

        assert "pts/" not in content, (
            "Securetty must NOT list pseudo-terminal entries (pts/)"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — securetty.j2 does not exist

- [ ] **Step 3: Create the template**

Create `roles/users/templates/securetty.j2`:

```
# Console TTY restrictions — deployed by Ansible
# Only listed TTYs allow root login. pam_securetty.so enforces this.

# Virtual console TTYs (KVM/physical console)
tty1
tty2
tty3
tty4
tty5
tty6

# Serial console TTYs (some hosters use serial instead of VT)
ttyS0
ttyS1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/templates/securetty.j2 tests/property/test_login_policy_properties.py
git commit -m "feat: add securetty template for console TTY restrictions"
```

---

### Task 4: Create login.defs Template

**Files:**
- Create: `roles/users/templates/login.defs.j2`
- Modify: `tests/property/test_login_policy_properties.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/property/test_login_policy_properties.py`:

```python


@st.composite
def hardened_login_defs_setting(draw):
    """Generate one of the hardened login.defs settings with expected values."""
    return draw(
        st.sampled_from(
            [
                ("UMASK", "login_policy_umask"),
                ("LOGIN_RETRIES", "login_policy_retries"),
                ("LOGIN_TIMEOUT", "login_policy_timeout"),
            ]
        )
    )


class TestLoginDefsProperties:
    """Property-based tests for /etc/login.defs template."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        setting=hardened_login_defs_setting(),
    )
    def test_login_defs_has_hardened_settings(
        self,
        setting: tuple,
    ):
        """
        Feature: vps-bootstrap-playbook, login.defs Hardened Settings

        The login.defs template SHALL contain all hardened settings
        using their corresponding configurable variables.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        assert template_path.exists(), "login.defs template must exist"

        content = template_path.read_text()

        setting_name, variable_name = setting
        assert setting_name in content, (
            f"login.defs must contain {setting_name}"
        )
        assert variable_name in content, (
            f"{setting_name} must use {variable_name} variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_enables_ok_login_logging(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Successful Login Logging

        The login.defs template SHALL set LOG_OK_LOGINS to yes
        to log successful console logins.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        # Find the LOG_OK_LOGINS line (not commented)
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("LOG_OK_LOGINS") and not stripped.startswith("#"):
                assert "yes" in stripped, (
                    "LOG_OK_LOGINS must be set to yes"
                )
                return
        pytest.fail("login.defs must contain an uncommented LOG_OK_LOGINS directive")

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_preserves_uid_ranges(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Preserves UID Ranges

        The login.defs template SHALL preserve Debian's default UID
        ranges (UID_MIN 1000, UID_MAX 60000) to avoid breaking user creation.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "UID_MIN" in content, "login.defs must define UID_MIN"
        assert "UID_MAX" in content, "login.defs must define UID_MAX"
        assert "1000" in content, "UID_MIN must be 1000"
        assert "60000" in content, "UID_MAX must be 60000"

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_preserves_encrypt_method(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Preserves Encryption

        The login.defs template SHALL preserve ENCRYPT_METHOD YESCRYPT
        to maintain password hashing compatibility.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "ENCRYPT_METHOD" in content, (
            "login.defs must define ENCRYPT_METHOD"
        )
        assert "YESCRYPT" in content, (
            "ENCRYPT_METHOD must be YESCRYPT"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_login_defs_preserves_home_mode(self):
        """
        Feature: vps-bootstrap-playbook, login.defs Preserves HOME_MODE

        The login.defs template SHALL preserve HOME_MODE 0700
        for secure home directory permissions.

        Validates: Login policy hardening design spec
        """
        template_path = Path("roles/users/templates/login.defs.j2")
        content = template_path.read_text()

        assert "HOME_MODE" in content, "login.defs must define HOME_MODE"
        assert "0700" in content, "HOME_MODE must be 0700"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — login.defs.j2 does not exist

- [ ] **Step 3: Create the template**

Create `roles/users/templates/login.defs.j2`. This is based on the Debian default with four settings changed (UMASK, LOGIN_RETRIES, LOGIN_TIMEOUT, LOG_OK_LOGINS):

```
#
# /etc/login.defs — deployed by Ansible
#
# Based on Debian default (shadow package) with hardened settings.
# See login.defs(5) for documentation.
#

#
# Mail directory
#
MAIL_DIR        /var/mail

#
# Logging
#
# Log failed login attempts with unknown usernames
LOG_UNKFAIL_ENAB    no

# [HARDENED] Log successful logins (Debian default: no)
LOG_OK_LOGINS       yes

#
# Hushlogin — suppress login messages if ~/.hushlogin exists
#
HUSHLOGIN_FILE  .hushlogin

#
# Environment PATH settings
#
# PATH for root (su, login)
ENV_SUPATH  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# PATH for regular users
ENV_PATH    PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games

#
# Terminal permissions
#
TTYPERM     0600

#
# Terminal control characters
#
ERASECHAR   0177
KILLCHAR    025

#
# Home directory permissions for new users
#
HOME_MODE   0700

#
# Password aging (preserved at Debian defaults — password auth is disabled)
#
PASS_MAX_DAYS   99999
PASS_MIN_DAYS   0
PASS_WARN_AGE   7

#
# UID/GID allocation ranges
#
UID_MIN         1000
UID_MAX         60000

GID_MIN         1000
GID_MAX         60000

#
# Subordinate UID/GID ranges (for user namespaces / containers)
#
SUB_UID_MIN     100000
SUB_UID_MAX     600100000
SUB_UID_COUNT   65536

SUB_GID_MIN     100000
SUB_GID_MAX     600100000
SUB_GID_COUNT   65536

#
# Console login security
#
# [HARDENED] Max login attempts before failure (Debian default: 5)
LOGIN_RETRIES   {{ login_policy_retries }}

# [HARDENED] Seconds to complete login (Debian default: 60)
LOGIN_TIMEOUT   {{ login_policy_timeout }}

#
# File creation mask
#
# [HARDENED] Default umask (Debian default: 022 implicit)
# 027 = files rw-r-----, directories rwxr-x---
UMASK       {{ login_policy_umask }}

#
# chfn restrictions
#
CHFN_RESTRICT   rwh

#
# Password encryption method
#
ENCRYPT_METHOD  YESCRYPT

#
# Miscellaneous
#
DEFAULT_HOME    yes
NONEXISTENT     /nonexistent
USERGROUPS_ENAB yes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/templates/login.defs.j2 tests/property/test_login_policy_properties.py
git commit -m "feat: add login.defs template with hardened defaults"
```

---

## Chunk 2: Tasks, Verification, and Documentation

### Task 5: Add Deployment Tasks

**Files:**
- Modify: `roles/users/tasks/main.yml` (append after line 169)

- [ ] **Step 1: Add the four login policy tasks**

Append to `roles/users/tasks/main.yml` after the last sudo hardening task (line 169):

```yaml

# Login Policy Hardening
# Harden login.defs, restrict console TTYs, enforce shell idle timeout

- name: Deploy hardened login.defs
  ansible.builtin.template:
    src: login.defs.j2
    dest: /etc/login.defs
    owner: root
    group: root
    mode: "0644"
  tags:
    - users
    - login_policy

- name: Ensure pam_securetty is enabled for console login
  ansible.builtin.lineinfile:
    path: /etc/pam.d/login
    regexp: '^\s*#?\s*auth\s+requisite\s+pam_securetty\.so'
    line: "auth       requisite   pam_securetty.so"
    state: present
  tags:
    - users
    - login_policy

- name: Deploy securetty for console TTY restrictions
  ansible.builtin.template:
    src: securetty.j2
    dest: /etc/securetty
    owner: root
    group: root
    mode: "0600"
  tags:
    - users
    - login_policy

- name: Deploy shell idle timeout
  ansible.builtin.template:
    src: shell-timeout.sh.j2
    dest: /etc/profile.d/shell-timeout.sh
    owner: root
    group: root
    mode: "0644"
  tags:
    - users
    - login_policy
```

**Note on pam_securetty regexp:** Debian's `/etc/pam.d/login` uses `auth requisite pam_securetty.so` (not `required`). The `requisite` keyword is correct — it immediately rejects the login if the TTY is not listed, without trying further PAM modules.

- [ ] **Step 2: Add property tests for tasks file**

Append to `tests/property/test_login_policy_properties.py`:

```python


class TestLoginPolicyTasksProperties:
    """Property-based tests for login policy deployment tasks."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_login_defs(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy login.defs

        The users role tasks SHALL deploy the login.defs template.

        Validates: Login policy hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        assert tasks_path.exists(), "Users tasks must exist"

        content = tasks_path.read_text()

        assert "login.defs.j2" in content, (
            "Tasks must reference login.defs.j2 template"
        )
        assert "dest: /etc/login.defs" in content, (
            "Tasks must deploy to /etc/login.defs"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_securetty(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy securetty

        The users role tasks SHALL deploy the securetty template.

        Validates: Login policy hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "securetty.j2" in content, (
            "Tasks must reference securetty.j2 template"
        )
        assert "dest: /etc/securetty" in content, (
            "Tasks must deploy to /etc/securetty"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_shell_timeout(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy Shell Timeout

        The users role tasks SHALL deploy the shell timeout template
        to /etc/profile.d/.

        Validates: Login policy hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "shell-timeout.sh.j2" in content, (
            "Tasks must reference shell-timeout.sh.j2 template"
        )
        assert "dest: /etc/profile.d/shell-timeout.sh" in content, (
            "Tasks must deploy to /etc/profile.d/shell-timeout.sh"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_ensure_pam_securetty(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Ensure pam_securetty

        The users role tasks SHALL ensure pam_securetty.so is enabled
        in /etc/pam.d/login.

        Validates: Login policy hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "pam_securetty" in content, (
            "Tasks must reference pam_securetty.so"
        )
        assert "/etc/pam.d/login" in content, (
            "Tasks must target /etc/pam.d/login"
        )
        assert "ansible.builtin.lineinfile:" in content, (
            "Tasks must use lineinfile module for pam_securetty"
        )
```

- [ ] **Step 3: Lint**

Run: `make ansible-lint && make python-lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add roles/users/tasks/main.yml tests/property/test_login_policy_properties.py
git commit -m "feat: add login policy hardening tasks and task property tests"
```

---

### Task 6: Add Verification Checks

**Files:**
- Modify: `tests/verify_bootstrap.yml` (add before FINAL SUMMARY section)

- [ ] **Step 1: Add verification block**

Insert before the `# FINAL SUMMARY` section (before line 885) in `tests/verify_bootstrap.yml`:

```yaml
    # ==============================================================================
    # LOGIN POLICY HARDENING VERIFICATION
    # ==============================================================================

    - name: "Verify login.defs hardening"
      block:
        - name: Read login.defs
          ansible.builtin.slurp:
            path: /etc/login.defs
          register: login_defs_content

        - name: Verify hardened login.defs settings
          ansible.builtin.assert:
            that:
              - login_defs_content.content | b64decode is search('UMASK.*027')
              - login_defs_content.content | b64decode is search('LOGIN_RETRIES.*3')
              - login_defs_content.content | b64decode is search('LOGIN_TIMEOUT.*30')
              - login_defs_content.content | b64decode is search('LOG_OK_LOGINS.*yes')
            fail_msg: "login.defs hardening is missing or incomplete"
            success_msg: "✓ login.defs is hardened (UMASK 027, LOGIN_RETRIES 3, LOGIN_TIMEOUT 30, LOG_OK_LOGINS yes)"

    - name: "Verify securetty and shell timeout"
      block:
        - name: Check securetty exists
          ansible.builtin.stat:
            path: /etc/securetty
          register: securetty_file

        - name: Read securetty
          ansible.builtin.slurp:
            path: /etc/securetty
          register: securetty_content
          when: securetty_file.stat.exists

        - name: Check shell timeout exists
          ansible.builtin.stat:
            path: /etc/profile.d/shell-timeout.sh
          register: shell_timeout_file

        - name: Read shell timeout
          ansible.builtin.slurp:
            path: /etc/profile.d/shell-timeout.sh
          register: shell_timeout_content
          when: shell_timeout_file.stat.exists

        - name: Verify securetty and shell timeout
          ansible.builtin.assert:
            that:
              - securetty_file.stat.exists
              - securetty_content.content | b64decode is search('tty1')
              - shell_timeout_file.stat.exists
              - shell_timeout_content.content | b64decode is search('TMOUT')
            fail_msg: "Securetty or shell timeout is missing"
            success_msg: "✓ Securetty deployed, shell timeout active"

```

- [ ] **Step 2: Add login policy to verification summary**

In the summary `debug` message (around line 913), add after the sudo hardening line:

```yaml
              - "  ✓ Login policy hardening (TMOUT, securetty, login.defs)"
```

- [ ] **Step 3: Lint**

Run: `make ansible-lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/verify_bootstrap.yml
git commit -m "test: add login policy hardening verification checks"
```

---

### Task 7: Add Admin Documentation

**Files:**
- Create: `docs/login-policy.md`

- [ ] **Step 1: Create documentation**

Create `docs/login-policy.md`:

```markdown
# Login Policy Hardening

The bootstrap playbook hardens system-wide login defaults. These settings apply to all users and all login methods (SSH and console).

## What It Does

### Shell Idle Timeout (TMOUT)

Interactive shells log out after 10 minutes of idle time at the prompt. This protects unattended console sessions. TMOUT only triggers when the shell waits for input — running commands, tailing logs, or other active work is unaffected.

The timeout is read-only and cannot be disabled by users.

Deployed to: `/etc/profile.d/shell-timeout.sh`

### Console TTY Restrictions

Root can only log in on virtual console TTYs (`tty1`–`tty6`) and serial console TTYs (`ttyS0`–`ttyS1`). This covers standard KVM and serial console access provided by hosting providers.

The manual user is not restricted — they can log in on any TTY and then `su` to root.

Deployed to: `/etc/securetty`

### Hardened login.defs

Four settings are tightened from Debian defaults:

| Setting | Value | Debian Default | Purpose |
|---------|-------|---------------|---------|
| `UMASK` | `027` | `022` | New files: `rw-r-----`, directories: `rwxr-x---` |
| `LOGIN_RETRIES` | `3` | `5` | Max console login attempts (matches SSH MaxAuthTries) |
| `LOGIN_TIMEOUT` | `30` | `60` | Seconds to complete console login (matches SSH LoginGraceTime) |
| `LOG_OK_LOGINS` | `yes` | `no` | Log successful console logins |

Deployed to: `/etc/login.defs`

## Querying Console Login Logs

Console logins log to syslog's AUTH facility, which journald captures:

```bash
# All console login activity
journalctl SYSLOG_IDENTIFIER=login

# Successful console logins today
journalctl SYSLOG_IDENTIFIER=login --since today

# Follow console login logs in real time
journalctl SYSLOG_IDENTIFIER=login -f
```

## Configuration

Override these variables in your inventory or playbook:

```yaml
login_policy_tmout: 600       # Shell idle timeout in seconds
login_policy_umask: "027"     # Default file creation mask
login_policy_retries: 3       # Max console login attempts
login_policy_timeout: 30      # Console login timeout in seconds
```

- [ ] **Step 2: Commit**

```bash
git add docs/login-policy.md
git commit -m "docs: add login policy hardening admin instructions"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run all property tests**

Run: `make test-property`
Expected: All tests pass (125 existing + new login policy tests)

- [ ] **Step 2: Run all tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 3: Run all linters**

Run: `make python-lint && make ansible-lint`
Expected: PASS

- [ ] **Step 4: Review git log**

Run: `git log --oneline -10`
Verify: All commits are present and well-described
