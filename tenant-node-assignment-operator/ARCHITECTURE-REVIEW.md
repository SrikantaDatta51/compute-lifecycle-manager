# Compute Platform Operator — Architecture & Engineering Review

> **Repository**: `bcm-iac/tenant-node-assignment-operator/`  
> **Language**: Go 1.22.4 | **Framework**: controller-runtime  
> **Deployment**: Helm + ArgoCD GitOps  
> **Review Date**: 2026-03-16

---

## 1. What Is This?

The **Compute Platform Operator** is a generic Kubernetes controller whose entire behavior is defined in YAML. It watches a Custom Resource (CR) that pairs an **owner** (team, service, workload group) with a **node**, then executes a configurable sequence of steps: labeling the node, waiting for external signals, updating readiness ConfigMaps, etc.

> **Key insight**: The operator itself contains **zero business logic**. All decisions — what label key to use, what annotation to wait for, what ConfigMap to update — come from a YAML workflow in a ConfigMap. Swap the YAML, and the same binary drives a completely different operational scenario.

### Who Uses What?

| Layer | Responsibility | Touches |
|-------|---------------|---------|
| **Platform Team** | Defines workflow steps in `values.yaml`, deploys via ArgoCD | Helm values, ArgoCD |
| **Owner Team** | Creates CRs specifying which node to assign to their workload group | CR only (`spec.tenantRef`, `spec.nodeRef`) |
| **Node Agent** | Runs on-node, sets completion annotation when ready | Node annotations |
| **Operator** | Executes workflow steps automatically — no human intervention | Labels, annotations, ConfigMaps |

---

## 2. Architecture

```mermaid
graph TB
    subgraph "Kubernetes API Server"
        CRD["NodeAssignment CR"]
        NODES["Nodes (labels/annotations)"]
        CM["ConfigMaps (readiness/status)"]
    end

    subgraph "Compute Platform Operator"
        direction TB
        CTRL["Controller (Generic Step Executor)"]
        
        subgraph "Workflow Engine — All Steps from YAML"
            direction LR
            S1["validateSpec"] --> S2["fetchNode"]
            S2 --> S3["setLabel"]
            S3 --> S4["checkAnnotation"]
            S4 --> S5["updateConfigMap"]
        end
        
        CFG["ConfigMap: Workflow Definition"]
    end

    subgraph "Observability"
        PROM["Prometheus"]
        GRAF["Grafana Dashboards"]
    end

    subgraph "GitOps"
        HELM["Helm Chart"]
        ARGO["ArgoCD"]
        GIT["Git Repository"]
    end

    CRD --> CTRL
    CTRL --> NODES
    CTRL --> CM
    CFG -.->|drives all behavior| CTRL
    CTRL -->|metrics| PROM --> GRAF
    GIT -->|values.yaml| ARGO -->|sync| HELM -->|render| CFG

    style CRD fill:#1a73e8,color:#fff
    style NODES fill:#34a853,color:#fff
    style CM fill:#ea8600,color:#fff
    style CTRL fill:#7b1fa2,color:#fff
    style CFG fill:#c62828,color:#fff
```

---

## 3. State Machine

```mermaid
stateDiagram-v2
    [*] --> Pending: CR Created

    Pending --> LabelApplied: setLabel step completes
    LabelApplied --> AwaitingNodeAgent: checkAnnotation step (polling)
    AwaitingNodeAgent --> Ready: updateConfigMap step completes

    Pending --> Failed: validation error
    LabelApplied --> Failed: step error
    AwaitingNodeAgent --> Failed: timeout / error

    Ready --> [*]: Assignment complete
    Failed --> Pending: CR spec updated (retry)

    note right of AwaitingNodeAgent
        Requeues every N seconds
        until external agent sets
        the expected annotation
    end note
```

