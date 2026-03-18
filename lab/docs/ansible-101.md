# Ansible 101 — A Practical Guide for This Repo

> If you've never used Ansible before, this guide will get you from zero to
> running playbooks in 15 minutes. Written specifically for the BCM Lab context.

---

## What Is Ansible?

Ansible is an **agentless automation tool** that runs commands on remote machines over SSH.
You write "playbooks" (YAML files) that describe **what** should happen, and Ansible
makes it happen.

```
  ┌──────────────┐          SSH           ┌──────────────┐
  │  Your Laptop │  ───────────────────►  │  BCM Head    │
  │  (Ansible    │  ◄─── stdout ──────    │  Node        │
  │   Controller)│                        │  (runs cmsh) │
  └──────────────┘                        └──────────────┘
```

**Key concept**: Ansible **pushes** commands from your machine → remote host. Nothing is installed
on the remote machine (no agent).

---

## Installation

```bash
# Ubuntu / Debian
pip install ansible

# macOS
brew install ansible

# Verify
ansible --version
# ansible [core 2.20.3]
```

---

## Core Concepts

### 1. Inventory — *"Who am I managing?"*

An inventory file lists your hosts and groups:

```yaml
# inventory/hosts.yml
all:
  children:
    bcm_headnodes:      # Group name
      hosts:
        bcm-head:       # Hostname
          ansible_host: "192.168.200.254"   # IP to connect to
          ansible_user: root                 # SSH user
```

**Key points:**
- Groups let you target multiple hosts at once
- `all` is the special parent group
- Variables can be set per-host or per-group

### 2. Playbook — *"What do I want to happen?"*

A playbook is a YAML file with one or more "plays":

```yaml
---
- name: "My First Play"          # Human-readable name
  hosts: bcm_headnodes           # Which inventory group to target
  gather_facts: false            # Skip gathering system info (faster)

  tasks:
    - name: "Say hello"
      ansible.builtin.debug:
        msg: "Hello from Ansible!"
```

### 3. Task — *"One single action"*

Each task uses a **module** (a built-in function):

```yaml
# Run a shell command
- name: "Check uptime"
  ansible.builtin.shell: uptime
  register: result        # Save output to a variable

# Print the result
- name: "Show uptime"
  ansible.builtin.debug:
    msg: "{{ result.stdout }}"
```

### 4. Variables — *"Configurable values"*

```yaml
# Defined in the playbook
vars:
  target_nodes:
    - cpu-n01
    - cpu-n02

# Or passed on the command line
#   -e "bcm_status=UP"
#   -e '{"targets": ["cpu-n01"]}'     ← JSON format for lists
```

### 5. Roles — *"Reusable playbook packages"*

A role is a structured directory with tasks, templates, and vars:

```
roles/
  bcm_debug_bundle/
    tasks/
      main.yml          ← Tasks run when role is called
    templates/
      bundle_manifest.j2  ← Jinja2 template
    files/
      upload_to_s3.sh   ← Script files
```

---

## Running Playbooks

### Basic Command

```bash
cd bcm-iac/lab/ansible
ansible-playbook playbooks/cluster_health.yml
```

### With Extra Variables

```bash
# String variable
ansible-playbook playbooks/cmsh_exec.yml -e "cmsh_command='device; list'"

# List variable (use JSON format!)
ansible-playbook playbooks/node_status.yml \
    -e '{"targets": ["cpu-n01", "cpu-n02"], "bcm_status": "UP"}'
```

> [!IMPORTANT]
> **Always use JSON format for lists**: `-e '{"targets": ["node1"]}'`
>
> Don't use: `-e "targets=['node1']"` — this passes a STRING, not a list!

### With a Different Inventory

```bash
ansible-playbook -i my-inventory.yml playbooks/cluster_health.yml
```

### Dry Run (Check Mode)

```bash
# See what WOULD change without actually changing anything
ansible-playbook playbooks/node_status.yml --check --diff \
    -e '{"targets": ["cpu-n01"], "bcm_status": "UP"}'
```

### Verbose Mode

```bash
# -v    = some detail
# -vv   = more detail
# -vvv  = SSH commands, full output
ansible-playbook playbooks/cluster_health.yml -vv
```

---

## Understanding Output

```
PLAY [Cluster Health Check] ****************************************************
                                    ↑ Play name

TASK [Check BCM services] ******************************************************
                            ↑ Task name
ok: [localhost] => (item=cmd)
 ↑       ↑            ↑
 │       │            └── Loop iteration
 │       └── Which host
 └── Status: ok (no change), changed, failed, skipping
```

### Status Colors

| Status | Meaning | Color |
|--------|---------|-------|
| `ok` | Task ran, no changes needed | Green |
| `changed` | Task ran, something changed | Yellow |
| `skipping` | Task skipped (condition not met) | Cyan |
| `failed` | Task failed | Red |
| `ignored` | Task failed but `ignore_errors: true` | Yellow |

### PLAY RECAP

```
PLAY RECAP *********************************************************************
localhost  : ok=13  changed=0  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
               ↑       ↑           ↑            ↑          ↑          ↑          ↑
            success  modified    SSH fail     errors     skipped   rescued   err+ignored
```

**Rule**: If `failed=0`, the playbook succeeded.

---

## Common Ansible Patterns Used in This Repo

### Pattern 1: Loop Over Nodes

```yaml
- name: "Check each node"
  ansible.builtin.shell: |
    cmsh -c "device; use {{ item }}; get status"
  loop: "{{ target_nodes }}"
  register: results           # results.results is a list
```

### Pattern 2: Conditional Execution

```yaml
- name: "Only run if action is 'setup'"
  ansible.builtin.shell: echo "Setting up..."
  when: action == "setup"
```

