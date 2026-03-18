# BCM Lab — Ansible Automation

Ansible playbooks for managing NVIDIA Base Command Manager (BCM) 11 lab cluster.

## Architecture

```
┌──────────────┐        SSH          ┌───────────────────┐      cmsh       ┌────────────────┐
│  Your        │ ──────────────────▶ │  BCM Head Node    │ ──────────────▶ │  Compute Nodes │
│  Workstation │   (password/key)    │  192.168.200.254  │  (device; exec) │  cpu-n01/02    │
└──────────────┘                     │  BCM 11.0 Active  │                 │  gpu-n01       │
                                     └───────────────────┘                 └────────────────┘
```

**Key design**: Ansible connects ONLY to the BCM head node. All compute-node operations use `cmsh` commands executed on the head node. This mirrors how production BCM clusters work.

## Quick Start

```bash
cd ansible/

# 1. Check cluster health
ansible-playbook playbooks/cluster_health.yml

# 2. Setup Slurm partitions
ansible-playbook playbooks/slurm_manage.yml -e "action=setup"

# 3. Check Slurm status
ansible-playbook playbooks/slurm_manage.yml -e "action=status"

# 4. Submit test job
ansible-playbook playbooks/slurm_manage.yml -e "action=test_job"
```

## Playbook Reference

| Playbook | Purpose | Example |
|----------|---------|---------|
| `cluster_health.yml` | Full cluster health check | `ansible-playbook playbooks/cluster_health.yml` |
| `slurm_manage.yml` | Slurm partition/node ops | `-e "action=setup\|status\|drain\|resume\|test_job"` |
| `node_status.yml` | BCM status (UP/DOWN/INSTALL) | `-e "targets=['cpu-n01']" -e "bcm_status=UP"` |
| `node_provision.yml` | PXE provisioning | `-e "targets=['cpu-n01']" -e "category=default"` |
| `debug_bundle.yml` | Diagnostic collection | `-e "targets=['cpu-n01']" -e "ticket_id=INC-123"` |
| `power_manage.yml` | Power on/off/reset/status | `-e "targets=['cpu-n01']" -e "power_action=reset"` |
| `node_reboot.yml` | Graceful reboot + Slurm drain | `-e "targets=['cpu-n01']" -e "drain_first=true"` |
| `cmsh_exec.yml` | Arbitrary cmsh commands | `-e "cmsh_command='device; list'"` |

## Inventory

The inventory (`inventory/hosts.yml`) defines:

- **`bcm_headnodes`**: SSH-accessible BCM head node (the only Ansible SSH target)
- **`cpu_nodes`**: Logical group for CPU compute nodes (managed via cmsh)
- **`gpu_nodes`**: Logical group for GPU compute nodes (managed via cmsh)

## Common Operations

### Drain a node for maintenance
```bash
ansible-playbook playbooks/slurm_manage.yml \
    -e "action=drain" \
    -e "targets=['cpu-n01']" \
    -e "reason='planned-maintenance'"
```

### Reprovision a node via PXE
```bash
ansible-playbook playbooks/node_provision.yml \
    -e "targets=['cpu-n01']" \
    -e "category=default"
```

### Collect debug bundle
```bash
ansible-playbook playbooks/debug_bundle.yml \
    -e "targets=['cpu-n01','cpu-n02']" \
    -e "ticket_id=INC-12345"
```

### Run arbitrary cmsh commands
```bash
# Single command
ansible-playbook playbooks/cmsh_exec.yml \
    -e "cmsh_command='device; list'"

# Multiple commands
ansible-playbook playbooks/cmsh_exec.yml \
    -e '{"cmsh_commands": ["device; list", "category; list", "partition; list"]}'
```

## Connection Configuration

The default connection uses password auth. To switch to SSH keys:

1. Generate key: `ssh-keygen -t ed25519 -f ~/.ssh/bcm_lab_key`
2. Copy to head node: `ssh-copy-id -i ~/.ssh/bcm_lab_key root@192.168.200.254`
3. Update `inventory/hosts.yml`: uncomment `ansible_ssh_private_key_file`, comment out `ansible_ssh_pass`

## Extending for Production

This lab setup mirrors production BCM clusters. To adapt:

1. Update `inventory/hosts.yml` with production head node IP
2. Update `group_vars/all.yml` with real node lists and GPU specs
3. Add GPU-specific debug commands (nvidia-smi, dcgmi, etc.)
4. Enable S3 upload in `debug_bundle.yml`
5. Add burn-in tests from the `bcm-ansible-gitops` repo
