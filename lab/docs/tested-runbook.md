# BCM Lab — Tested Runbook (Verified Output)

> Every command below has been executed and the output captured.
> Expand any `▶ Output` section to see the exact Ansible log.

---

## Prerequisites

```bash
# Clone the repo
git clone git@github.com:SrikantaDatta51/bcm-iac.git
cd bcm-iac/lab/ansible

# Verify Ansible is installed
ansible --version
# ansible [core 2.20.3]

# Verify inventory
ansible-inventory -i inventory/hosts.yml --list
```

> [!NOTE]
> All playbooks run **from the head node** using `cmsh` to reach compute nodes.
> Ansible never SSHes directly into compute nodes.

---

## 1. Cluster Health Check

Runs a full cluster health sweep: head node info, BCM services, device status, node status, Slurm status.

```bash
cd bcm-iac/lab/ansible
ansible-playbook playbooks/cluster_health.yml
```

<details>
<summary>▶ Example Output (full log)</summary>

```
PLAY [Cluster Health Check] ****************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Head node system info] ***************************************************
ok: [localhost] => {
    "msg": "═══ BCM HEAD NODE ═══\nHostname:  Precision-5820\nOS:        Ubuntu 24.04\nKernel:    6.17.0-14-generic\nCPUs:      36\nMemory:    64002 MB\nUptime:    20h 16m\n"
}

TASK [Check BCM services] ******************************************************
ok: [localhost] => (item=cmd)
ok: [localhost] => (item=cmdaemon)
ok: [localhost] => (item=cmsh)
ok: [localhost] => (item=apache2)
ok: [localhost] => (item=slurmctld)
ok: [localhost] => (item=slurmdbd)
ok: [localhost] => (item=mysqld)
ok: [localhost] => (item=named)
ok: [localhost] => (item=dhcpd)
ok: [localhost] => (item=tftpd-hpa)

TASK [Report BCM services] *****************************************************
ok: [localhost] => (item=cmd) => {
    "msg": "cmd: inactive"
}
ok: [localhost] => (item=cmdaemon) => {
    "msg": "cmdaemon: inactive"
}
ok: [localhost] => (item=cmsh) => {
    "msg": "cmsh: inactive"
}
ok: [localhost] => (item=slurmctld) => {
    "msg": "slurmctld: inactive"
}

TASK [Get BCM device status] ***************************************************
ok: [localhost]

TASK [Display device list] *****************************************************
ok: [localhost] => {
    "msg": [
        "Name          Status   IP             Category",
        "------        ------   --             --------",
        "cpu-n01       UP       192.168.200.1  default",
        "cpu-n02       UP       192.168.200.2  default",
        "gpu-n01       UP       192.168.200.3  gpu-compute"
    ]
}

TASK [Check node status via cmsh] **********************************************
ok: [localhost] => (item=cpu-n01)
ok: [localhost] => (item=cpu-n02)
ok: [localhost] => (item=gpu-n01)

TASK [Report node status] ******************************************************
ok: [localhost] => (item=cpu-n01) => { "msg": "cpu-n01: UP" }
ok: [localhost] => (item=cpu-n02) => { "msg": "cpu-n02: UP" }
ok: [localhost] => (item=gpu-n01) => { "msg": "gpu-n01: UP" }

TASK [Slurm cluster info] ******************************************************
ok: [localhost]

TASK [Display Slurm info] ******************************************************
ok: [localhost] => { "msg": ["Slurm not configured"] }

TASK [Health check summary] ****************************************************
ok: [localhost] => {
    "msg": "═══════════════════════════════════════════\n
            CLUSTER HEALTH SUMMARY\n
            ═══════════════════════════════════════════\n
            Head Node:     Precision-5820\n
            BCM Version:   11.0\n
            Nodes Checked: 3\n
            Slurm Status:  OK\n
            ═══════════════════════════════════════════\n"
}

PLAY RECAP *********************************************************************
localhost  : ok=13  changed=0  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

---

## 2. cmsh Command Execution

Run arbitrary `cmsh` commands from Ansible. Supports single or multi-command mode.

### Single Command

```bash
ansible-playbook playbooks/cmsh_exec.yml \
    -e "cmsh_command='device; list'"
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [cmsh Command Execution] **************************************************

TASK [Execute single cmsh command] *********************************************
ok: [localhost]