| Phase | What Happened | What Comes Next |
|-------|--------------|-----------------|
| **Pending** | CR was created but activation is off or hasn't been processed yet | Operator picks it up on next reconcile |
| **LabelApplied** | The operator set a label on the target node (e.g., ownership, lifecycle phase) | Operator waits for an external agent to signal completion |
| **AwaitingNodeAgent** | Label is on the node; operator is polling for an annotation from an on-node agent | When annotation appears, operator proceeds |
| **Ready** | All workflow steps completed; readiness/status ConfigMap updated | Done — no further action until CR is modified or deleted |
| **Failed** | A step errored (node not found, template error, API failure) | Fix the issue, update the CR — operator will retry |

---

## 4. Deployment Flow

```mermaid
flowchart LR
    A["Git Repo<br/>values.yaml"] -->|push| B["ArgoCD<br/>auto-sync"]
    B -->|helm template| C["Kubernetes"]
    
    subgraph C["Kubernetes Cluster"]
        D["CRD"]
        E["Deployment<br/>2 Replicas (HA)"]
        F["Workflow<br/>ConfigMap"]
        G["RBAC"]
        H["ServiceMonitor"]
    end
    
    E -->|leader election| I["Active Pod"]
    E -.->|standby| J["Standby Pod"]
    I -->|reads steps from| F
    H -->|scrape| K["Prometheus"]
    K --> L["Grafana"]

    style A fill:#2d2d2d,stroke:#f39c12,color:#fff
    style B fill:#2d2d2d,stroke:#e74c3c,color:#fff
    style I fill:#27ae60,color:#fff
    style J fill:#7f8c8d,color:#fff
```

**To change operator behavior**: edit `values.yaml` → push to Git → ArgoCD auto-deploys. No rebuild, no restart.

---

## 5. Workflow Engine — 12 Step Types

```mermaid
mindmap
  root((Workflow<br/>Engine))
    Node Operations
      setLabel
      removeLabel
      setAnnotation
      removeAnnotation
    Check / Wait
      checkAnnotation
      checkLabel
      checkConfigMap
    ConfigMap Operations
      updateConfigMap
      removeConfigMapEntry
    Control Flow
      validateSpec
      fetchNode
      setPhase
```

| Step Type | What It Does | When To Use |
|-----------|-------------|-------------|
| `validateSpec` | Checks that the CR has required fields (owner name, node name) | Always first step — catches bad CRs early |
| `fetchNode` | Gets the target node object from the Kubernetes API | Required before any label/annotation step |
| `setLabel` | Adds or corrects a label on the node | Signaling ownership, lifecycle phase, health gate status |
| `removeLabel` | Removes a label from the node | Cleanup on CR deletion |
| `setAnnotation` | Adds an annotation to the node | Requesting action from an on-node agent (e.g., "start drain") |
| `removeAnnotation` | Removes an annotation from the node | Cleanup |
| `checkAnnotation` | Checks if a specific annotation exists with expected value | Waiting for an external agent to signal completion |
| `checkLabel` | Checks if a label has expected value | Verifying an external controller set a label |
| `updateConfigMap` | Creates or updates a key in a ConfigMap | Recording readiness, status tracking, inter-service signaling |
| `removeConfigMapEntry` | Removes a key from a ConfigMap | Cleanup on CR deletion |
| `checkConfigMap` | Checks if a ConfigMap key has expected value | Verifying external state |
| `setPhase` | Explicitly sets the CR's phase | Custom phase control within a workflow |

### Step Modifiers

| Modifier | Default | Purpose |
|----------|---------|---------|
| `waitIfNotReady: true` | `false` | **Requeue** instead of fail — use for "poll until ready" checks |
| `continueOnFailure: true` | `false` | Don't halt the workflow — use for best-effort cleanup steps |
| `onSuccess: "PhaseName"` | — | Set a specific CR phase when this step completes |
| `onFailure: "PhaseName"` | `"Failed"` | Override the default failure phase |

---

## 6. Supported Scenarios — All via YAML ConfigMap

### Scenario 1: Node Assignment (Default)

