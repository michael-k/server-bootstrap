# PAM Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden PAM with pam_faillock (account lockout after failed login attempts) and pam_limits (nproc, nofile, core resource limits).

**Architecture:** Extend the existing `users` role with two new config templates (faillock.conf.j2, 50-hardening.conf.j2), one PAM profile template (faillock-pam-config.j2), and four new tasks. pam_faillock uses Debian's `pam-auth-update` mechanism for safe PAM stack integration. pam_limits uses a drop-in file in `/etc/security/limits.d/`.

**Tech Stack:** Ansible (templates, command), Pytest + Hypothesis (property tests), Jinja2

**Spec:** `docs/superpowers/specs/2026-03-12-pam-hardening-design.md`

---

## Chunk 1: Defaults and Templates

### Task 1: Add PAM Hardening Defaults

**Files:**
- Modify: `roles/users/defaults/main.yml`
- Create: `tests/property/test_pam_hardening_properties.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/property/test_pam_hardening_properties.py`:

```python
"""
Property-based tests for PAM hardening in VPS Bootstrap Playbook.

These tests verify universal properties about the PAM hardening templates
and the users role tasks that deploy pam_faillock and pam_limits.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


class TestPamHardeningDefaults:
    """Property-based tests for PAM hardening default variables."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_faillock_deny(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Faillock Deny

        The users role defaults SHALL define pam_faillock_deny.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        assert defaults_path.exists(), "Users defaults must exist"

        content = defaults_path.read_text()

        assert "pam_faillock_deny:" in content, (
            "pam_faillock_deny must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_faillock_unlock_time(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Faillock Unlock Time

        The users role defaults SHALL define pam_faillock_unlock_time.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_faillock_unlock_time:" in content, (
            "pam_faillock_unlock_time must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_faillock_fail_interval(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Faillock Fail Interval

        The users role defaults SHALL define pam_faillock_fail_interval.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_faillock_fail_interval:" in content, (
            "pam_faillock_fail_interval must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nproc(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nproc

        The users role defaults SHALL define pam_limits_nproc.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nproc:" in content, (
            "pam_limits_nproc must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nproc_root(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nproc Root

        The users role defaults SHALL define pam_limits_nproc_root.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nproc_root:" in content, (
            "pam_limits_nproc_root must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nofile(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nofile

        The users role defaults SHALL define pam_limits_nofile.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nofile:" in content, (
            "pam_limits_nofile must be defined in defaults"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_defaults_define_limits_nofile_root(self):
        """
        Feature: vps-bootstrap-playbook, Defaults Define Limits Nofile Root

        The users role defaults SHALL define pam_limits_nofile_root.

        Validates: PAM hardening design spec
        """
        defaults_path = Path("roles/users/defaults/main.yml")
        content = defaults_path.read_text()

        assert "pam_limits_nofile_root:" in content, (
            "pam_limits_nofile_root must be defined in defaults"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — pam_faillock_deny not defined in defaults

- [ ] **Step 3: Add defaults**

Append to `roles/users/defaults/main.yml` after the login policy section (after line 33):

```yaml

# PAM hardening — account lockout
pam_faillock_deny: 5
pam_faillock_unlock_time: 600
pam_faillock_fail_interval: 900

# PAM hardening — resource limits
pam_limits_nproc: 1024
pam_limits_nproc_root: 2048
pam_limits_nofile: 4096
pam_limits_nofile_root: 8192
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/defaults/main.yml tests/property/test_pam_hardening_properties.py
git commit -m "feat: add PAM hardening defaults and initial property tests"
```

---

### Task 2: Create faillock.conf Template

**Files:**
- Create: `roles/users/templates/faillock.conf.j2`
- Modify: `tests/property/test_pam_hardening_properties.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/property/test_pam_hardening_properties.py`:

```python


@st.composite
def faillock_configurable_setting(draw):
    """Generate one of the configurable faillock.conf settings."""
    return draw(
        st.sampled_from(
            [
                ("deny", "pam_faillock_deny"),
                ("unlock_time", "pam_faillock_unlock_time"),
                ("fail_interval", "pam_faillock_fail_interval"),
            ]
        )
    )