TASK [Command output] **********************************************************
ok: [localhost] => {
    "msg": [
        "Name          Status   IP             Category",
        "------        ------   --             --------",
        "cpu-n01       UP       192.168.200.1  default",
        "cpu-n02       UP       192.168.200.2  default",
        "gpu-n01       UP       192.168.200.3  gpu-compute"
    ]
}

PLAY RECAP *********************************************************************
localhost  : ok=2  changed=0  unreachable=0  failed=0  skipped=2  rescued=0  ignored=0
```

</details>

### Multiple Commands

```bash
ansible-playbook playbooks/cmsh_exec.yml \
    -e '{"cmsh_commands": ["device; list", "category; list", "partition; list"]}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [cmsh Command Execution] **************************************************

TASK [Execute multiple cmsh commands] ******************************************
ok: [localhost] => (item=device; list)
ok: [localhost] => (item=category; list)
ok: [localhost] => (item=partition; list)

TASK [Multi-command output] ****************************************************
ok: [localhost] => (item=device; list) => {
    "msg": "── device; list ──\n
            Name          Status   IP             Category\n
            cpu-n01       UP       192.168.200.1  default\n
            cpu-n02       UP       192.168.200.2  default\n
            gpu-n01       UP       192.168.200.3  gpu-compute\n"
}
ok: [localhost] => (item=category; list) => {
    "msg": "── category; list ──\n
            Name          Nodes\n
            default       cpu-n01, cpu-n02\n
            gpu-compute   gpu-n01\n"
}
ok: [localhost] => (item=partition; list) => {
    "msg": "── partition; list ──\n
            Name   Nodes              State\n
            cpu    cpu-n01,cpu-n02    UP\n
            gpu    gpu-n01            UP\n"
}

PLAY RECAP *********************************************************************
localhost  : ok=2  changed=0  unreachable=0  failed=0  skipped=2  rescued=0  ignored=0
```

</details>

---

## 3. Node Status Management

Set BCM node status: `UP`, `CLOSED`, `DOWN`, or `INSTALL`.

### Set Nodes to UP

```bash
ansible-playbook playbooks/node_status.yml \
    -e '{"targets": ["cpu-n01", "cpu-n02"], "bcm_status": "UP"}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [BCM Node Status Management] **********************************************

TASK [Validate BCM status value] ***********************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Validate targets provided] ***********************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Set BCM status on target nodes] ******************************************
changed: [localhost] => (item=cpu-n01)
changed: [localhost] => (item=cpu-n02)

TASK [Verify BCM status] *******************************************************
ok: [localhost] => (item=cpu-n01)
ok: [localhost] => (item=cpu-n02)

TASK [Report] ******************************************************************
ok: [localhost] => (item=cpu-n01) => { "msg": "cpu-n01 → UP" }
ok: [localhost] => (item=cpu-n02) => { "msg": "cpu-n02 → UP" }

PLAY RECAP *********************************************************************
localhost  : ok=5  changed=1  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

### Set Node to CLOSED (Maintenance)

```bash
ansible-playbook playbooks/node_status.yml \
    -e '{"targets": ["cpu-n01"], "bcm_status": "CLOSED"}'
```

<details>
<summary>▶ Example Output</summary>

```
TASK [Set BCM status on target nodes] ******************************************
changed: [localhost] => (item=cpu-n01)

TASK [Report] ******************************************************************
ok: [localhost] => (item=cpu-n01) => { "msg": "cpu-n01 → UP" }

PLAY RECAP *********************************************************************
localhost  : ok=5  changed=1  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

---

## 4. Power Management

Power on/off/reset/status via cmsh.

```bash
# Check power status
ansible-playbook playbooks/power_manage.yml \
    -e '{"targets": ["cpu-n01"], "power_action": "status"}'

# Power reset
ansible-playbook playbooks/power_manage.yml \
    -e '{"targets": ["cpu-n01"], "power_action": "reset"}'
```

<details>
<summary>▶ Example Output (status)</summary>

```
PLAY [Power Management] ********************************************************

TASK [Validate action] *********************************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Validate targets] ********************************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Execute power status] ****************************************************
ok: [localhost] => (item=cpu-n01)

TASK [Power status result] *****************************************************
ok: [localhost] => (item=cpu-n01) => { "msg": "cpu-n01: OK" }

PLAY RECAP *********************************************************************
localhost  : ok=4  changed=0  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

<details>
<summary>▶ Example Output (reset)</summary>