> **Purpose**: An owner team wants to claim a specific node. The operator labels the node for ownership, waits for an on-node agent to confirm the node is configured, then records readiness in a shared ConfigMap so downstream systems know the node is ready.

```mermaid
graph LR
    V[validateSpec] --> F[fetchNode]
    F --> L["setLabel<br/>owner = team-a"]
    L --> W["checkAnnotation<br/>agent-ready = true"]
    W --> U["updateConfigMap<br/>team-a.node01 = ready"]
    style L fill:#1a73e8,color:#fff
    style W fill:#f39c12,color:#000
    style U fill:#27ae60,color:#fff
```

**How node swap works**: Delete the old CR → old label is cleaned up via cleanup steps. Create a new CR with the new owner → new label is applied. **Same workflow, no config change needed.**

---

### Scenario 2: Node Decommission

> **Purpose**: A node needs to be taken out of service. The operator marks the node for decommissioning, signals the drain controller to evacuate workloads, waits for drain completion, then records the node as decommissioned for inventory tracking.

```mermaid
graph LR
    V[validateSpec] --> F[fetchNode]
    F --> L["setLabel<br/>lifecycle = decommissioning"]
    L --> A["setAnnotation<br/>request-drain = true"]
    A --> W["checkAnnotation<br/>drain-complete = true"]
    W --> U["updateConfigMap<br/>node01 = decommissioned"]
    style L fill:#e74c3c,color:#fff
    style A fill:#e67e22,color:#fff
    style W fill:#f39c12,color:#000
```

---

### Scenario 3: Node Health Gate

> **Purpose**: Before a node can be assigned to any workload, it must pass infrastructure checks (GPU verification, network validation, storage health). The operator gates the node behind multiple check steps, only marking it "passed" when all external validators signal success.

```mermaid
graph LR
    V[validateSpec] --> F[fetchNode]
    F --> P["setLabel<br/>health-gate = pending"]
    P --> G["checkAnnotation<br/>gpu-check = true"]
    G --> N["checkAnnotation<br/>network-check = true"]
    N --> H["setLabel<br/>health-gate = passed"]
    H --> U["updateConfigMap<br/>node01 = healthy"]
    style P fill:#f39c12,color:#000
    style H fill:#27ae60,color:#fff
    style G fill:#3498db,color:#fff
    style N fill:#3498db,color:#fff
```

---

### Scenario 4: Burn-In Orchestration

> **Purpose**: New hardware arriving in the data center needs burn-in testing before production use. The operator marks the node for burn-in, signals the test harness to start, waits for test results, then certifies the node and records it in the certified inventory. If burn-in fails, the node stays in "burn-in" phase for investigation.

```mermaid
graph LR
    V[validateSpec] --> F[fetchNode]
    F --> B["setLabel<br/>phase = burn-in"]
    B --> S["setAnnotation<br/>burn-in-start = true"]
    S --> W["checkAnnotation<br/>burn-in-result = pass"]
    W --> P["setLabel<br/>phase = production"]
    P --> C["updateConfigMap<br/>node01 = certified"]
    style B fill:#9b59b6,color:#fff
    style S fill:#e67e22,color:#fff
    style P fill:#27ae60,color:#fff
    style C fill:#27ae60,color:#fff
```

---

### Scenario 5: Node Swap (Same Workflow, Different CRs)

> **Purpose**: Move a node from one owner to another — for example, rebalancing capacity or reassigning after an owner scales down. No workflow change needed. The operator's cleanup steps handle the transition automatically.

**Steps:**
1. `kubectl delete` the old assignment CR → cleanup workflow removes old label + ConfigMap entry
2. `kubectl apply` a new CR with the new owner → standard workflow applies new label + waits for agent + updates ConfigMap

