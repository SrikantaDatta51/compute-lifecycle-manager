# BCM Infrastructure as Code — Team Walkthrough

> Walk through this document top-to-bottom with your team.
> Each `---` marks a slide break.

---

## Slide 1: What We Built

### BCM IaC — One Repo, All Environments

```
Same playbooks → Different inventories → Different outcomes
```

| Environment | What It Is | Scale |
|---|---|---|
| **local-lab** | Your workstation — KVM VMs | 1 head + 3 nodes |
| **az2-staging** | AZ2 staging cluster | 1 CPU head + 1 GPU + few CPU |
| **az2-staging-bmaas** | BMaaS staging cluster | 1 head + 3 CPU + 1 GPU |
| **az2-bmaas-prod** | BMaaS production | 1 head + 66 DGX B200 |
| **az1-prod** | AZ1 production | TBD |
| **az2-prod** | AZ2 production | TBD |

**Key**: All environments run the **same playbooks**, just different inventory files.

---

## Slide 2: Repository Structure

```
bcm-iac/
├── SLIDES.md                ← THIS FILE — team presentation
├── ansible.cfg              ← SSH pipelining, YAML output
│
├── inventories/             ← WHERE: per-environment config
│   ├── local-lab/
│   ├── az2-staging/
│   ├── az2-staging-bmaas/
│   ├── az2-bmaas-prod/
│   ├── az1-prod/
│   └── az2-prod/
│
├── playbooks/               ← WHAT: 11 playbooks
│   ├── cluster-health.yml
│   ├── dns-config.yml
│   ├── nodegroup-config.yml
│   ├── firmware-audit.yml
│   ├── firmware-upgrade.yml
│   └── ...
│
├── roles/                   ← HOW: reusable logic
│   ├── bcm-dns/
│   ├── bcm-nodegroup/
│   ├── bcm-health/
│   └── bcm-slurm/
│
└── docs/                    ← DOCS: runbooks, SOPs
```

> **Rule of thumb**: `inventories/` = WHERE, `playbooks/` = WHAT, `roles/` = HOW.

---

## Slide 3: How to Run — Explicit Commands

### Pattern:
```bash
ansible-playbook -i inventories/<ENVIRONMENT>/hosts.yml playbooks/<PLAYBOOK>.yml
```

### Examples:
```bash
# Health check on local lab
ansible-playbook -i inventories/local-lab/hosts.yml playbooks/cluster-health.yml

# Configure DNS on production
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/dns-config.yml

# Firmware audit on staging
ansible-playbook -i inventories/az2-staging/hosts.yml playbooks/firmware-audit.yml

# Dry-run anything (add --check --diff)
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/dns-config.yml --check --diff

# Limit to specific tags
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-audit.yml --tags gpu,nic
```

---

## Slide 4: All 11 Playbooks — Quick Reference

| Playbook | What It Does | Example |
|---|---|---|
| `cluster-health.yml` | Check services, disk, memory, Slurm | `ansible-playbook -i inventories/local-lab/hosts.yml playbooks/cluster-health.yml` |
| `dns-config.yml` | Set nameservers, search domains via cmsh | `ansible-playbook -i inventories/az2-staging/hosts.yml playbooks/dns-config.yml` |
| `nodegroup-config.yml` | Manage categories, overlays, node assignments | `ansible-playbook -i inventories/az2-staging/hosts.yml playbooks/nodegroup-config.yml` |
| `firmware-audit.yml` | Collect BIOS, BMC, GPU, NIC firmware versions | `ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-audit.yml` |
| `firmware-upgrade.yml` | Upgrade firmware (dry-run default) | `ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-upgrade.yml` |
| `node-lifecycle.yml` | Power, provision, drain, resume nodes | `ansible-playbook -i inventories/local-lab/hosts.yml playbooks/node-lifecycle.yml` |
| `slurm-ops.yml` | Slurm partition management | `ansible-playbook -i inventories/local-lab/hosts.yml playbooks/slurm-ops.yml` |
| `slurm-jobs.yml` | Submit and monitor Slurm jobs | `ansible-playbook -i inventories/local-lab/hosts.yml playbooks/slurm-jobs.yml` |
| `debug-bundle.yml` | Collect diagnostic logs and GPU info | `ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/debug-bundle.yml` |
| `bcm-config.yml` | Audit BCM configuration objects | `ansible-playbook -i inventories/local-lab/hosts.yml playbooks/bcm-config.yml` |
| `bcm-image-mgmt.yml` | Audit and manage software images | `ansible-playbook -i inventories/local-lab/hosts.yml playbooks/bcm-image-mgmt.yml` |

---

## Slide 5: Environment Configuration

### Each environment has `inventories/<env>/group_vars/all.yml`

