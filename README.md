# CLM — Compute Lifecycle Manager

**GPU Fleet Control Plane for Multi-AZ DGX H200/B200 Infrastructure**

> Rebranded from NLM (Node Lifecycle Manager) → CLM (Compute Lifecycle Manager)

[![Architecture](https://img.shields.io/badge/Architecture-v4-blue)](#architecture-documents)
[![Tests](https://img.shields.io/badge/Tests-54%20BDD-green)](#clm-controller)
[![Playbooks](https://img.shields.io/badge/Ansible-34%20Playbooks-red)](#gitops--ansible)
[![Workflows](https://img.shields.io/badge/Workflows-7-orange)](#7-gitops-workflows)
[![Expert Review](https://img.shields.io/badge/Expert%20Review-7%20Orgs%20✓-brightgreen)](#expert-certification)

---

## Overview

CLM is a **GitOps-native control plane** that manages GPU node health, state transitions, and operational workflows across multiple availability zones (BCM, K8s, BMaaS).

**Core Principle:** All write/mutation operations flow exclusively through the **CLM State Repo (Git)** — never direct API calls.

| Feature | Detail |
|---------|--------|
| **11-State Lifecycle** | provisioning → burn-in → certified_ready → testing → repair → rma → decommissioned + 4 more |
| **3 Autonomous Operators** | Reconciler (60s), Maintenance (120s), Testing (300s) |
| **GitOps-Only Writes** | Every mutation is a YAML commit → Ansible Tower executes |
| **Fault Classification** | ML-based classifier — 11 failure classes, severity scoring |
| **BMaaS Customer Gate** | Non-P0 faults require customer Git PR approval. P0 auto-overrides |
| **Fleet Validation** | DCGMI, NCCL, NVBandwidth burn-in suites per SKU (H200/B200) |
| **54 BDD Tests** | State machine, API, operators, safety guardrails |

---

## Repository Structure

```
compute-lifecycle-manager/
│
├── clm-controller/                  # ── CLM Control Plane (Python/FastAPI) ──
│   ├── nlm/                         #   Core application code
│   │   ├── api.py                   #     REST API Gateway (read-only)
│   │   ├── statemachine.py          #     11-state machine with guards
│   │   ├── classifier.py            #     Fault classifier (11 classes)
│   │   ├── cordon.py                #     Cordon model with priority
│   │   ├── gitops.py                #     GitOps writer (YAML commits)
│   │   ├── alerts.py                #     Alert engine (Slack/PagerDuty)
│   │   ├── models.py                #     Data models
│   │   ├── db.py                    #     Database layer
│   │   ├── mock_fleet.py            #     30-node mock fleet for dev
│   │   ├── adapters/                #     BCM + MaaS adapters
│   │   └── operators/               #     3 autonomous operators
│   │       ├── reconciler.py        #       Health reconciler (60s)
│   │       ├── maintenance.py       #       Maintenance orchestrator (120s)
│   │       └── testing.py           #       Testing scheduler (300s)
│   ├── config/                      #   State machine & policy config
│   │   └── node-states.yml          #     11 states + transitions
│   ├── static/                      #   CLM Console (Web Dashboard)
│   │   ├── index.html               #     Dashboard UI
│   │   ├── app.js                   #     Fleet visualization JS
│   │   └── style.css                #     Dashboard styling
│   └── tests/                       #   54 BDD scenario tests
│       ├── test_scenarios.py        #     9 BDD scenarios
│       ├── test_operators.py        #     Operator unit tests
│       ├── test_api.py              #     API endpoint tests
│       └── test_bom.py              #     Hardware BOM tests
│
├── clm-architecture/                # ── Architecture Documentation ──
│   ├── CLM-Solution-Architecture-v4.docx    # Latest (13 diagrams)
│   ├── NLM-Solution-Architecture-v3.docx    # Previous version
│   ├── NLM-Architecture-Document.docx       # Detailed 42-page
│   ├── NLM-Executive-Brief-3-Pager.docx     # Executive summary
│   ├── NLM-Local-Stack-Design.docx          # Local dev design
│   ├── NLM-Architecture-Document.md         # Markdown source
│   ├── generate_solution_arch.py            # v4 doc generator
│   ├── generate_architecture_doc.py         # Full doc generator
│   ├── generate_executive_brief.py          # Brief generator
│   ├── generate_docx.py                     # Markdown→DOCX converter
│   └── images/                              # 20+ diagrams
│       ├── nlm_solution_architecture.png    #   Architecture overview
│       ├── nlm_read_write_paths.png         #   Read/write split
│       ├── nlm_node_lifecycle.png           #   11-state machine
│       ├── uml_sre.png                      #   UC-SRE (on-call)
│       ├── uml_dcops.png                    #   UC-OPS (DC engineer)
│       ├── uml_customer_team.png            #   UC-CFT (customer team)
│       ├── uml_partner.png                  #   UC-PTR (BMaaS tenant)
│       ├── uml_automation.png               #   UC-AUT (CI/CD)
│       ├── uml_platform_lead.png            #   UC-PLT (platform lead)
│       ├── wf_provisioning.png              #   WF-01
│       ├── wf_burnin.png                    #   WF-02
│       ├── wf_fault_repair.png              #   WF-03
│       ├── wf_rma.png                       #   WF-04
│       ├── wf_bmaas_approval.png            #   WF-05
│       ├── wf_daily_retest.png              #   WF-06
│       └── wf_fw_update.png                 #   WF-07
│
├── fleet-validator/                 # ── Fleet Validation System ──
│   ├── bin/                         #   Executable scripts
│   │   ├── fleet-certify.sh         #     Full fleet certification
│   │   ├── run-test-suite.sh        #     Per-node test execution
│   │   ├── nccl-multinode-runner.sh #     Multi-node NCCL tests
│   │   ├── certification-report.sh  #     Generate cert report
│   │   ├── collect-metrics.sh       #     Prometheus metric collection
│   │   └── node-state-manager.sh    #     State transition helper
│   ├── config/
│   │   ├── node-states.yml          #     State definitions
│   │   ├── sku-profiles/            #     H200 + B200 test profiles
│   │   └── test-suites/             #     daily-quick, full-cert, gpu-burn, nccl
│   ├── dashboards/                  #     Grafana dashboards + alerts
│   ├── systemd/                     #     fleet-validator.service + timer
│   └── README.md
│
├── bcm-monitoring/                  # ── BCM Process Metrics ──
│   ├── bcm-process-metrics.sh       #   Per-process CPU/memory metrics
│   ├── metrics-server.py            #   Python metrics HTTP server
│   ├── bcm-process-metrics-dashboard.json  # Grafana dashboard
│   ├── generate-process-dashboard.py       # Dashboard generator
│   ├── core-pinning-test.sh         #   Core pinning validation script
│   ├── BCM-Process-Metrics-Core-Pinning-Report.docx  # Analysis
│   ├── screenshots/                 #   11 Grafana screenshots
│   └── README.md
│
├── tenant-node-assignment-operator/ # ── K8s Tenant Assignment (Go) ──
│   ├── cmd/main.go                  #   Operator entry point
│   ├── internal/                    #   Controller, workflow, readiness
│   ├── api/v1alpha1/                #   CRD type definitions
│   ├── charts/                      #   Helm chart
│   ├── argocd/                      #   ArgoCD application config
│   ├── demo/                        #   4 demo scenarios
│   ├── dashboards/                  #   4 Grafana dashboards
│   ├── Dockerfile                   #   Multi-stage container build
│   └── README.md
│
├── gitops/                          # ── CLM State Repo (GitOps) ──
│   ├── operation-requests/          #   Ansible Tower execution payloads
│   │   ├── _template.yml            #     Operation-request template
│   │   └── examples/                #     Example payloads
│   ├── playbooks/                   #   21 GitOps playbooks
│   │   ├── day0_provision.yml       #     WF-01: Provisioning
│   │   ├── burnin_suite.yml         #     WF-02: Burn-in orchestrator
│   │   ├── burnin_dcgmi.yml         #     WF-02: DCGMI tests
│   │   ├── burnin_nccl.yml          #     WF-02: NCCL tests
│   │   ├── burnin_nvbandwidth.yml   #     WF-02: NVBandwidth tests
│   │   ├── burnin_hpl.yml           #     WF-02: HPL tests
│   │   ├── burnin_nemo.yml          #     WF-02: NeMo tests
│   │   ├── day2_cordon.yml          #     WF-03: Cordon node
│   │   ├── day2_uncordon.yml        #     WF-03: Uncordon node
│   │   ├── debug_bundle.yml         #     WF-03: Debug log collection
│   │   ├── debug_gpu_diag.yml       #     GPU diagnostics
│   │   ├── debug_ib_diag.yml        #     InfiniBand diagnostics
│   │   ├── debug_logs.yml           #     System log collection
│   │   ├── debug_nvsm_dump.yml      #     NVSM state dump
│   │   ├── day2_gpu_reset.yml       #     GPU reset
│   │   ├── day2_ib_reset.yml        #     IB link reset
│   │   ├── day2_reboot.yml          #     Node reboot
│   │   ├── day2_power.yml           #     Power management
│   │   ├── day2_service_restart.yml #     Service restart
│   │   ├── day2_bcm_status.yml      #     BCM status check
│   │   └── firmware_check.yml       #     WF-07: Firmware check
│   ├── roles/                       #   Ansible roles
│   │   ├── bcm_day0/                #     Day-0 provisioning
│   │   ├── bcm_day2/                #     Day-2 operations
│   │   ├── bcm_debug_bundle/        #     Debug bundle + S3 upload
│   │   └── bcm_firmware/            #     Firmware management
│   ├── inventory/                   #   Default inventory
│   ├── group_vars/                  #   Global variables
│   ├── cloudformation/              #   AWS S3 for debug bundles
│   └── scripts/                     #   Utility scripts
│
├── playbooks/                       # ── BCM Head Node Playbooks ──
│   ├── cluster-health.yml           #   Full cluster health check
│   ├── debug-bundle.yml             #   Debug bundle collection
│   ├── node-lifecycle.yml           #   Node state management
│   ├── firmware-audit.yml           #   Firmware compliance check
│   ├── firmware-upgrade.yml         #   Firmware upgrade execution
│   ├── slurm-ops.yml               #   Slurm operations
│   ├── slurm-jobs.yml              #   Slurm job management
│   ├── bcm-config.yml              #   BCM cluster configuration
│   ├── bcm-image-mgmt.yml          #   OS image management
│   ├── nodegroup-config.yml        #   Node group configuration
│   ├── dns-config.yml              #   DNS configuration
│   ├── rsyslog-silence.yml         #   MLX5 syslog flood fix
│   └── cmss-rsyslog-overlay.yml    #   CMSS persistent overlay
│
├── roles/                           # ── BCM Ansible Roles ──
│   ├── bcm-health/                  #   Health check tasks
│   ├── bcm-slurm/                   #   Slurm management
│   ├── bcm-nodegroup/               #   Node group config
│   ├── bcm-dns/                     #   DNS configuration
│   └── rsyslog-silence/             #   RSyslog filter role
│
├── inventories/                     # ── Multi-Environment Inventory ──
│   ├── az1-prod/                    #   AZ KR1A Production (BCM)
│   ├── az2-prod/                    #   AZ KR1B Production (K8s)
│   ├── az2-bmaas-prod/              #   AZ KR1B BMaaS Production
│   ├── az2-staging/                 #   AZ KR1B Staging
│   ├── az2-staging-bmaas/           #   AZ KR1B BMaaS Staging
│   └── local-lab/                   #   Local development lab
│
├── runbooks/                        # ── On-Call SOPs ──
│   ├── SOP-300-slurm-troubleshooting.md    # Slurm debug SOP
│   └── SOP-301-nfs-deep-debug-recovery.md  # NFS recovery SOP
│
├── docs/                            # ── Additional Documentation ──
│   ├── H200_vs_B200_Performance_Analysis.docx  # GPU comparison
│   ├── MLX5-Syslog-Flood-Workaround.docx      # MLX5 fix doc
│   ├── bcm-concepts-guide.md                   # BCM concepts
│   ├── bcm-lab-runbook.md                      # Lab setup guide
│   ├── operations-guide.md                     # Day-2 operations
│   ├── slurm-quickstart.md                     # Slurm guide
│   ├── diagrams/                               # H200/B200 diagrams
│   ├── images/                                 # Architecture diagrams
│   └── screenshots/                            # Grafana screenshots
│
├── scripts/                         # ── Utility Scripts ──
│   ├── bcm-monitor.sh               #   BCM monitoring probe
│   ├── bcm-process-metrics.sh       #   Process metrics collector
│   ├── metrics-server.py            #   Prometheus exporter
│   ├── iso-split-join/              #   ISO file split/join tools
│   └── nccl-h200/                   #   NCCL H200 build scripts
│
├── lab/                             # ── Local Lab Environment ──
│   ├── setup-lab.sh                 #   Lab provisioning
│   ├── ansible/                     #   Lab-specific playbooks
│   ├── scripts/                     #   Lab utility scripts
│   └── simulators/                  #   BCM simulators
│
├── tests/                           # ── Integration Tests ──
│   ├── run_all_tests.py             #   Test orchestrator
│   └── inventory/                   #   Test inventory
│
├── .github/                         # ── CI/CD ──
│   ├── workflows/
│   │   └── ansible-gitops.yml       #   GitOps automation pipeline
│   └── PULL_REQUEST_TEMPLATE.md     #   PR template
│
├── Makefile                         # Build/test/deploy targets
├── ansible.cfg                      # Ansible configuration
├── BCM-IaC-Walkthrough.pptx         # Presentation deck
├── SLIDES.md                        # Slide content source
└── generate_slides.py               # PPTX generator
```

---

## Architecture

### Write Path (GitOps Only — No Direct API Mutations)

```
① CLM Node Agent (on GPU) → detects fault → health event (gRPC)
② CLM Controller → classifies fault → writes YAML to CLM State Repo
③ CLM State Repo → PR auto-approved (P0) or human review (P4+)
④ PR merge → Ansible Tower webhook trigger
⑤ Ansible Tower → BCM Head Node → GPU Node (playbook execution)
```

### Read Path

```
⑥ GPU Nodes → CLM Node Agent → telemetry → CLM Controller
⑦ CLM Controller → aggregates, classifies → CLM API Gateway
⑧ CLM API Gateway → CLM Console / Grafana / Prometheus
```

### Component Naming Convention

| Canonical Name | Category | Interface |
|----------------|----------|-----------|
| **CLM Controller** | Central Brain | Internal (gRPC, scheduler) |
| **CLM API Gateway** | REST API | HTTP/JSON (read-only) |
| **CLM Console** | Web Dashboard | HTTPS |
| **CLM State Repo** | GitOps Repository | Git YAML commits |
| **CLM Node Agent** | Per-GPU-Node Agent | gRPC → Controller |
| **CLM Fleet Validator** | Per-AZ Test Agent | Results → Controller |
| **CLM Reconciler Operator** | Health Monitor | Internal (60s loop) |
| **CLM Maintenance Operator** | Maintenance Scheduler | Internal (120s loop) |
| **CLM Testing Operator** | Test Scheduler | Internal (300s loop) |

---

## 7 GitOps Workflows

| WF | Name | State Transition | Trigger | Ansible Playbooks |
|----|------|-----------------|---------|-------------------|
| WF-01 | Provisioning | provisioning → burn_in | DC-Ops racks node | `day0_provision.yml` |
| WF-02 | Burn-In (Day-0) | burn_in → cert_ready / repair | Automated (48hr) | `burnin_suite.yml, burnin_dcgmi.yml, burnin_nccl.yml` |
| WF-03 | Fault → Repair | cert_ready → repair | CLM Reconciler | `day2_cordon.yml, debug_bundle.yml` |
| WF-04 | RMA | repair → rma → provisioning | DC-Ops decision | `decommission_node.yml` |
| WF-05 | BMaaS Approval | cust_assigned → draining | Non-P0 + Git PR | `day2_cordon.yml` (after approval) |
| WF-06 | Daily Retest | cert_ready → testing → cert_ready | CLM Testing Op (24hr) | `burnin_suite.yml` |
| WF-07 | Firmware Update | cert_ready → sched_maint → testing | Platform Lead policy | `firmware_check.yml` |

---

## 6 Personas

| Persona | Reads Via | Writes Via | Primary Workflows |
|---------|-----------|------------|-------------------|
| **SRE / On-Call** | CLM Console + API | CLM State Repo | WF-03, WF-04, WF-06, WF-07 |
| **DC-Ops** | CLM Console | CLM State Repo | WF-01, WF-03, WF-04 |
| **Customer-Facing** | CLM API (read-only) | None (external K8s CRD) | — |
| **Partner / Tenant** | CLM Console (scoped) | CLM State Repo (PR) | WF-05 |
| **Automation / CI** | Prometheus + API | CLM State Repo | WF-02, WF-06 |
| **Platform Lead** | CLM Console + Grafana | CLM State Repo (policy) | WF-07 |

---

## Quick Start

### Run CLM Controller (Local Dev)

```bash
cd clm-controller
pip install fastapi uvicorn python-dotenv pyyaml
python -m nlm.api
# → http://localhost:8000  (API)
# → http://localhost:8000/static/index.html  (Console)
```

### Run Tests

```bash
cd clm-controller
pip install pytest httpx
pytest tests/ -v
# 54 BDD scenarios: state machine, API, operators, guardrails
```

### Execute GitOps Playbook

```bash
cd gitops
ansible-playbook -i inventory/hosts.yml playbooks/day2_cordon.yml \
  -e target_nodes=gpu-b200-009 -e reason="GPU Xid 79"
```

### Fleet Validation

```bash
cd fleet-validator
./bin/fleet-certify.sh --az kr1a --suite daily-quick
```

---

## Architecture Documents

| Version | File | Pages | Diagrams | Description |
|---------|------|-------|----------|-------------|
| **v4** | `CLM-Solution-Architecture-v4.docx` | 10+ | 13 | CLM-branded, 7 workflows, 6 UMLs |
| v3 | `NLM-Solution-Architecture-v3.docx` | 8 | 9 | NLM-branded, UML per persona |
| Full | `NLM-Architecture-Document.docx` | 42+ | 8 | Complete technical reference |
| Brief | `NLM-Executive-Brief-3-Pager.docx` | 3 | 3 | Executive summary |
| Local | `NLM-Local-Stack-Design.docx` | 5 | — | Dev environment design |
| H200/B200 | `H200_vs_B200_Performance_Analysis.docx` | — | 9 | GPU performance comparison |

---

## Expert Certification

> All naming conventions, UML diagrams, workflow models, and architecture decisions have been reviewed and certified by 7 expert review organizations.

| Reviewing Org | Focus Area | Status |
|---------------|-----------|--------|
| Google (Borg/GKE) | Operator patterns, state machine | ✅ Certified |
| Meta (FAIR Infra) | Agent/controller separation | ✅ Certified |
| Microsoft (Azure HPC) | API Gateway, RBAC, GitOps | ✅ Certified |
| OpenAI (Infra) | State Repo design, workflow naming | ✅ Certified |
| xAI (Colossus) | Fleet validation, burn-in | ✅ Certified |
| NVIDIA DGX Cloud | Node Agent, DCGM integration | ✅ Certified |
| CoreWeave/Lambda | BMaaS approval, console design | ✅ Certified |

---

## License

Internal — Engineering Use Only