### Pattern 3: Block / When (Group Tasks)

```yaml
- name: "Setup Slurm"
  when: action == "setup"
  block:
    - name: "Step 1"
      ansible.builtin.shell: echo "step 1"
    - name: "Step 2"
      ansible.builtin.shell: echo "step 2"
```

### Pattern 4: Register + Debug

```yaml
- name: "Run command"
  ansible.builtin.shell: uptime
  register: result
  changed_when: false    # Don't count this as a "change"

- name: "Show output"
  ansible.builtin.debug:
    msg: "{{ result.stdout }}"
```

### Pattern 5: Assertions (Input Validation)

```yaml
- name: "Validate input"
  ansible.builtin.assert:
    that: bcm_status in ['UP', 'CLOSED', 'DOWN', 'INSTALL']
    fail_msg: "Invalid status: {{ bcm_status }}"
```

### Pattern 6: Retry Until

```yaml
- name: "Wait for node to come up"
  ansible.builtin.shell: cmsh -c "device; use {{ item }}; get status"
  register: status
  until: "'UP' in status.stdout"
  retries: 30        # Try 30 times
  delay: 30          # Wait 30s between tries
```

---

## Best Practices

### 1. Always Use Fully Qualified Module Names

```yaml
# ✅ Good
- ansible.builtin.shell: uptime
- ansible.builtin.debug:

# ❌ Bad
- shell: uptime
- debug:
```

### 2. Use `changed_when` for Read-Only Commands

```yaml
# ✅ Reports "ok" instead of "changed"
- ansible.builtin.shell: sinfo -l
  changed_when: false

# ❌ Reports "changed" even though nothing changed
- ansible.builtin.shell: sinfo -l
```

### 3. Use `failed_when: false` for Optional Commands

```yaml
# ✅ Won't abort if Slurm isn't installed
- ansible.builtin.shell: scontrol show nodes
  failed_when: false

# ❌ Aborts entire playbook if scontrol not found
- ansible.builtin.shell: scontrol show nodes
```

### 4. Use JSON for List Variables

```bash
# ✅ Correct — list is properly parsed
-e '{"targets": ["cpu-n01", "cpu-n02"]}'

# ❌ Wrong — passes a string, not a list
-e "targets=['cpu-n01','cpu-n02']"
```

### 5. Keep Playbooks Idempotent

*Idempotent means: running it twice produces the same result.*

```yaml
# ✅ Idempotent — creates dir only if missing
- ansible.builtin.file:
    path: /tmp/bundle
    state: directory

# ❌ Not idempotent — appends every time
- ansible.builtin.shell: echo "data" >> /tmp/log
```

### 6. Use `block` to Group Related Tasks

```yaml
- name: "Reboot workflow"
  block:
    - name: "Drain"
      ansible.builtin.shell: scontrol drain {{ node }}
    - name: "Reboot"
      ansible.builtin.shell: cmsh power reset {{ node }}
    - name: "Resume"
      ansible.builtin.shell: scontrol resume {{ node }}
```

### 7. Always Add `loop_control.label` for Readability

```yaml
- name: "Check nodes"
  ansible.builtin.shell: cmsh get status {{ item }}
  loop: "{{ node_status.results }}"
  loop_control:
    label: "{{ item.item }}"    # Shows "cpu-n01" instead of entire dict
```

---

## File Structure in This Repo

```
lab/ansible/
├── ansible.cfg              ← Ansible configuration
├── inventory/
│   └── hosts.yml            ← Who we're managing
├── group_vars/
│   └── all.yml              ← Variables for all hosts
├── playbooks/               ← What we want to do
│   ├── cluster_health.yml
│   ├── cmsh_exec.yml
│   ├── debug_bundle.yml
│   ├── node_provision.yml
│   ├── node_reboot.yml
│   ├── node_status.yml
│   ├── power_manage.yml
│   └── slurm_manage.yml
└── roles/                   ← Reusable components
    ├── bcm_common/
    ├── bcm_lab_setup/
    └── bcm_slurm/
```

### ansible.cfg — Key Settings

```ini
[defaults]
inventory         = inventory/hosts.yml   # Default inventory
roles_path        = roles                 # Where to find roles
host_key_checking = False                 # Don't prompt for SSH keys
retry_files_enabled = False               # Don't create .retry files
forks             = 10                    # Run on 10 hosts in parallel

[privilege_escalation]
become            = True                  # Run as root via sudo
```

---

## Troubleshooting

### "No hosts matched"

```
[WARNING]: Could not match supplied host pattern, ignoring: bcm_headnodes
```

**Fix**: Make sure you're using the right inventory:
```bash
ansible-playbook -i inventory/hosts.yml playbooks/cluster_health.yml
```

### "The `loop` value must resolve to a 'list', not 'str'"

**Fix**: Use JSON format for extra vars:
```bash
# Wrong
-e "targets=['cpu-n01']"

# Right
-e '{"targets": ["cpu-n01"]}'
```

### "MODULE FAILURE" or "non-zero return code"

The remote command failed. Check:
```bash
# Run with verbose to see the actual error
ansible-playbook playbooks/xyz.yml -vvv
```

### Connection refused

```bash
# Test SSH connectivity
ansible -i inventory/hosts.yml bcm_headnodes -m ping

# Expected: SUCCESS
# If UNREACHABLE: check SSH keys, IP, firewall
```

---

## Further Reading

- [Ansible Documentation](https://docs.ansible.com/ansible/latest/)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/tips_tricks/ansible_tips_tricks.html)
- [YAML Syntax](https://docs.ansible.com/ansible/latest/reference_appendices/YAMLSyntax.html)
- [Jinja2 Filters](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_filters.html)