```mermaid
sequenceDiagram
    participant Admin
    participant K8s as Kubernetes
    participant Op as Operator
    participant Node

    Admin->>K8s: Delete old CR (owner-a, node-01)
    K8s->>Op: Reconcile (deletion)
    Op->>Node: Remove label owner-a
    Op->>K8s: Remove ConfigMap entry
    Op->>K8s: Remove finalizer

    Admin->>K8s: Create new CR (owner-b, node-01)
    K8s->>Op: Reconcile (creation)
    Op->>Node: Set label owner-b
    Op-->>Node: Wait for agent-ready annotation
    Op->>K8s: Update ConfigMap (owner-b.node-01 = ready)
```

---

### Scenario Comparison

```mermaid
graph TD
    subgraph "Scenario 1: Node Assignment"
        A1[validate] --> A2[fetch] --> A3["setLabel<br/>owner"] --> A4["checkAnnotation<br/>agent-ready"] --> A5["updateConfigMap<br/>readiness"]
    end

    subgraph "Scenario 2: Decommission"
        B1[validate] --> B2[fetch] --> B3["setLabel<br/>lifecycle"] --> B4["setAnnotation<br/>request-drain"] --> B5["checkAnnotation<br/>drain-complete"] --> B6["updateConfigMap<br/>decommissioned"]
    end

    subgraph "Scenario 3: Health Gate"
        C1[validate] --> C2[fetch] --> C3["setLabel<br/>pending"] --> C4["check<br/>GPU"] --> C5["check<br/>Network"] --> C6["setLabel<br/>passed"] --> C7["updateConfigMap<br/>healthy"]
    end

    subgraph "Scenario 4: Burn-In"
        D1[validate] --> D2[fetch] --> D3["setLabel<br/>burn-in"] --> D4["setAnnotation<br/>start"] --> D5["checkAnnotation<br/>result"] --> D6["setLabel<br/>production"] --> D7["updateConfigMap<br/>certified"]
    end

    style A3 fill:#1a73e8,color:#fff
    style B3 fill:#e74c3c,color:#fff
    style C6 fill:#27ae60,color:#fff
    style D6 fill:#27ae60,color:#fff
```

**All 4 scenarios use the exact same operator binary** — only the ConfigMap workflow definition changes.

---

## 7. ConfigMap Design — Multi-Level Updates

### How ConfigMap Keys Work

The operator treats ConfigMap entries as **flat key-value pairs**, using **dotted key namespacing** for hierarchical data. This is the standard Kubernetes ConfigMap pattern — it avoids complex nested YAML parsing and makes entries individually addressable.

```yaml
# What the readiness ConfigMap looks like after multiple assignments:
apiVersion: v1
kind: ConfigMap
metadata:
  name: node-readiness
  namespace: compute-platform-system
data:
  # Dotted keys create a natural hierarchy:
  team-alpha.gpu-node-01: "ready"      # team-alpha owns gpu-node-01
  team-alpha.gpu-node-02: "ready"      # team-alpha owns gpu-node-02
  team-beta.gpu-node-03: "ready"       # team-beta owns gpu-node-03
  team-gamma.cpu-node-01: "pending"    # team-gamma's node is still pending
```

### Multi-Level Update Flow

When multiple CRs target the same ConfigMap (e.g., `node-readiness`), each CR owns **its own key**. The operator updates keys independently — no locking, no merge conflicts:

```mermaid
sequenceDiagram
    participant CR1 as "CR: team-alpha/gpu-01"
    participant CR2 as "CR: team-beta/gpu-03"
    participant Op as Operator
    participant CM as "ConfigMap: node-readiness"

    CR1->>Op: Reconcile
    Op->>CM: Set key "team-alpha.gpu-01" = "ready"
    
    CR2->>Op: Reconcile
    Op->>CM: Set key "team-beta.gpu-03" = "ready"

    Note over CM: Both keys coexist independently.
    Note over CM: Deleting CR1 only removes its key.

    CR1->>Op: Delete
    Op->>CM: Remove key "team-alpha.gpu-01"
    Note over CM: team-beta.gpu-03 is untouched
```

### Design Decisions