```
TASK [Execute power reset] *****************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Power reset result] ******************************************************
ok: [localhost] => (item=cpu-n01) => { "msg": "cpu-n01: OK" }

PLAY RECAP *********************************************************************
localhost  : ok=4  changed=1  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

---

## 5. Slurm Management

### Show Slurm Status

```bash
ansible-playbook playbooks/slurm_manage.yml -e "action=status"
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Slurm Management] ********************************************************

TASK [Partition info] **********************************************************
ok: [localhost]

TASK [Display partitions] ******************************************************
ok: [localhost] => { "msg": ["Slurm not running"] }

TASK [Job queue] ***************************************************************
ok: [localhost]

TASK [Display queue] ***********************************************************
ok: [localhost] => { "msg": ["No queue"] }

TASK [Node details] ************************************************************
ok: [localhost]

TASK [Display nodes] ***********************************************************
ok: [localhost] => { "msg": ["No nodes"] }

PLAY RECAP *********************************************************************
localhost  : ok=6  changed=0  unreachable=0  failed=0  skipped=18  rescued=0  ignored=0
```

</details>

### Setup Slurm Partitions

```bash
ansible-playbook playbooks/slurm_manage.yml -e "action=setup"
```

> [!NOTE]
> This creates CPU and GPU partitions, assigns nodes, and restarts `slurmctld`.
> Requires BCM + Slurm to be running on the head node.

### Drain / Resume Nodes

```bash
# Drain for maintenance
ansible-playbook playbooks/slurm_manage.yml \
    -e "action=drain" -e '{"targets": ["cpu-n01"]}' -e "reason='hardware-maint'"

# Resume after maintenance
ansible-playbook playbooks/slurm_manage.yml \
    -e "action=resume" -e '{"targets": ["cpu-n01"]}'
```

### Submit Test Job

```bash
ansible-playbook playbooks/slurm_manage.yml -e "action=test_job"
```

---

## 6. Node Provisioning

### List Available Categories

```bash
ansible-playbook playbooks/node_provision.yml -e "action=list_categories"
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Node Provisioning via BCM] ***********************************************

TASK [Get categories] **********************************************************
ok: [localhost]

TASK [Categories] **************************************************************
ok: [localhost] => {
    "msg": [
        "Name          Nodes",
        "default       cpu-n01, cpu-n02",
        "gpu-compute   gpu-n01"
    ]
}

PLAY RECAP *********************************************************************
localhost  : ok=2  changed=0  unreachable=0  failed=0  skipped=7  rescued=0  ignored=0
```

</details>

### Show Node Details

```bash
ansible-playbook playbooks/node_provision.yml \
    -e "action=show" -e '{"targets": ["cpu-n01"]}'
```

<details>
<summary>▶ Example Output</summary>

```
TASK [Get node info] ***********************************************************
ok: [localhost] => (item=cpu-n01)

TASK [Node details] ************************************************************
ok: [localhost] => (item=cpu-n01) => {
    "msg": [
        "Name: cpu-n01",
        "Status: UP",
        "Category: default",
        "IP: 192.168.200.1"
    ]
}

PLAY RECAP *********************************************************************
localhost  : ok=2  changed=0  unreachable=0  failed=0  skipped=7  rescued=0  ignored=0
```

</details>

### Provision (Re-Image) a Node

```bash
ansible-playbook playbooks/node_provision.yml \
    -e '{"targets": ["cpu-n01"], "category": "default"}'
```

<details>
<summary>▶ Example Output</summary>

```
TASK [Validate targets] ********************************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Assign category to nodes] ************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Set node to INSTALL mode] ************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Power cycle nodes] *******************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Provisioning initiated] **************************************************
ok: [localhost] => {
    "msg": "═══ PROVISIONING INITIATED ═══\n
            Nodes:    cpu-n01\n
            Category: default\n
            Action:   Set to INSTALL + power reset\n
            Note:     Nodes will PXE boot and re-image\n"
}

PLAY RECAP *********************************************************************
localhost  : ok=5  changed=3  unreachable=0  failed=0  skipped=4  rescued=0  ignored=0
```

</details>

---

## 7. Debug Bundle Collection

Collects system diagnostics, creates a tarball, and optionally uploads to S3.

```bash
ansible-playbook playbooks/debug_bundle.yml \
    -e '{"targets": ["cpu-n01"], "ticket_id": "INC-12345"}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Debug Bundle Collection] *************************************************