```yaml
# inventories/local-lab/group_vars/all.yml
env_name: local-lab
bcm_domain: "lab.local"
dns_nameservers: ["192.168.200.254", "8.8.8.8"]
bcm_categories:
  - name: default
    image: default-image
    nodes: [node001, node002, node003]
```

```yaml
# inventories/az2-bmaas-prod/group_vars/all.yml
env_name: az2-bmaas-prod
bcm_domain: "bmaas.prod.corp.internal"
dns_nameservers: ["10.20.200.254", "10.0.0.53"]
bcm_categories:
  - name: dgx-b200
    image: ubuntu24-dgx-b200
    node_range: "dgx-b200-[001-066]"
```

**Same playbook + different `group_vars` = different environment.**

---

## Slide 6: Working Example — DNS Configuration

### `playbooks/dns-config.yml`

Steps:
1. Sets global nameservers → `cmsh -c "base; set nameservers ..."`
2. Sets network domain → `cmsh -c "network; use internalnet; set domainname ..."`
3. Configures DNS per node category
4. Verifies with `nslookup` and `/etc/resolv.conf`

### Run on each environment:
```bash
# Test on local lab first
ansible-playbook -i inventories/local-lab/hosts.yml playbooks/dns-config.yml

# Promote to staging
ansible-playbook -i inventories/az2-staging/hosts.yml playbooks/dns-config.yml

# Then production
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/dns-config.yml
```

### Where to look:
| What | File |
|---|---|
| DNS variables | `inventories/<env>/group_vars/all.yml` → `dns_nameservers`, `dns_search_domains` |
| DNS playbook | `playbooks/dns-config.yml` |
| DNS role | `roles/bcm-dns/tasks/main.yml` |
| Best practices | `docs/bcm-dns-and-image-best-practices.md` |

---

## Slide 7: Working Example — Firmware Audit

### `playbooks/firmware-audit.yml`

Collects from every node:
| Component | Method | Tags |
|---|---|---|
| BIOS version | `dmidecode -t bios` | `--tags bios` |
| BMC firmware | `ipmitool mc info` | `--tags bmc` |
| GPU driver + VBIOS | `nvidia-smi --query-gpu` | `--tags gpu` |
| NIC firmware | `mlxfwmanager --query` | `--tags nic` |
| BCM + Slurm | `cmsh get version` | `--tags bcm` |

```bash
# Full audit
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-audit.yml

# GPU only
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-audit.yml --tags gpu

# Report saved to: /tmp/firmware-audit-<env>/firmware-audit-<timestamp>.md
```

---

## Slide 8: Working Example — Firmware Upgrade (Safety-First)

### `playbooks/firmware-upgrade.yml`

**Dry-run by default** — must pass `-e fw_apply=true` to actually apply.

| Step | What Happens | Tag |
|---|---|---|
| 1. Pre-flight | Checks Slurm, aborts if jobs running | `--tags pre-check` |
| 2. Drain | Removes nodes from Slurm | `--tags drain` |
| 3. Upgrade GPU | Updates driver in BCM image | `--tags upgrade-gpu` |
| 4. Upgrade BIOS | Flashes BIOS firmware | `--tags upgrade-bios` |
| 5. Upgrade BMC | Updates BMC firmware | `--tags upgrade-bmc` |
| 6. Upgrade NIC | Flashes Mellanox ConnectX | `--tags upgrade-nic` |
| 7. Reboot | Reboots nodes, waits 120s | `--tags reboot` |
| 8. Verify | Re-checks all versions | `--tags verify` |
| 9. Resume | Puts nodes back in Slurm | `--tags resume` |

```bash
# Dry-run (see what would happen)
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-upgrade.yml

# Apply GPU driver upgrade
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-upgrade.yml \
  -e fw_apply=true -e target_gpu_driver=560

# Apply NIC firmware only
ansible-playbook -i inventories/az2-bmaas-prod/hosts.yml playbooks/firmware-upgrade.yml \
  -e fw_apply=true -e nic_firmware_file=/path/to/fw.bin --tags upgrade-nic,reboot,verify,resume
```

---

## Slide 9: Day-0 Operations (Initial Setup)

> Run **once** when onboarding a new cluster.