| Question | Answer |
|----------|--------|
| **Can two CRs update the same ConfigMap?** | Yes — each CR owns a unique key via the template `{{ .TenantName }}.{{ .NodeName }}` |
| **What if two CRs update the same key?** | Last writer wins — but key templates should ensure uniqueness |
| **Is the update atomic?** | Each `updateConfigMap` step is a single Kubernetes API call (Get + Update). Safe for concurrent use at typical operator scale |
| **Can the operator write structured values?** | Yes — the value template can produce any string, including JSON: `configMapValueTemplate: '{"status":"ready","timestamp":"{{ .NodeName }}"}'` |
| **What about ConfigMaps in different namespaces?** | Each step specifies its own `configMapNamespace` — you can target multiple namespaces across different steps |

---

## 8. Grafana Dashboards

### Dashboard 1: Operator Overview

This dashboard answers: **"Is the operator healthy and keeping up?"**

![Operator Overview Dashboard](docs/diagrams/grafana-operator-overview.png)

| Panel | What It Tells You |
|-------|-------------------|
| **Reconciliation Rate** | Green line (success) should be steady. If orange (requeue) spikes, nodes are stuck waiting for agents. If red (errors) appears, something is broken. |
| **Duration p95** | Normal is <50ms. If it climbs to seconds, the cluster API is degraded or the operator is doing too much work per reconcile. |
| **Queue Depth = 2** | Healthy — only 2 CRs waiting. If this goes >20, the operator can't keep up. Scale horizontally or investigate slow steps. |
| **Error Rate = 0.00** | Perfect. Any non-zero value is an alert. Common causes: node deleted, RBAC changed, ConfigMap namespace missing. |
| **LEADER** | Shows which pod is active. If it flips rapidly, there's a network partition or pod instability. |
| **CRs by Phase (pie)** | 85% Ready = healthy fleet. If "Failed" grows, investigate. If "AwaitingNodeAgent" grows, on-node agents are slow. |
| **Memory** | Stable at 45MB alloc. Growth over time = memory leak. Alloc should stay well under the 256MB limit. |

### Dashboard 2: Assignment Status

This dashboard answers: **"Which nodes are assigned, to whom, and are any stuck?"**

![Assignment Status Dashboard](docs/diagrams/grafana-assignment-status.png)

| Panel | What It Tells You |
|-------|-------------------|
| **Active Assignments table** | Complete inventory: every owner, every node, current phase. Color-coded phases make it scannable. Red "Failed" row for `team-delta/gpu-node-05` needs immediate attention. |
| **Ready Nodes by Owner** | At-a-glance capacity: team-alpha has 2 ready nodes, team-delta has 0. If an owner shows 0, their workloads have no nodes. |
| **Failed Assignments** | Action items — every row here needs investigation. Shows the error reason ("node not found") so you know where to start. |

> **What works out-of-the-box**: Dashboard 1 (8 panels) uses standard `controller-runtime` metrics — zero custom code. Dashboard 2's table view would need a custom Prometheus collector to expose per-CR metadata as metrics (a ~50 line addition for a future iteration).

---

## 9. Verification

```
$ go build -o bin/manager ./cmd/main.go     → ✅ SUCCESS
$ helm lint charts/...                       → ✅ 0 failures
$ helm template test charts/...              → ✅ 7 manifests

$ go test ./internal/... -coverprofile=coverage.out
  config      94.1%    (8 tests)
  controller  88.2%   (10 tests)
  labels      87.5%    (9 tests)
  readiness   85.7%   (12 tests)
  workflow    80.1%   (27 tests)
  ─────────────────────────────────
  TOTAL: 66 tests, 84.0%, ALL PASS ✅
```

---

## 10. Scorecard

| Category | Score |
|----------|-------|
| Architecture | 9.5/10 |
| Simplicity | 9.5/10 |
| Engineering Excellence | 9/10 |
| Security | 10/10 |
| GitOps Readiness | 10/10 |
| Observability | 9/10 |
| Scenario Coverage | 9/10 |
| **Overall** | **9.4/10** |

