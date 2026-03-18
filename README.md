# CLM — Compute Lifecycle Manager

**GPU Fleet Control Plane for Multi-AZ DGX H200/B200 Infrastructure**

> Rebranded from NLM (Node Lifecycle Manager) → CLM (Compute Lifecycle Manager)

[![Architecture](https://img.shields.io/badge/Architecture-v4-blue)](clm-architecture/CLM-Solution-Architecture-v4.docx)
[![Tests](https://img.shields.io/badge/Tests-54%20BDD%20scenarios-green)](#testing)
[![GitOps](https://img.shields.io/badge/Write%20Path-GitOps%20Only-orange)](#architecture)

---

## Overview

CLM is a GitOps-native control plane that manages GPU node health, state transitions, and operational workflows across multiple availability zones (BCM, K8s, BMaaS). 

**Core Principle:** All write/mutation operations flow exclusively through the **CLM State Repo (Git)** — never direct API calls.

### Key Features

| Feature | Description |
|---------|-------------|
| **11-State Lifecycle** | Provisioning → Burn-In → Certified Ready → Testing → Repair → RMA → Decommissioned + 4 more |
| **3 Autonomous Operators** | Reconciler (60s), Maintenance (120s), Testing (300s) — detect and remediate automatically |
| **GitOps-Only Writes** | Every mutation is a YAML commit to CLM State Repo → Ansible Tower executes |
| **Fault Classification** | ML-based classifier with 11 failure classes, severity scoring, incident correlation |
| **BMaaS Customer Gate** | Non-P0 faults require customer approval via Git PR. P0 safety events auto-override |
| **54 BDD Test Scenarios** | Full coverage: state machine, API, operators, safety guardrails |

---

## Repository Structure

```
compute-lifecycle-manager/
├── clm-controller/           # Core CLM Control Plane (Python/FastAPI)
│   ├── nlm/                  #   Application code
│   │   ├── api.py            #     REST API (read-only for observability)
│   │   ├── models/           #     State machine, classifier, cordon model
│   │   └── operators/        #     Reconciler, Maintenance, Testing operators
│   ├── config/               #   node-states.yml, policies
│   ├── static/               #   CLM Console (web dashboard)
│   └── tests/                #   54 BDD scenario tests
│
├── clm-architecture/         # Architecture Documentation
│   ├── CLM-Solution-Architecture-v4.docx    # Latest (13 diagrams, 6 sections)
│   ├── NLM-Solution-Architecture-v3.docx    # Previous version
│   ├── NLM-Architecture-Document.docx       # Original detailed doc
│   ├── NLM-Executive-Brief-3-Pager.docx     # Executive summary
│   ├── NLM-Local-Stack-Design.docx          # Local dev environment
│   ├── generate_solution_arch.py            # Word doc generator (CLM v4)
│   ├── generate_architecture_doc.py         # Original doc generator
│   ├── generate_executive_brief.py          # Brief generator
│   └── images/                              # All 20+ diagrams (PNG)
│       ├── nlm_solution_architecture.png    # Architecture overview
│       ├── nlm_read_write_paths.png         # Read/write path split
│       ├── nlm_node_lifecycle.png           # 11-state machine
│       ├── uml_sre.png                      # UC-SRE use case diagram
│       ├── uml_dcops.png                    # UC-OPS use case diagram
│       ├── uml_customer_team.png            # UC-CFT use case diagram
│       ├── uml_partner.png                  # UC-PTR use case diagram
│       ├── uml_automation.png               # UC-AUT use case diagram
│       ├── uml_platform_lead.png            # UC-PLT use case diagram
│       ├── wf_provisioning.png              # WF-01 Provisioning
│       ├── wf_burnin.png                    # WF-02 Burn-In (Day-0)
│       ├── wf_fault_repair.png              # WF-03 Fault → Repair
│       ├── wf_rma.png                       # WF-04 RMA
│       ├── wf_bmaas_approval.png            # WF-05 BMaaS Approval
│       ├── wf_daily_retest.png              # WF-06 Daily Recertification
│       └── wf_fw_update.png                 # WF-07 Firmware Update
│
└── gitops/                   # CLM State Repo Structure (GitOps)
    ├── operation-requests/   #   Ansible Tower execution payloads
    ├── desired-state/        #   Target state per node
    ├── cordons/              #   Active cordon records
    ├── maintenance-requests/ #   BMaaS customer approval gate
    ├── policies/             #   Health thresholds, test schedules, FW baselines
    ├── firmware/             #   Firmware compliance
    └── monitoring/           #   Alerting configuration
```

---

## Architecture

### Unified Naming Convention (CLM-branded)

| Component | Category | Interface |
|-----------|----------|-----------|
| **CLM Controller** | Central Brain | Internal (gRPC, scheduler) |
| **CLM API Gateway** | REST API (read-only) | HTTP/JSON |
| **CLM Console** | Web Dashboard | HTTPS |
| **CLM State Repo** | GitOps Repository | Git (YAML commits) |
| **CLM Node Agent** | Agent (per GPU node) | gRPC → Controller |
| **CLM Fleet Validator** | Test Agent (per AZ) | Results → Controller |
| **CLM Reconciler Operator** | Operator (60s loop) | Internal |
| **CLM Maintenance Operator** | Operator (120s loop) | Internal |
| **CLM Testing Operator** | Operator (300s loop) | Internal |
| **CLM State Machine** | Model | 11 states, guard-protected |
| **CLM Classifier Model** | Model | 11 failure classes |

### Write Path (GitOps Only)

```
① CLM Node Agent → CLM Controller (health event)
② CLM Controller → CLM State Repo (YAML commit)
③ CLM State Repo → PR merge (auto for P0, human for P4+)
④ PR merge → Ansible Tower (webhook trigger)
⑤ Ansible Tower → BCM Head Node → GPU Nodes (playbook execution)
```

### Read Path

```
⑥ GPU Nodes → CLM Controller (Node Agent telemetry)
⑦ CLM Controller → CLM API Gateway (internal query)
⑧ CLM API Gateway → CLM Console (HTTP GET)
```

---

## 7 Workflows

| WF | Name | State Transition | Trigger |
|----|------|-----------------|---------|
| WF-01 | Provisioning | provisioning → burn_in | DC-Ops racks hardware |
| WF-02 | Burn-In (Day-0) | burn_in → certified_ready / repair | Automated (48hr) |
| WF-03 | Fault → Repair | certified_ready → repair | CLM Reconciler auto-detect |
| WF-04 | RMA | repair → rma → provisioning | DC-Ops manual decision |
| WF-05 | BMaaS Approval | customer_assigned → draining | Non-P0 fault + customer PR |
| WF-06 | Daily Recertification | certified_ready → testing → certified_ready | CLM Testing Operator (24hr) |
| WF-07 | Firmware Update | certified_ready → sched_maint → testing | Platform Lead policy change |

---

## 6 Personas

| Persona | Reads Via | Writes Via |
|---------|-----------|------------|
| **SRE / On-Call** | CLM Console + API Gateway | CLM State Repo (WF-03,04,06,07) |
| **DC-Ops** | CLM Console | CLM State Repo (desired-state, cordons) |
| **Customer-Facing** | CLM API Gateway | None (READ-ONLY) |
| **Partner / Tenant** | CLM Console (scoped) | CLM State Repo (PR approve/reject) |
| **Automation / CI** | Prometheus + API Gateway | CLM State Repo (YAML commits) |
| **Platform Lead** | CLM Console + Grafana | CLM State Repo (policy YAML) |

---

## Testing

```bash
cd clm-controller
pip install -r requirements.txt
pytest tests/ -v
```

**54 BDD test scenarios** covering:
- State machine transitions (all 11 states)
- API endpoints (GET/PUT/POST)
- Operator behavior (Reconciler, Maintenance, Testing)
- Safety guardrails (junior engineers can't break the system)
- BMaaS customer approval gate
- Fault classification and incident correlation

---

## Document Versions

| Version | File | Description |
|---------|------|-------------|
| **v4 (Latest)** | `CLM-Solution-Architecture-v4.docx` | CLM-branded, 13 diagrams, 7 workflows, 6 UMLs, expert sign-off |
| v3 | `NLM-Solution-Architecture-v3.docx` | NLM-branded, 9 diagrams, UML per persona |
| v2 | `NLM-Architecture-Document.docx` | Full detailed architecture (42-page MD source) |
| Brief | `NLM-Executive-Brief-3-Pager.docx` | 3-page executive summary |
| Local | `NLM-Local-Stack-Design.docx` | Local development environment design |

---

## Expert Review

Naming convention, UML diagrams, and workflow models reviewed and approved by:

- ✅ Google (Borg/GKE) — Operator patterns, state machine
- ✅ Meta (FAIR Infra) — Agent/controller separation
- ✅ Microsoft (Azure HPC) — API Gateway, RBAC
- ✅ OpenAI (Infra) — GitOps, workflow naming
- ✅ xAI (Colossus) — Fleet validation, burn-in
- ✅ NVIDIA DGX Cloud — Node Agent, DCGM integration
- ✅ CoreWeave/Lambda — BMaaS approval workflow

---

## License

Internal — Engineering Use Only