class TestFaillockConfProperties:
    """Property-based tests for faillock.conf template."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        setting=faillock_configurable_setting(),
    )
    def test_faillock_conf_has_configurable_settings(
        self,
        setting: tuple,
    ):
        """
        Feature: vps-bootstrap-playbook, faillock.conf Configurable Settings

        The faillock.conf template SHALL contain deny, unlock_time, and
        fail_interval using their corresponding configurable variables.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock.conf.j2")
        assert template_path.exists(), "faillock.conf template must exist"

        content = template_path.read_text()

        setting_name, variable_name = setting
        assert setting_name in content, (
            f"faillock.conf must contain {setting_name}"
        )
        assert variable_name in content, (
            f"{setting_name} must use {variable_name} variable"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_faillock_conf_hardcodes_even_deny_root(self):
        """
        Feature: vps-bootstrap-playbook, faillock.conf Even Deny Root

        The faillock.conf template SHALL hardcode even_deny_root = true.
        Root lockout is security policy, not configurable.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock.conf.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("even_deny_root") and not stripped.startswith("#"):
                assert "true" in stripped, (
                    "even_deny_root must be set to true"
                )
                return
        pytest.fail("faillock.conf must contain an uncommented even_deny_root directive")

    @pytest.mark.property
    @pytest.mark.unit
    def test_faillock_conf_has_root_unlock_time(self):
        """
        Feature: vps-bootstrap-playbook, faillock.conf Root Unlock Time

        The faillock.conf template SHALL set root_unlock_time using the
        pam_faillock_unlock_time variable (same as regular users).

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock.conf.j2")
        content = template_path.read_text()

        assert "root_unlock_time" in content, (
            "faillock.conf must contain root_unlock_time"
        )
        assert "pam_faillock_unlock_time" in content, (
            "root_unlock_time must use pam_faillock_unlock_time variable"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — faillock.conf.j2 does not exist

- [ ] **Step 3: Create the template**

Create `roles/users/templates/faillock.conf.j2`:

```
# Account lockout policy — deployed by Ansible
# Locks accounts after repeated failed authentication attempts.
# See faillock.conf(5) for documentation.

deny = {{ pam_faillock_deny }}
unlock_time = {{ pam_faillock_unlock_time }}
fail_interval = {{ pam_faillock_fail_interval }}
even_deny_root = true
root_unlock_time = {{ pam_faillock_unlock_time }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/templates/faillock.conf.j2 tests/property/test_pam_hardening_properties.py
git commit -m "feat: add faillock.conf template for account lockout"
```

---

### Task 3: Create faillock PAM Profile Template

**Files:**
- Create: `roles/users/templates/faillock-pam-config.j2`
- Modify: `tests/property/test_pam_hardening_properties.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/property/test_pam_hardening_properties.py`:

```python


class TestFaillockPamProfileProperties:
    """Property-based tests for faillock pam-auth-update profile template."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_has_correct_priority(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Priority

        The faillock PAM profile SHALL set Priority to 512 to place it
        after pam_unix (priority 256) in the PAM stack.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        assert template_path.exists(), "Faillock PAM profile template must exist"

        content = template_path.read_text()

        assert "Priority: 512" in content, (
            "PAM profile must set Priority to 512"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_has_auth_sections(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Auth Sections

        The faillock PAM profile SHALL contain Auth-Type Primary with
        preauth and Auth-Final with authfail sections.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        content = template_path.read_text()

        assert "Auth-Type: Primary" in content, (
            "PAM profile must have Auth-Type: Primary"
        )
        assert "preauth" in content, (
            "PAM profile must contain preauth directive"
        )
        assert "Auth-Final:" in content, (
            "PAM profile must have Auth-Final section"
        )
        assert "authfail" in content, (
            "PAM profile must contain authfail directive"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_has_account_section(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Account Section

        The faillock PAM profile SHALL contain an Account section to reset
        the failure counter on successful login.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        content = template_path.read_text()

        assert "Account-Type: Additional" in content, (
            "PAM profile must have Account-Type: Additional"
        )
        assert "Account:" in content, (
            "PAM profile must have Account section"
        )
        assert "pam_faillock.so" in content, (
            "PAM profile Account section must reference pam_faillock.so"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_pam_profile_sets_default_yes(self):
        """
        Feature: vps-bootstrap-playbook, Faillock PAM Profile Default

        The faillock PAM profile SHALL set Default to yes so
        pam-auth-update enables it automatically.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/faillock-pam-config.j2")
        content = template_path.read_text()

        assert "Default: yes" in content, (
            "PAM profile must set Default: yes"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — faillock-pam-config.j2 does not exist

- [ ] **Step 3: Create the template**

Create `roles/users/templates/faillock-pam-config.j2`:

```
Name: Faillock account lockout
Default: yes
Priority: 512
Auth-Type: Primary
Auth:
  required  pam_faillock.so preauth
Auth-Final:
  [default=die]  pam_faillock.so authfail
Account-Type: Additional
Account:
  required  pam_faillock.so
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/templates/faillock-pam-config.j2 tests/property/test_pam_hardening_properties.py
git commit -m "feat: add faillock pam-auth-update profile template"
```

---

### Task 4: Create Resource Limits Template

**Files:**
- Create: `roles/users/templates/50-hardening.conf.j2`
- Modify: `tests/property/test_pam_hardening_properties.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/property/test_pam_hardening_properties.py`:

```python


@st.composite
def resource_limit_type(draw):
    """Generate one of the resource limit types."""
    return draw(st.sampled_from(["nproc", "nofile", "core"]))


class TestResourceLimitsProperties:
    """Property-based tests for resource limits template."""

    @pytest.mark.property
    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        limit_type=resource_limit_type(),
    )
    def test_limits_template_contains_all_limit_types(
        self,
        limit_type: str,
    ):
        """
        Feature: vps-bootstrap-playbook, Resource Limits Contains All Types

        The resource limits template SHALL contain nproc, nofile, and
        core limit definitions.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        assert template_path.exists(), "Resource limits template must exist"

        content = template_path.read_text()

        assert limit_type in content, (
            f"Resource limits must contain {limit_type} limit"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_hardcodes_core_zero(self):
        """
        Feature: vps-bootstrap-playbook, Resource Limits Core Zero

        The resource limits template SHALL hardcode core to 0 to prevent
        credential leaks in core dumps.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        # Find a line with 'core' that has '0' and is not a comment
        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped.startswith("#") and "core" in stripped:
                assert "0" in stripped, (
                    "core limit must be set to 0"
                )
                return
        pytest.fail("Resource limits must contain an uncommented core limit line")

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_has_separate_root_nproc(self):
        """
        Feature: vps-bootstrap-playbook, Resource Limits Root Nproc

        The resource limits template SHALL define a separate nproc limit
        for root using the pam_limits_nproc_root variable.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        assert "pam_limits_nproc_root" in content, (
            "Resource limits must use pam_limits_nproc_root variable for root"
        )
        assert "pam_limits_nproc" in content, (
            "Resource limits must use pam_limits_nproc variable for regular users"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_has_separate_root_nofile(self):
        """
        Feature: vps-bootstrap-playbook, Resource Limits Root Nofile

        The resource limits template SHALL define a separate nofile limit
        for root using the pam_limits_nofile_root variable.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        assert "pam_limits_nofile_root" in content, (
            "Resource limits must use pam_limits_nofile_root variable for root"
        )
        assert "pam_limits_nofile" in content, (
            "Resource limits must use pam_limits_nofile variable for regular users"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_limits_template_uses_hard_limits_only(self):
        """
        Feature: vps-bootstrap-playbook, Resource Limits Hard Only

        The resource limits template SHALL use hard limits only (not soft).
        Hard limits set the ceiling; users keep flexibility below it.

        Validates: PAM hardening design spec
        """
        template_path = Path("roles/users/templates/50-hardening.conf.j2")
        content = template_path.read_text()

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                assert "hard" in stripped, (
                    f"All limit lines must use 'hard' type, got: {stripped}"
                )
                assert "soft" not in stripped, (
                    f"Limit lines must NOT use 'soft' type, got: {stripped}"
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-property`
Expected: FAIL — 50-hardening.conf.j2 does not exist

- [ ] **Step 3: Create the template**

Create `roles/users/templates/50-hardening.conf.j2`:

```
# Resource limits — deployed by Ansible
# Prevents fork bombs, caps file descriptors, disables core dumps.
# Only affects PAM-authenticated sessions (login shells, SSH).
# Systemd services set their own limits via LimitNOFILE= independently.

# Prevent fork bombs — hard limit on number of processes
*               hard    nproc           {{ pam_limits_nproc }}
root            hard    nproc           {{ pam_limits_nproc_root }}

# Cap open file descriptors — prevents fd exhaustion
*               hard    nofile          {{ pam_limits_nofile }}
root            hard    nofile          {{ pam_limits_nofile_root }}

# Disable core dumps — prevents credential leaks in dumps
*               hard    core            0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-property`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `make python-lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/users/templates/50-hardening.conf.j2 tests/property/test_pam_hardening_properties.py
git commit -m "feat: add resource limits template (nproc, nofile, core)"
```

---

## Chunk 2: Tasks, Verification, and Documentation

### Task 5: Add Deployment Tasks

**Files:**
- Modify: `roles/users/tasks/main.yml` (append after line 215)
- Modify: `tests/property/test_pam_hardening_properties.py`

- [ ] **Step 1: Add the four PAM hardening tasks**

Append to `roles/users/tasks/main.yml` after the last login policy task (line 215):

```yaml

# PAM Hardening
# Account lockout via pam_faillock, resource limits via pam_limits

- name: Deploy faillock configuration
  ansible.builtin.template:
    src: faillock.conf.j2
    dest: /etc/security/faillock.conf
    owner: root
    group: root
    mode: "0644"
  tags:
    - users
    - pam_hardening

- name: Deploy faillock PAM profile
  ansible.builtin.template:
    src: faillock-pam-config.j2
    dest: /usr/share/pam-configs/faillock
    owner: root
    group: root
    mode: "0644"
  tags:
    - users
    - pam_hardening
  notify: Enable faillock in PAM

- name: Deploy resource limits
  ansible.builtin.template:
    src: 50-hardening.conf.j2
    dest: /etc/security/limits.d/50-hardening.conf
    owner: root
    group: root
    mode: "0644"
  tags:
    - users
    - pam_hardening
```

**Note on pam-auth-update:** The spec says to run `pam-auth-update --enable faillock` as a task. However, the idiomatic Ansible approach is to use a handler triggered by the PAM profile template change. This way `pam-auth-update` only runs when the profile file actually changes, and it runs at the end of the play (after all tasks). Add the handler:

Append to `roles/users/handlers/main.yml` (create the file if it doesn't exist):

```yaml
---
- name: Enable faillock in PAM
  ansible.builtin.command:
    cmd: pam-auth-update --enable faillock
  changed_when: true
```

- [ ] **Step 2: Add property tests for tasks and handler**

Append to `tests/property/test_pam_hardening_properties.py`:

```python


class TestPamHardeningTasksProperties:
    """Property-based tests for PAM hardening deployment tasks."""

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_faillock_conf(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy faillock.conf

        The users role tasks SHALL deploy the faillock.conf template.

        Validates: PAM hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        assert tasks_path.exists(), "Users tasks must exist"

        content = tasks_path.read_text()

        assert "faillock.conf.j2" in content, (
            "Tasks must reference faillock.conf.j2 template"
        )
        assert "dest: /etc/security/faillock.conf" in content, (
            "Tasks must deploy to /etc/security/faillock.conf"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_faillock_pam_profile(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy Faillock PAM Profile

        The users role tasks SHALL deploy the faillock PAM profile
        to /usr/share/pam-configs/.

        Validates: PAM hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "faillock-pam-config.j2" in content, (
            "Tasks must reference faillock-pam-config.j2 template"
        )
        assert "dest: /usr/share/pam-configs/faillock" in content, (
            "Tasks must deploy to /usr/share/pam-configs/faillock"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_enable_faillock_via_pam_auth_update(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Enable Faillock via pam-auth-update

        The users role SHALL run pam-auth-update to enable faillock
        after deploying the PAM profile (via handler or task).

        Validates: PAM hardening design spec
        """
        # Check handler or tasks for pam-auth-update
        handlers_path = Path("roles/users/handlers/main.yml")
        tasks_path = Path("roles/users/tasks/main.yml")

        handlers_content = ""
        if handlers_path.exists():
            handlers_content = handlers_path.read_text()

        tasks_content = tasks_path.read_text()
        combined = handlers_content + tasks_content

        assert "pam-auth-update" in combined, (
            "Role must run pam-auth-update to enable faillock"
        )

    @pytest.mark.property
    @pytest.mark.unit
    def test_tasks_deploy_resource_limits(self):
        """
        Feature: vps-bootstrap-playbook, Tasks Deploy Resource Limits

        The users role tasks SHALL deploy the resource limits template
        to /etc/security/limits.d/.

        Validates: PAM hardening design spec
        """
        tasks_path = Path("roles/users/tasks/main.yml")
        content = tasks_path.read_text()

        assert "50-hardening.conf.j2" in content, (
            "Tasks must reference 50-hardening.conf.j2 template"
        )
        assert "dest: /etc/security/limits.d/50-hardening.conf" in content, (
            "Tasks must deploy to /etc/security/limits.d/50-hardening.conf"
        )
```

- [ ] **Step 3: Lint**

Run: `make ansible-lint && make python-lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add roles/users/tasks/main.yml roles/users/handlers/main.yml tests/property/test_pam_hardening_properties.py
git commit -m "feat: add PAM hardening deployment tasks and handler"
```

---

### Task 6: Add Verification Checks

**Files:**
- Modify: `tests/verify_bootstrap.yml`

- [ ] **Step 1: Add verification blocks**

Insert before the `# FINAL SUMMARY` section (before line 944) in `tests/verify_bootstrap.yml`:

```yaml

    # ==============================================================================
    # PAM HARDENING VERIFICATION
    # ==============================================================================

    - name: "Verify faillock configuration"
      block:
        - name: Read faillock.conf
          ansible.builtin.slurp:
            path: /etc/security/faillock.conf
          register: faillock_conf_content

        - name: Verify faillock.conf settings
          ansible.builtin.assert:
            that:
              - faillock_conf_content.content | b64decode is search('deny.*' + (pam_faillock_deny | string))
              - faillock_conf_content.content | b64decode is search('even_deny_root.*true')
            fail_msg: "faillock.conf is missing or incomplete"
            success_msg: >-
              ✓ faillock.conf deployed (deny {{ pam_faillock_deny }},
              even_deny_root true)

        - name: Check faillock PAM profile exists
          ansible.builtin.stat:
            path: /usr/share/pam-configs/faillock
          register: faillock_pam_profile

        - name: Verify faillock is enabled in PAM
          ansible.builtin.command:
            cmd: grep -q pam_faillock /etc/pam.d/common-auth
          register: faillock_pam_check
          changed_when: false
          failed_when: false

        - name: Verify faillock PAM integration
          ansible.builtin.assert:
            that:
              - faillock_pam_profile.stat.exists
              - faillock_pam_check.rc == 0
            fail_msg: "Faillock PAM profile not deployed or not enabled in common-auth"
            success_msg: "✓ Faillock enabled in PAM via pam-auth-update"

    - name: "Verify resource limits"
      block:
        - name: Check resource limits file exists
          ansible.builtin.stat:
            path: /etc/security/limits.d/50-hardening.conf
          register: limits_file

        - name: Read resource limits
          ansible.builtin.slurp:
            path: /etc/security/limits.d/50-hardening.conf
          register: limits_content
          when: limits_file.stat.exists

        - name: Verify resource limits
          ansible.builtin.assert:
            that:
              - limits_file.stat.exists
              - limits_content.content | b64decode is search('nproc')
              - limits_content.content | b64decode is search('core.*0')
            fail_msg: "Resource limits file is missing or incomplete"
            success_msg: "✓ Resource limits deployed (nproc, nofile, core)"

```

- [ ] **Step 2: Add PAM hardening to verification summary**

In the summary `debug` message, add after the login policy line:

```yaml
              - "  ✓ PAM hardening (faillock account lockout, resource limits)"
```

- [ ] **Step 3: Lint**

Run: `make ansible-lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/verify_bootstrap.yml
git commit -m "test: add PAM hardening verification checks"
```

---

### Task 7: Add Admin Documentation

**Files:**
- Create: `docs/pam-hardening.md`

- [ ] **Step 1: Create documentation**

Create `docs/pam-hardening.md`:

```markdown
# PAM Hardening

The bootstrap playbook hardens PAM with account lockout protection and system-wide resource limits.

## What It Does

### Account Lockout (pam_faillock)

Locks accounts after repeated failed authentication attempts. Protects against brute-force attacks on console login, SSH, and sudo.

- Locks after 5 failed attempts within a 15-minute window
- Unlocks automatically after 10 minutes
- Root accounts are locked too (timed, never permanent)
- Lockout state clears on reboot

Deployed to: `/etc/security/faillock.conf`
PAM profile: `/usr/share/pam-configs/faillock`

### Resource Limits (pam_limits)

Enforces system-wide resource limits to prevent fork bombs, file descriptor exhaustion, and credential leaks via core dumps. These limits apply to PAM-authenticated sessions (login shells, SSH). Systemd services set their own limits independently.

| Limit | User | Root | Purpose |
|-------|------|------|---------|
| `nproc` | 1024 | 2048 | Max processes (prevents fork bombs) |
| `nofile` | 4096 | 8192 | Max open file descriptors |
| `core` | 0 | 0 | Disables core dumps (prevents credential leaks) |

Deployed to: `/etc/security/limits.d/50-hardening.conf`

## Managing Locked Accounts

```bash
# View failed login attempts for a user
faillock --user <username>

# Manually unlock a locked account
faillock --user <username> --reset

# View all users with failed attempts
faillock
```

A locked account unlocks automatically after 10 minutes. Rebooting also clears all lockout state.

## Checking Resource Limits

```bash
# Check current resource limits for your session
ulimit -a

# Check a specific user's limits
su - <username> -c 'ulimit -a'
```

## Configuration

Override these variables in your inventory or playbook:

```yaml
# Account lockout
pam_faillock_deny: 5             # Failed attempts before lockout
pam_faillock_unlock_time: 600    # Seconds until automatic unlock
pam_faillock_fail_interval: 900  # Sliding window for counting failures

# Resource limits
pam_limits_nproc: 1024           # Max processes per user
pam_limits_nproc_root: 2048      # Max processes for root
pam_limits_nofile: 4096          # Max open file descriptors per user
pam_limits_nofile_root: 8192     # Max open file descriptors for root
```

Core dumps (`core 0`) cannot be configured — this is security policy.
```

- [ ] **Step 2: Commit**

```bash
git add docs/pam-hardening.md
git commit -m "docs: add PAM hardening admin instructions"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run all property tests**

Run: `make test-property`
Expected: All tests pass

- [ ] **Step 2: Run all tests**

Run: `make test`
Expected: All tests pass (pre-existing firewall failures are known/unrelated)

- [ ] **Step 3: Run all linters**

Run: `make python-lint && make ansible-lint`
Expected: PASS

- [ ] **Step 4: Review git log**

Run: `git log --oneline -10`
Verify: All commits are present and well-described
