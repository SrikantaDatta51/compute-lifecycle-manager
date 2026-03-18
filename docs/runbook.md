# BCM IAC — Operational Runbook

> Complete guide for running all BCM lab and production operations.

---

## Table of Contents

1. [Lab Setup](#1-lab-setup)
2. [Lab Ansible Playbooks](#2-lab-ansible-playbooks)
3. [GitOps Production Operations](#3-gitops-production-operations)
4. [Slurm Operations](#4-slurm-operations)
5. [Debug Bundle Collection](#5-debug-bundle-collection)
6. [Burn-In Test Suite](#6-burn-in-test-suite)
7. [Firmware Management](#7-firmware-management)
8. [Sample Workloads](#8-sample-workloads)

---

## 1. Lab Setup

### Prerequisites

- Linux host with KVM/libvirt installed
- NVIDIA BCM 11 ISO
- IOMMU enabled (for GPU passthrough)
- At least 64 GB RAM, 8+ CPU cores

### Step-by-Step Lab Creation

```bash
cd lab/

# ── Step 1: Create the management network ──
./scripts/01-create-networks.sh
# Creates 'bcm-mgmt' virtual network (192.168.200.0/24)
# Verify: virsh net-list --all

# ── Step 2: Create BCM head node ──
./scripts/02-create-head-node.sh
# Creates VM: 16 vCPU, 48 GB RAM, 200 GB disk
# Attach BCM ISO and complete installation
# Head node IP: 192.168.200.254

# ── Step 3: Create CPU compute nodes ──
./scripts/03-create-cpu-nodes.sh
# Creates cpu-n01 and cpu-n02 (2 vCPU, 2 GB each)
# Network: bcm-mgmt only (PXE boot)

# ── Step 4: Create GPU compute node ──
./scripts/04-create-gpu-node.sh
# Creates gpu-n01 (4 vCPU, 4 GB, Quadro GV100 passthrough)
# Requires IOMMU enabled — see lab/configs/gpu-passthrough.md

# ── Step 5: Boot compute nodes ──
virsh start cpu-n01
virsh start cpu-n02
virsh start gpu-n01
# BCM head node will PXE-provision all compute nodes automatically

# ── Step 6: Configure Slurm ──
# SSH to head node and run cmsh commands:
ssh root@192.168.200.254
# Then run: source /path/to/configs/slurm-setup.sh
# Or manually: see configs/slurm-setup.cmsh

# ── Step 7: Verify everything ──
./post-install/verify-cluster.sh
./post-install/test-slurm-job.sh
```

### Teardown

```bash
./scripts/05-teardown.sh
# Removes all VMs and the bcm-mgmt network
```

---

## 2. Lab Ansible Playbooks

All lab playbooks are in `lab/ansible/playbooks/`. They connect to the BCM head node via SSH and use `cmsh` for compute node operations.

```bash
cd lab/ansible/
```

### 2.1 Cluster Health Check

Runs a full health check on all nodes, Slurm, and services.

```bash
ansible-playbook playbooks/cluster_health.yml
```

**Output**: Node status, Slurm partition health, service states, network connectivity.

### 2.2 Slurm Management

```bash
# Setup Slurm partitions (cpu-partition + gpu-partition)
ansible-playbook playbooks/slurm_manage.yml -e "action=setup"

# Check Slurm status
ansible-playbook playbooks/slurm_manage.yml -e "action=status"

# Drain a node for maintenance
ansible-playbook playbooks/slurm_manage.yml \
    -e "action=drain" \
    -e "targets=['cpu-n01']" \
    -e "reason='planned-maintenance'"

# Resume a drained node
ansible-playbook playbooks/slurm_manage.yml \
    -e "action=resume" \
    -e "targets=['cpu-n01']"

# Submit a test job
ansible-playbook playbooks/slurm_manage.yml -e "action=test_job"
```

### 2.3 Node Status (BCM)

```bash
# Set a node to UP
ansible-playbook playbooks/node_status.yml \
    -e "targets=['cpu-n01']" \
    -e "bcm_status=UP"

# Set a node to CLOSED (maintenance)
ansible-playbook playbooks/node_status.yml \
    -e "targets=['cpu-n01']" \
    -e "bcm_status=CLOSED"
```

### 2.4 Node Provisioning (PXE)

```bash
# Re-provision a node
ansible-playbook playbooks/node_provision.yml \
    -e "targets=['cpu-n01']" \
    -e "category=default"

# Provision with a specific software image
ansible-playbook playbooks/node_provision.yml \
    -e "targets=['cpu-n01']" \
    -e "category=gpu-compute"
```

### 2.5 Debug Bundle Collection

```bash
# Collect diagnostics for a support ticket
ansible-playbook playbooks/debug_bundle.yml \
    -e "targets=['cpu-n01','cpu-n02']" \
    -e "ticket_id=INC-12345"
```

**Collects**: dmesg, syslog, hardware info, Slurm logs, BCM status.

### 2.6 Power Management

```bash
# Power cycle a node
ansible-playbook playbooks/power_manage.yml \
    -e "targets=['cpu-n01']" \
    -e "power_action=reset"

# Power off
ansible-playbook playbooks/power_manage.yml \
    -e "targets=['cpu-n01']" \
    -e "power_action=off"

# Check power status
ansible-playbook playbooks/power_manage.yml \
    -e "targets=['cpu-n01']" \
    -e "power_action=status"
```

### 2.7 Node Reboot (Graceful)

```bash
# Reboot with Slurm drain
ansible-playbook playbooks/node_reboot.yml \
    -e "targets=['cpu-n01']" \
    -e "drain_first=true"

# Hard reboot (skip drain)
ansible-playbook playbooks/node_reboot.yml \
    -e "targets=['cpu-n01']" \
    -e "drain_first=false"
```

### 2.8 Arbitrary cmsh Commands

```bash
# List all devices
ansible-playbook playbooks/cmsh_exec.yml \
    -e "cmsh_command='device; list'"

# List categories
ansible-playbook playbooks/cmsh_exec.yml \
    -e "cmsh_command='category; list'"

# Multiple commands
ansible-playbook playbooks/cmsh_exec.yml \
    -e '{"cmsh_commands": ["device; list", "partition; list", "device status"]}'
```

---

## 3. GitOps Production Operations

All production playbooks are in `gitops/playbooks/`. Operations are triggered via GitHub PRs.

### 3.1 PR-Based Workflow

```bash
cd gitops/

# ── Step 1: Copy the template ──
cp operation-requests/_template.yml operation-requests/my-operation.yml

# ── Step 2: Edit the YAML ──
# See examples below for each operation type

# ── Step 3: Create PR ──
git checkout -b ops/my-operation
git add operation-requests/my-operation.yml
git commit -m "ops: describe the operation"
git push origin ops/my-operation

# ── Step 4: Create PR in GitHub, get approval, merge ──
# GitHub Actions triggers Ansible Tower automatically
# Results posted as PR comment
```

### 3.2 Operation Request Examples

#### Reboot a Node

```yaml
# operation-requests/reboot-node-042.yml
operation: day2_reboot
targets:
  - dgx-b200-042
reboot_type: graceful    # graceful | hard | ipmi
reason: "XID 79 recovery"
drain_first: true
```

#### Cordon a Node (Maintenance)

```yaml
# operation-requests/cordon-node-028.yml
operation: day2_cordon
targets:
  - dgx-b200-028
reason: "Scheduled hardware maintenance"
```

#### Uncordon a Node (Return to Service)

```yaml
# operation-requests/uncordon-node-028.yml
operation: day2_uncordon
targets:
  - dgx-b200-028
run_sanity_check: true
```

#### Power Management

```yaml
# operation-requests/power-reset-node-015.yml
operation: day2_power
targets:
  - dgx-b200-015
action: reset    # on | off | reset | status
```

#### GPU Reset (XID Error Recovery)

```yaml
# operation-requests/gpu-reset-node-042.yml
operation: day2_gpu_reset
targets:
  - dgx-b200-042
clear_ecc: true
restart_services: true
```

#### InfiniBand Reset

```yaml
# operation-requests/ib-reset-node-042.yml
operation: day2_ib_reset
targets:
  - dgx-b200-042
```

#### Debug Bundle

```yaml
# operation-requests/debug-bundle-node-015.yml
operation: debug_bundle
targets:
  - dgx-b200-015
  - dgx-b200-016
ticket_id: "NVBUG-4567890"
upload_to_s3: true
collect:
  - gpu
  - ib
  - nvsm
  - system
  - firmware
```

#### Burn-In Test

```yaml
# operation-requests/burnin-node-042.yml
operation: burnin_suite
targets:
  - dgx-b200-042
tests:
  - dcgmi
  - hpl
  - nccl
  - nemo
  - nvbandwidth
timeout_minutes: 240
```

---

## 4. Slurm Operations

### Quick Reference

```bash
# Check partition status
sinfo

# Show job queue
squeue

# Submit a simple CPU job
sbatch --partition=cpu-partition --wrap="echo Hello from $(hostname)"

# Submit a multi-node job
sbatch --partition=cpu-partition --nodes=2 --wrap="hostname"

# Submit a GPU job
sbatch --partition=gpu-partition --gres=gpu:1 --wrap="nvidia-smi"

# Cancel a job
scancel <jobid>

# Show node details
scontrol show nodes

# Watch jobs in real-time
watch -n 5 squeue
```

### Job Script Template

```bash
#!/bin/bash
#SBATCH --job-name=my-job
#SBATCH --partition=cpu-partition
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:10:00
#SBATCH --output=result_%j.log

echo "Running on: $(hostname)"
echo "Start: $(date)"
# Your workload here
echo "Done: $(date)"
```

### GPU Job Script

```bash
#!/bin/bash
#SBATCH --job-name=gpu-test
#SBATCH --partition=gpu-partition
#SBATCH --gres=gpu:1
#SBATCH --time=00:10:00
#SBATCH --output=gpu_%j.log

echo "Node: $(hostname)"
nvidia-smi
echo "CUDA devices: $CUDA_VISIBLE_DEVICES"
```

---

## 5. Debug Bundle Collection

### Lab (Direct Ansible)

```bash
cd lab/ansible/

ansible-playbook playbooks/debug_bundle.yml \
    -e "targets=['cpu-n01','cpu-n02']" \
    -e "ticket_id=INC-12345"
```

### Production (GitOps PR)

Create a YAML and PR:

```yaml
operation: debug_bundle
targets:
  - dgx-b200-015
ticket_id: "NVBUG-4567890"
upload_to_s3: true
```

### Targeted Diagnostics

```bash
# GPU diagnostics only (nvidia-smi, dcgmi, nvidia-bug-report.sh)
# PR with: operation: debug_gpu_diag

# InfiniBand diagnostics only (ibstat, perfquery, mlxlink)
# PR with: operation: debug_ib_diag

# NVSM dump only
# PR with: operation: debug_nvsm_dump

# System logs only (dmesg, journalctl, IPMI SEL)
# PR with: operation: debug_logs
```

### Retrieve Debug Bundles from S3

```bash
# Generate pre-signed URL for sharing with NVIDIA
cd gitops/
./scripts/generate_presigned_url.sh <s3-key>
```

---

## 6. Burn-In Test Suite

### Full Suite (All Tests)

```yaml
# operation-requests/burnin-full-node-042.yml
operation: burnin_suite
targets:
  - dgx-b200-042
tests:
  - dcgmi        # DCGM GPU stress
  - hpl          # High Performance Linpack
  - nccl         # Multi-GPU NCCL all-reduce
  - nemo         # NeMo training
  - nvbandwidth  # GPU memory bandwidth
timeout_minutes: 240
```

### Individual Tests

```yaml
# DCGM GPU diagnostics only
operation: burnin_dcgmi
targets: [dgx-b200-042]

# HPL benchmark only
operation: burnin_hpl
targets: [dgx-b200-042]

# NCCL all-reduce test only
operation: burnin_nccl
targets: [dgx-b200-042]

# NeMo training test only
operation: burnin_nemo
targets: [dgx-b200-042]

# GPU memory bandwidth only
operation: burnin_nvbandwidth
targets: [dgx-b200-042]
```

---

## 7. Firmware Management

### Check Firmware Versions

```yaml
# operation-requests/firmware-check-042.yml
operation: firmware_check
targets:
  - dgx-b200-042
action: check    # check | update
components:
  - gpu
  - nic
  - bmc
```

---

## 8. Sample Workloads

### Nemotron Sample (CPU Benchmark)

```bash
# From the head node:
sbatch lab/post-install/nemotron-sample.sh
```

This runs a 3-phase benchmark:
1. **CPU Benchmark** — Python matrix multiplication
2. **I/O Benchmark** — 100 MB write/read test
3. **Network Test** — Connectivity and IP listing

### Quick Test Jobs

```bash
# Submit all 3 test jobs (CPU, multi-node, GPU)
lab/post-install/test-slurm-job.sh
```

---

## Infrastructure Setup

### S3 Debug Bundle Storage

```bash
aws cloudformation deploy \
  --template-file gitops/cloudformation/nvidia-debug-s3.yaml \
  --stack-name nvidia-debug-bundles \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=production
```

### GitHub Actions Secrets

| Secret | Description |
|--------|-------------|
| `ANSIBLE_TOWER_HOST` | Ansible Tower URL |
| `ANSIBLE_TOWER_TOKEN` | Tower API token |

### Ansible Tower Setup

1. Create **Inventory** with BCM head node
2. Create **Credential** for SSH access
3. Create **Job Template** named `BCM-GitOps-Runner`

---

> *CIC Platform Engineering — BCM IAC Runbook v1.0*
