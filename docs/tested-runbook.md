# BCM 11.0 Lab — Copy-Paste Command Reference

> All output below is **real** — captured from a live BCM 11.0 lab on 2026-03-09.
> Copy-paste any command block directly into your terminal.

---

## Quick Access

```bash
# SSH into BCM head node
sshpass -p '' ssh -o StrictHostKeyChecking=no root@192.168.122.186

# BCM Web UI (Base View)
# URL:  https://192.168.122.186:8081/base-view/
# User: admin
# Pass: system
```

---

## 1. cmsh — Device Management

### List all devices

```bash
cmsh -c 'device list'
```

```
Type             Hostname         MAC                Category  IP               Network          Status
---------------- ---------------- ------------------ --------- ---------------- ---------------- ---------------------------------
HeadNode         bcm11-headnode   52:54:00:27:A5:0C             192.168.200.254  internalnet      [   UP   ], health check failed
PhysicalNode     node001          52:54:00:8D:5D:F8  default   192.168.200.1    internalnet      [  DOWN  ], pingable
PhysicalNode     node002          52:54:00:D0:19:FC  default   192.168.200.2    internalnet      [  DOWN  ]
PhysicalNode     node003          52:54:00:E0:F0:AB  default   192.168.200.3    internalnet      [  DOWN  ]
```

### List categories

```bash
cmsh -c 'category list'
```

```
Name                  Software image    Nodes
--------------------- ----------------- -----
default               default-image     3
```

### List software images

```bash
cmsh -c 'softwareimage list'
```

```
Name              Path                     Kernel            Nodes
----------------- ------------------------ ----------------- -----
default-image     /cm/images/default-image  6.8.0-51-generic  3
```

### List configuration overlays

```bash
cmsh -c 'configurationoverlay list'
```

```
Name                 Priority   All HN   Categories       Roles
-------------------- ---------- -------- ---------------- ----------------
slurm-accounting     500        yes                       slurmaccounting
slurm-client         500        no       default          slurmclient
slurm-server         500        yes                       slurmserver
slurm-submit         500        no       default          slurmsubmit
wlm-headnode-submit  600        yes                       slurmsubmit
```

### List networks

```bash
cmsh -c 'network list'
```

```
Name               Type           Mask  Network          Domain               DHCP
------------------ -------------- ----- ---------------- -------------------- ----
externalnet        External       24    192.168.200.0    nvidia.com           no
globalnet          Global         0     0.0.0.0          cm.cluster
internalnet        Internal       24    192.168.200.0    cluster.local
```

### List partitions

```bash
cmsh -c 'partition list'
```

```
Name    Cluster name         Head node
------- -------------------- ---------
base    BCM 11.0 Cluster     bcm11-headnode
```

### Set a node MAC address (interactive cmsh)

```bash
cmsh
device
use node001
set mac 52:54:00:8D:5D:F8
commit
quit
```

---

## 2. Slurm Commands

### Cluster overview

```bash
sinfo
```

```
PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
defq*        up   infinite      3  idle* node[001-003]
```

### Detailed partition view

```bash
sinfo -l
```

```
Mon Mar 09 18:19:55 2026
PARTITION AVAIL  TIMELIMIT   JOB_SIZE ROOT OVERSUBS     GROUPS  NODES       STATE RESERVATION NODELIST
defq*        up   infinite 1-infinite   no       NO        all      3       idle*             node[001-003]
```

### Node details

```bash
scontrol show nodes
```

```
NodeName=node001 CoresPerSocket=1
   CPUAlloc=0 CPUEfctv=1 CPUTot=1 CPULoad=0.00
   AvailableFeatures=location=local
   ActiveFeatures=location=local
   Gres=(null)
   NodeAddr=node001 NodeHostName=node001
   RealMemory=1 AllocMem=0 FreeMem=N/A Sockets=1 Boards=1
   State=IDLE+NOT_RESPONDING ThreadsPerCore=1
   Partitions=defq
   CfgTRES=cpu=1,mem=1M,billing=1

NodeName=node002 CoresPerSocket=1
   State=IDLE+NOT_RESPONDING
   Partitions=defq
   CfgTRES=cpu=1,mem=1M,billing=1

NodeName=node003 CoresPerSocket=1
   State=IDLE+NOT_RESPONDING
   Partitions=defq
   CfgTRES=cpu=1,mem=1M,billing=1
```

### Partition configuration

```bash
scontrol show partitions
```

```
PartitionName=defq
   AllowGroups=ALL AllowAccounts=ALL AllowQos=ALL
   AllocNodes=ALL Default=YES QoS=N/A
   DefaultTime=UNLIMITED DisableRootJobs=NO
   MaxNodes=UNLIMITED MaxTime=UNLIMITED MinNodes=1
   Nodes=node[001-003]
   State=UP TotalCPUs=3 TotalNodes=3
   TRES=cpu=3,mem=3M,node=3,billing=3
```

### Accounting cluster info

```bash
sacctmgr show cluster
```

```
   Cluster     ControlHost  ControlPort   RPC     Share
---------- --------------- ------------ ----- ---------
     slurm 192.168.200.254         6817 11008         1
```

### Job queue

```bash
squeue
```

```
  JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
```

### Resume down nodes

```bash
scontrol update nodename=node001 state=resume reason="manual"
scontrol update nodename=node002 state=resume reason="manual"
scontrol update nodename=node003 state=resume reason="manual"
```

### Slurm version

```bash
sinfo --version
```