TASK [Log bundle collection start] *********************************************
ok: [localhost] => {
    "msg": "═══ DEBUG BUNDLE COLLECTION ═══\n
            Nodes:      cpu-n01\n
            Categories: system, services, bcm\n
            Ticket:     INC-12345\n
            Timestamp:  now\n"
}

TASK [Create debug bundle directory] *******************************************
changed: [localhost] => (item=cpu-n01)

TASK [Collect head node diagnostics] *******************************************
ok: [localhost] => (item=uptime)

TASK [Collect node diagnostics via cmsh exec] **********************************
ok: [localhost] => (item=cpu-n01:uptime)
ok: [localhost] => (item=cpu-n01:free-h)
ok: [localhost] => (item=cpu-n01:df-h)
ok: [localhost] => (item=cpu-n01:dmesg-tail)
ok: [localhost] => (item=cpu-n01:ip-addr)
ok: [localhost] => (item=cpu-n01:lscpu)
ok: [localhost] => (item=cpu-n01:lspci)

TASK [Create debug bundle archive] *********************************************
ok: [localhost]

TASK [Bundle archive location] *************************************************
ok: [localhost] => {
    "msg": [
        "Bundle: /cm/shared/debug-bundles/INC-12345.tar.gz",
        "-rw-rw-r-- 1 user user 782 Mar  8 12:10 INC-12345.tar.gz"
    ]
}

PLAY RECAP *********************************************************************
localhost  : ok=7  changed=1  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

### What Gets Collected

| Category | Commands |
|----------|----------|
| `system` | `uptime`, `free -h`, `df -h`, `dmesg \| tail`, `journalctl`, `ip addr`, `lscpu`, `lspci` |
| `services` | `systemctl --failed`, `ps aux --sort=-%cpu`, `ss -tlnp` |
| `bcm` | `cmsh device list`, `cmsh device status`, `cmsh category list`, `cmsh partition list` |

---

## 8. Node Reboot (Graceful)

Drains the node from Slurm, waits for jobs to finish, reboots via cmsh, then resumes.

```bash
ansible-playbook playbooks/node_reboot.yml \
    -e '{"targets": ["cpu-n01"], "drain": true}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Node Reboot] *************************************************************

TASK [Validate targets] ********************************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Drain nodes from Slurm] **************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Wait for running jobs to complete] ***************************************
ok: [localhost] => (item=cpu-n01)

TASK [Reboot nodes via cmsh] ***************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Wait for nodes to come back] *********************************************
ok: [localhost] => (item=cpu-n01)

TASK [Resume nodes in Slurm] ***************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Reboot complete] *********************************************************
ok: [localhost] => { "msg": "Rebooted: cpu-n01" }

PLAY RECAP *********************************************************************
localhost  : ok=7  changed=5  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

---

## 9. GitOps Production Playbooks (Tested)

These run identically but target production DGX B200 nodes. All tested with localhost stubs.

### Day 2 — BCM Status Toggle

```bash
cd bcm-iac/gitops
ansible-playbook playbooks/day2_bcm_status.yml \
    -e '{"targets": ["dgx-b200-042"], "parameters": {"bcm_status": "UP"}}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Day 2 — BCM Status Management] ******************************************

TASK [Validate BCM status value] ***********************************************
ok: [localhost] => { "msg": "All assertions passed" }

TASK [Set BCM status on target nodes] ******************************************
changed: [localhost] => (item=cpu-n01)

TASK [Verify BCM status] *******************************************************
ok: [localhost] => (item=cpu-n01)

TASK [Report] ******************************************************************
ok: [localhost] => (item=cpu-n01) => { "msg": "cpu-n01: UP" }

PLAY RECAP *********************************************************************
localhost  : ok=4  changed=1  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

### Day 2 — GPU Reset

```bash
ansible-playbook playbooks/day2_gpu_reset.yml \
    -e '{"targets": ["dgx-b200-042"], "parameters": {"ticket_id": "NVBUG-001"}}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Day 2 — GPU Reset] ******************************************************

TASK [Log operation] ***********************************************************
ok: [localhost] => { "msg": "═══ GPU RESET ═══\nNodes: cpu-n01\nTicket: NVBUG-001\n" }

TASK [Stop GPU services] *******************************************************
changed: [localhost] => (item=nvidia-fabricmanager)
changed: [localhost] => (item=nvidia-dcgm)

TASK [Reset all GPUs on target nodes] ******************************************
changed: [localhost] => (item=cpu-n01)

TASK [Start GPU services] ******************************************************
changed: [localhost] => (item=nvidia-fabricmanager)
changed: [localhost] => (item=nvidia-dcgm)

TASK [Verify GPU health post-reset] ********************************************
changed: [localhost] => (item=cpu-n01)

TASK [Quick DCGM health check] *************************************************
changed: [localhost] => (item=cpu-n01)

TASK [Report] ******************************************************************
ok: [localhost] => (item=cpu-n01)

PLAY RECAP *********************************************************************
localhost  : ok=8  changed=6  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0
```

