# Demo — Compute Platform Operator MVP

## What This Demonstrates

Scenario 1 (Node Assignment) running end-to-end with **real Grafana dashboards** fed by
a live Prometheus → metrics server stack. No Docker, no Kubernetes cluster needed.

## Architecture

```
demo/metrics-server (Go)    →  Simulates controller-runtime metrics
        ↓ :8080/metrics
   Prometheus v3.3.0        →  Scrapes every 5s
        ↓ :9090
   Grafana v11.5.2           →  8-panel Operator Overview dashboard
        ↓ :3000
   Browser screenshots       →  Captured in demo/scenario-1-node-assignment/
```

## Quick Start

```bash
# 1. Start the metrics simulator (emits controller-runtime & custom phase metrics)
go run demo/metrics-server/main.go &

# 2. Start Prometheus (downloads separately — see below)
prometheus --config.file=demo/prometheus.yml --storage.tsdb.path=/tmp/prometheus-data &

# 3. Start Grafana (downloads separately — see below)
cd /path/to/grafana && ./bin/grafana server --homepath=. &

# 4. Run the workflow demo harness (all 4 scenarios)
go run demo/main.go
```

## Demo Harness Output

`demo/main.go` runs the **real workflow engine** (`internal/workflow/engine.go`) against
a fake Kubernetes API. All 4 scenarios complete with numbered steps:

| Scenario | Steps | Final State |
|----------|-------|-------------|
| 1. Node Assignment | 5 | ✅ READY — label set, ConfigMap updated |
| 2. Node Decommission | 6 | ✅ DECOMMISSIONED — drain complete, recorded |
| 3. Node Health Gate | 7 | ✅ HEALTHY — GPU+Network checks passed |
| 4. Burn-In | 7 | ✅ CERTIFIED — burn-in passed, production ready |

## Grafana Evidence (Scenario 1)

| File | Description |
|------|-------------|
| `scenario-1-node-assignment/grafana-dashboard-top.png` | Real Grafana — top panels |
| `scenario-1-node-assignment/grafana-dashboard-bottom.png` | Real Grafana — bottom panels |
| `scenario-1-node-assignment/grafana-recording.webp` | Browser recording of live dashboard |

### What the Panels Show

- **Reconciliation Rate**: success/requeue/error lines (success dominant)
- **Duration p95/p50**: sub-50ms latency
- **Queue Depth**: 0 (no backlog)
- **Errors**: 0 (stable)
- **Active Leader**: LEADER (green)
- **Go Goroutines**: ~47 (stable)
- **Phase Pie Chart**: Ready=1 (Scenario 1 completed)
- **Memory**: ~45MB alloc, ~128MB sys (stable)