```
slurm 25.05.5
```

---

## 3. Service Health

```bash
systemctl is-active cmd slurmctld slurmdbd
```

```
active
active
active
```

```bash
systemctl status cmd | head -6
```

```
● cmd.service - BCM daemon
     Active: active (running)
     Main PID: 2814 (safe_cmd)
     Memory: 278.0M
```

---

## 4. Ansible Playbooks (Inside VM)

### Install Ansible

```bash
apt-get install -y ansible sshpass
ansible --version
```

```
ansible [core 2.16.3]
```

### Inventory (`/root/ansible/inventory.ini`)

```ini
[headnode]
bcm11-headnode ansible_connection=local

[compute]
node001 ansible_host=192.168.200.1
node002 ansible_host=192.168.200.2
node003 ansible_host=192.168.200.3

[compute:vars]
ansible_user=root
ansible_ssh_common_args='-o StrictHostKeyChecking=no'

[all:children]
headnode
compute
```

### Run Cluster Health Check

```bash
ansible-playbook -i /root/ansible/inventory.ini /root/ansible/playbooks/cluster-health.yml
```

```
PLAY [BCM Cluster Health Check] ************************************************

TASK [Gathering Facts] *********************************************************
ok: [bcm11-headnode]

TASK [Get hostname] ************************************************************
changed: [bcm11-headnode]

TASK [Get BCM device status] ***************************************************
changed: [bcm11-headnode]

TASK [Get Slurm partition status] **********************************************
changed: [bcm11-headnode]

TASK [Get Slurm node details] **************************************************
changed: [bcm11-headnode]

TASK [Get BCM service status] **************************************************
changed: [bcm11-headnode]

TASK [Get cluster accounting info] *********************************************
changed: [bcm11-headnode]

TASK [Display Cluster Health Report] *******************************************
ok: [bcm11-headnode] => {
    "msg": "=== BCM CLUSTER HEALTH REPORT ===\n
           Hostname: bcm11-headnode\n
           === Device List ===\n
           HeadNode  bcm11-headnode  [UP], health check failed\n
           node001   [DOWN], pingable\n
           node002   [DOWN]\n
           node003   [DOWN]\n
           === Slurm ===\n
           defq*  up  infinite  3  idle*  node[001-003]\n
           === Services ===\n
           active active active"
}

PLAY RECAP *********************************************************************
bcm11-headnode  : ok=8  changed=6  unreachable=0  failed=0  skipped=0
```

### Run BCM Config Audit

```bash
ansible-playbook -i /root/ansible/inventory.ini /root/ansible/playbooks/bcm-config.yml
```

```
PLAY [BCM Configuration Audit] *************************************************

TASK [Get categories] **********************************************************
changed: [bcm11-headnode]

TASK [Get software images] *****************************************************
changed: [bcm11-headnode]

TASK [Get configuration overlays] **********************************************
changed: [bcm11-headnode]

TASK [Get networks] ************************************************************
changed: [bcm11-headnode]

TASK [Get partition info] ******************************************************
changed: [bcm11-headnode]

TASK [Display BCM Configuration] ***********************************************
ok: [bcm11-headnode] => {
    "msg": "=== CATEGORIES ===\n  default  default-image  3\n
           === SOFTWARE IMAGES ===\n  default-image  /cm/images/default-image  6.8.0-51-generic  3\n
           === OVERLAYS ===\n  slurm-accounting  slurm-client  slurm-server  slurm-submit  wlm-headnode-submit\n
           === NETWORKS ===\n  externalnet  internalnet  globalnet\n
           === PARTITIONS ===\n  base  BCM 11.0 Cluster  bcm11-headnode"
}

PLAY RECAP *********************************************************************
bcm11-headnode  : ok=6  changed=5  unreachable=0  failed=0  skipped=0
```

### Run Slurm Operations

```bash
ansible-playbook -i /root/ansible/inventory.ini /root/ansible/playbooks/slurm-ops.yml
```

```
PLAY [Slurm Operations] ********************************************************

TASK [Get Slurm version] *******************************************************
changed: [bcm11-headnode]

TASK [Show all partitions] *****************************************************
changed: [bcm11-headnode]

TASK [Resume all nodes] ********************************************************
changed: [bcm11-headnode]     (ignored error: nodes already idle)

TASK [Verify node state after resume] ******************************************
changed: [bcm11-headnode]

TASK [Display Slurm Report] ****************************************************
ok: [bcm11-headnode] => {
    "msg": "=== SLURM slurm 25.05.5 ===\n
           defq*  up  infinite  3  idle*  node[001-003]\n
           Job Queue: (empty)"
}

PLAY RECAP *********************************************************************
bcm11-headnode  : ok=9  changed=8  unreachable=0  failed=0  ignored=1
```

---

## 5. Environment Info

| Key | Value |
|-----|-------|
| **Head Node** | bcm11-headnode (192.168.200.254) |
| **External IP** | 192.168.122.186 |
| **Compute Nodes** | node001 (.200.1), node002 (.200.2), node003 (.200.3) |
| **BCM Version** | 11.0 |
| **Slurm Version** | 25.05.5 |
| **OS** | Ubuntu 24.04.1 LTS |
| **Kernel** | 6.8.0-51-generic |
| **Ansible** | 2.16.3 |
| **Software Image** | default-image |
| **Category** | default (3 nodes) |
| **Partition** | defq (default, unlimited time) |
| **BCM Web UI** | https://192.168.122.186:8081/base-view/ (admin/system) |