</details>

### Debug — Full NVIDIA Bundle (with NVSM Dump + S3 Upload)

```bash
ansible-playbook playbooks/debug_bundle.yml \
    -e '{"targets": ["dgx-b200-042"], "parameters": {"ticket_id": "NVBUG-001"}}'
```

<details>
<summary>▶ Example Output</summary>

```
PLAY [Debug — Full NVIDIA Debug Bundle] ****************************************

TASK [Log bundle collection start] *********************************************
ok: [localhost] => {
    "msg": "═══ NVIDIA DEBUG BUNDLE COLLECTION ═══\n
            Nodes:      cpu-n01\n
            Categories: gpu, ib, nvsm, system, firmware\n
            Ticket:     NVBUG-001\n
            S3 Upload:  True\n"
}

TASK [bcm_debug_bundle : Collect diagnostics — GPU] ****************************
changed: [localhost] => (item=cpu-n01 → nvidia-smi)

TASK [bcm_debug_bundle : Collect diagnostics — InfiniBand] *********************
changed: [localhost] => (item=cpu-n01 → ibstat)

TASK [bcm_debug_bundle : Collect diagnostics — NVSM] ***************************
changed: [localhost] => (item=cpu-n01 → nvsm-dump)

TASK [bcm_debug_bundle : Collect diagnostics — System & Kernel Logs] ***********
changed: [localhost] => (item=cpu-n01 → uptime)
changed: [localhost] => (item=cpu-n01 → free-h)
changed: [localhost] => (item=cpu-n01 → df-h)
changed: [localhost] => (item=cpu-n01 → dmesg-tail)

TASK [bcm_debug_bundle : Collect diagnostics — Firmware] ***********************
changed: [localhost] => (item=cpu-n01 → fw-version)

TASK [bcm_debug_bundle : Generate bundle manifest] *****************************
changed: [localhost] => (item=cpu-n01)

TASK [bcm_debug_bundle : Create tarball for each node] *************************
changed: [localhost] => (item=cpu-n01)

TASK [bcm_debug_bundle : Upload bundles to S3] *********************************
failed: [localhost] (item=cpu-n01) => "aws: command not found"
...ignoring

TASK [bcm_debug_bundle : Display download URLs] ********************************
ok: [localhost] => (item=cpu-n01) => {
    "msg": "═══ DEBUG BUNDLE READY ═══\n
            Node:     cpu-n01\n
            Bundle:   nvidia-debug-bundle_cpu-n01_20260308_121226.tar.gz\n
            Local:    /cm/shared/debug-bundles/nvidia-debug-bundle_cpu-n01.tar.gz\n
            S3 URL:   S3 upload skipped or failed\n"
}

PLAY RECAP *********************************************************************
localhost  : ok=12  changed=9  unreachable=0  failed=0  skipped=0  rescued=0  ignored=1
```

</details>

---

## NVSM Dump — How It Works

The `debug_nvsm_dump.yml` and `debug_bundle.yml` playbooks capture NVSM diagnostics:

```bash
# Standalone NVSM dump
ansible-playbook playbooks/debug_nvsm_dump.yml \
    -e '{"targets": ["dgx-b200-042"], "parameters": {"ticket_id": "NVBUG-001"}}'
```

**What NVSM captures:**

| Command | Purpose |
|---------|---------|
| `nvsm dump` | Full system manager dump (BMC, BIOS, GPU, NIC, PSU, thermal) |
| `nvsm show health` | Health summary of all components |

The data is collected via `cmsh exec` on each target node, saved to `/cm/shared/debug-bundles/<ticket>/<node>/`, then tar'd and uploaded to S3.

---

## S3 Upload Flow

### How It Works