| # | Operation | Command |
|---|---|---|
| 1 | Health baseline | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/cluster-health.yml` |
| 2 | BCM config audit | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/bcm-config.yml` |
| 3 | Image audit | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/bcm-image-mgmt.yml` |
| 4 | Configure DNS | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/dns-config.yml` |
| 5 | Setup node categories | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/nodegroup-config.yml` |
| 6 | Provision nodes | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/node-lifecycle.yml` |
| 7 | Setup Slurm | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/slurm-ops.yml` |
| 8 | Firmware audit | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/firmware-audit.yml` |
| 9 | Firmware upgrade | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/firmware-upgrade.yml -e fw_apply=true` |

**Execution order**: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

---

## Slide 10: Day-2 Operations (Ongoing Management)

> Run **repeatedly** for maintenance and troubleshooting.

| # | Operation | Command | Frequency |
|---|---|---|---|
| 1 | Health check | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/cluster-health.yml` | Daily |
| 2 | Debug bundle | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/debug-bundle.yml` | On incident |
| 3 | Power cycle node | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/node-lifecycle.yml` | As needed |
| 4 | Reprovision node | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/node-lifecycle.yml` | After RMA |
| 5 | Job monitoring | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/slurm-jobs.yml` | Daily |
| 6 | Image update | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/bcm-image-mgmt.yml` | On patch |
| 7 | DNS change | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/dns-config.yml` | On network change |
| 8 | Category change | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/nodegroup-config.yml` | On scale |
| 9 | Firmware upgrade | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/firmware-upgrade.yml -e fw_apply=true` | Quarterly |
| 10 | Firmware audit | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/firmware-audit.yml` | Monthly |

---

## Slide 11: Image vs Overlay — Quick Reference

| ✅ In the **Image** | ✅ In the **Overlay** |
|---|---|
| OS base packages | `/etc/resolv.conf` (DNS) |
| NVIDIA GPU drivers | NTP servers |
| CUDA toolkit | LDAP client config |
| Container runtime | Mount points (`/scratch`) |
| Slurm client (`slurmd`) | SSH authorized_keys |
| Monitoring agents | Kernel parameters |
| System libs | Network bonding |

> **Golden Rule**: Binaries → Image. Config files that vary → Overlay.

Full guide: `docs/bcm-dns-and-image-best-practices.md`

---

## Slide 12: Promotion Flow

```
local-lab → az2-staging → az2-staging-bmaas → az2-bmaas-prod
   │              │                │                    │
   ▼              ▼                ▼                    ▼
 Dev/Test      Staging        BMaaS Staging       Production
(your VMs)   (real HW)       (BMaaS test)     (66 B200 nodes)
```

### Workflow:
1. **Develop** playbook changes on `local-lab` (KVM VMs)
2. **Test** on `az2-staging` (real hardware, small scale)
3. **Validate** on `az2-staging-bmaas` (BMaaS-specific test)
4. **Deploy** to `az2-bmaas-prod` (production, 66 nodes)
5. All on `main` branch — no branch-per-env

---

## Slide 13: Where to Find Things

| I want to... | Look at... |
|---|---|
| See what's in an environment | `inventories/<env>/group_vars/all.yml` |
| See what a playbook does | `playbooks/<name>.yml` |
| See reusable logic | `roles/<name>/tasks/main.yml` |
| Run a playbook | `ansible-playbook -i inventories/<env>/hosts.yml playbooks/<name>.yml` |
| Dry-run something | Append `--check --diff` to any command |
| Run specific tags only | Append `--tags <tag1>,<tag2>` |
| Understand BCM concepts | `docs/bcm-concepts-guide.md` |
| Copy-paste tested commands | `docs/tested-runbook.md` |
| DNS + image best practices | `docs/bcm-dns-and-image-best-practices.md` |
| VM configs for local lab | `lab/vm-configs/*.xml` |

---

## Slide 14: Testing Backlog

| Priority | Playbook | Status |
|---|---|---|
| P0 | `cluster-health.yml` | ✅ Tested on local-lab |
| P0 | `dns-config.yml` | 🔲 Need nodes UP |
| P0 | `nodegroup-config.yml` | 🔲 Need nodes UP |
| P1 | `node-lifecycle.yml` | ✅ Tested on local-lab |
| P1 | `slurm-ops.yml` | ✅ Tested on local-lab |
| P1 | `debug-bundle.yml` | ✅ Tested on local-lab |
| P1 | `firmware-audit.yml` | 🔲 Need nodes UP |
| P1 | `firmware-upgrade.yml` | 🔲 Need nodes UP |
| P2 | `bcm-image-mgmt.yml` | ✅ Tested on local-lab |
| P2 | `bcm-config.yml` | ✅ Tested on local-lab |
| P2 | `slurm-jobs.yml` | ✅ Tested on local-lab |

### Planned Additions
- [ ] `burn-in-test.yml` — post-RMA node validation
- [ ] `ldap-config.yml` — LDAP/authentication setup
- [ ] `network-bonding.yml` — IB/ETH bond configuration
- [ ] CI/CD pipeline (lint on PR + dry-run on merge)
- [ ] Ansible Vault for secrets management