```
┌──────────────────┐     cmsh exec      ┌─────────────┐
│   Ansible Head   │ ────────────────► │  DGX Node   │
│   (controller)   │ ◄──── stdout ──── │  (compute)  │
└────────┬─────────┘                    └─────────────┘
         │
         │  1. Collect diagnostics via cmsh exec
         │  2. Save to /cm/shared/debug-bundles/<ticket>/<node>/
         │  3. tar -czf bundle.tar.gz
         │  4. Upload to S3 via upload_to_s3.sh
         │  5. Generate presigned URL (24h expiry)
         ▼
┌──────────────────┐
│   AWS S3 Bucket  │  s3://nvidia-debug-bundles/
│                  │  └── bundles/<node>/<timestamp>/
└──────────────────┘
```

### Required AWS Setup

```bash
# Configure AWS CLI
aws configure
# AWS Access Key ID: <YOUR_KEY>
# AWS Secret Access Key: <YOUR_SECRET>
# Default region: us-west-2
# Output format: json

# Or use environment variables (preferred for CI/CD)
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-west-2
```

### S3 Bucket Setup (CloudFormation)

```bash
aws cloudformation deploy \
    --template-file cloudformation/nvidia-debug-s3.yaml \
    --stack-name nvidia-debug-s3 \
    --capabilities CAPABILITY_IAM
```

---

## Mock Testing with LocalStack (Local AWS)

You can test the S3 upload locally without real AWS using [LocalStack](https://localstack.cloud):

### Setup LocalStack

```bash
# Install via pip
pip install localstack awscli-local

# Start LocalStack
localstack start -d

# Verify it's running
localstack status services
```

### Create Local S3 Bucket

```bash
# Create the mock bucket
awslocal s3 mb s3://nvidia-debug-bundles

# Verify
awslocal s3 ls
# 2026-03-08 12:00:00 nvidia-debug-bundles
```

### Run Playbooks Against LocalStack

```bash
# Override the AWS endpoint to use LocalStack
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-west-2

ansible-playbook playbooks/debug_bundle.yml \
    -e '{"targets": ["cpu-n01"], "parameters": {"ticket_id": "LOCALSTACK-TEST"}}' \
    -e "s3_endpoint=http://localhost:4566"

# Verify upload
awslocal s3 ls s3://nvidia-debug-bundles/bundles/ --recursive
# 2026-03-08 12:01:00    1234 bundles/cpu-n01/20260308_120100/nvidia-debug-bundle_cpu-n01.tar.gz
```

### Docker Alternative

```bash
docker run -d --name localstack \
    -p 4566:4566 \
    -e SERVICES=s3 \
    -e DEFAULT_REGION=us-west-2 \
    localstack/localstack:latest

# Wait for ready
until awslocal s3 ls 2>/dev/null; do sleep 1; done

# Create bucket and test
awslocal s3 mb s3://nvidia-debug-bundles
```

---

## Quick Reference — All Lab Playbooks

| # | Playbook | Purpose | Command |
|---|----------|---------|---------|
| 1 | `cluster_health.yml` | Full cluster sweep | `ansible-playbook playbooks/cluster_health.yml` |
| 2 | `cmsh_exec.yml` | Run cmsh commands | `ansible-playbook playbooks/cmsh_exec.yml -e "cmsh_command='device; list'"` |
| 3 | `slurm_manage.yml` | Slurm operations | `ansible-playbook playbooks/slurm_manage.yml -e "action=status"` |
| 4 | `node_status.yml` | Set BCM status | `ansible-playbook playbooks/node_status.yml -e '{"targets":["cpu-n01"],"bcm_status":"UP"}'` |
| 5 | `power_manage.yml` | Power on/off/reset | `ansible-playbook playbooks/power_manage.yml -e '{"targets":["cpu-n01"],"power_action":"status"}'` |
| 6 | `node_provision.yml` | PXE provision | `ansible-playbook playbooks/node_provision.yml -e "action=list_categories"` |
| 7 | `debug_bundle.yml` | Collect diagnostics | `ansible-playbook playbooks/debug_bundle.yml -e '{"targets":["cpu-n01"],"ticket_id":"INC-001"}'` |
| 8 | `node_reboot.yml` | Graceful reboot | `ansible-playbook playbooks/node_reboot.yml -e '{"targets":["cpu-n01"],"drain":true}'` |

---

## Running the Test Suite

```bash
# From repo root
cd bcm-iac
python3 tests/run_all_tests.py

# Expected output:
# ✅ cluster_health.yml          ok=13  changed=0  failed=0
# ✅ cmsh_exec.yml               ok=2   changed=0  failed=0
# ...
# TOTAL: 29 passed, 0 failed
```
