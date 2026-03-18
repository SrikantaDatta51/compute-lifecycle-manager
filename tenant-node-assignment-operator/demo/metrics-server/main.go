// Package main runs a Prometheus metrics server that simulates the
// Compute Platform Operator's controller-runtime metrics AND per-step
// workflow state transitions with timing.
package main

import (
	"fmt"
	"math/rand"
	"net/http"
	"sync"
	"time"
)

var (
	mu sync.Mutex

	// === Standard controller-runtime metrics ===
	reconcileTotal   = 0
	reconcileErrors  = 0
	reconcileRequeue = 0
	queueDepth       = 2
	goroutines       = 47
	memAlloc   int64 = 45 * 1024 * 1024
	memSys     int64 = 128 * 1024 * 1024
	isLeader         = 1

	// Phase counters
	phaseReady         = 0
	phasePending       = 1
	phaseLabelApplied  = 0
	phaseAwaitingAgent = 0
	phaseFailed        = 0

)

// StepMetric records the state of a single workflow step.
type StepMetric struct {
	Name     string
	CR       string
	Owner    string
	Node     string
	Status   string // pending, running, completed, waiting, failed
	Duration float64
	StartTs  int64
	EndTs    int64
}

var steps []StepMetric

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	defer mu.Unlock()

	w.Header().Set("Content-Type", "text/plain")

	// === controller-runtime reconcile metrics ===
	fmt.Fprintf(w, "# HELP controller_runtime_reconcile_total Total reconciliations.\n")
	fmt.Fprintf(w, "# TYPE controller_runtime_reconcile_total counter\n")
	fmt.Fprintf(w, "controller_runtime_reconcile_total{controller=\"tenantnodeassignment\",result=\"success\"} %d\n", reconcileTotal)
	fmt.Fprintf(w, "controller_runtime_reconcile_total{controller=\"tenantnodeassignment\",result=\"error\"} %d\n", reconcileErrors)
	fmt.Fprintf(w, "controller_runtime_reconcile_total{controller=\"tenantnodeassignment\",result=\"requeue\"} %d\n", reconcileRequeue)

	// Reconcile duration histogram
	fmt.Fprintf(w, "# HELP controller_runtime_reconcile_time_seconds Reconciliation duration.\n")
	fmt.Fprintf(w, "# TYPE controller_runtime_reconcile_time_seconds histogram\n")
	for _, le := range []string{"0.005", "0.01", "0.025", "0.05", "0.1", "0.25", "0.5", "1", "+Inf"} {
		fmt.Fprintf(w, "controller_runtime_reconcile_time_seconds_bucket{controller=\"tenantnodeassignment\",le=\"%s\"} %d\n", le, reconcileTotal)
	}
	fmt.Fprintf(w, "controller_runtime_reconcile_time_seconds_sum{controller=\"tenantnodeassignment\"} %f\n", float64(reconcileTotal)*0.012)
	fmt.Fprintf(w, "controller_runtime_reconcile_time_seconds_count{controller=\"tenantnodeassignment\"} %d\n", reconcileTotal)

	// Work queue
	fmt.Fprintf(w, "# HELP workqueue_depth Current depth of workqueue.\n")
	fmt.Fprintf(w, "# TYPE workqueue_depth gauge\n")
	fmt.Fprintf(w, "workqueue_depth{name=\"tenantnodeassignment\"} %d\n", queueDepth)

	// Leader
	fmt.Fprintf(w, "# HELP leader_election_master_status Lease held.\n")
	fmt.Fprintf(w, "# TYPE leader_election_master_status gauge\n")
	fmt.Fprintf(w, "leader_election_master_status{name=\"compute-platform-operator\"} %d\n", isLeader)

	// Go runtime
	fmt.Fprintf(w, "# HELP go_goroutines Number of goroutines.\n")
	fmt.Fprintf(w, "# TYPE go_goroutines gauge\n")
	fmt.Fprintf(w, "go_goroutines %d\n", goroutines)
	fmt.Fprintf(w, "# HELP go_memstats_alloc_bytes Bytes allocated.\n")
	fmt.Fprintf(w, "# TYPE go_memstats_alloc_bytes gauge\n")
	fmt.Fprintf(w, "go_memstats_alloc_bytes %d\n", memAlloc)
	fmt.Fprintf(w, "# HELP go_memstats_sys_bytes Bytes from system.\n")
	fmt.Fprintf(w, "# TYPE go_memstats_sys_bytes gauge\n")
	fmt.Fprintf(w, "go_memstats_sys_bytes %d\n", memSys)

	// Phase distribution
	fmt.Fprintf(w, "# HELP compute_platform_cr_phase_total CRs in each phase.\n")
	fmt.Fprintf(w, "# TYPE compute_platform_cr_phase_total gauge\n")
	fmt.Fprintf(w, "compute_platform_cr_phase_total{phase=\"Ready\"} %d\n", phaseReady)
	fmt.Fprintf(w, "compute_platform_cr_phase_total{phase=\"Pending\"} %d\n", phasePending)
	fmt.Fprintf(w, "compute_platform_cr_phase_total{phase=\"LabelApplied\"} %d\n", phaseLabelApplied)
	fmt.Fprintf(w, "compute_platform_cr_phase_total{phase=\"AwaitingNodeAgent\"} %d\n", phaseAwaitingAgent)
	fmt.Fprintf(w, "compute_platform_cr_phase_total{phase=\"Failed\"} %d\n", phaseFailed)

	// === Workflow step metrics ===
	fmt.Fprintf(w, "# HELP compute_platform_step_status Current status of each workflow step (0=pending, 1=running, 2=completed, 3=waiting, 4=failed).\n")
	fmt.Fprintf(w, "# TYPE compute_platform_step_status gauge\n")
	for _, s := range steps {
		statusVal := 0
		switch s.Status {
		case "pending":
			statusVal = 0
		case "running":
			statusVal = 1
		case "completed":
			statusVal = 2
		case "waiting":
			statusVal = 3
		case "failed":
			statusVal = 4
		}
		fmt.Fprintf(w, "compute_platform_step_status{step=\"%s\",cr=\"%s\",owner=\"%s\",node=\"%s\"} %d\n",
			s.Name, s.CR, s.Owner, s.Node, statusVal)
	}

	fmt.Fprintf(w, "# HELP compute_platform_step_duration_seconds Duration of each workflow step.\n")
	fmt.Fprintf(w, "# TYPE compute_platform_step_duration_seconds gauge\n")
	for _, s := range steps {
		fmt.Fprintf(w, "compute_platform_step_duration_seconds{step=\"%s\",cr=\"%s\",owner=\"%s\",node=\"%s\"} %f\n",
			s.Name, s.CR, s.Owner, s.Node, s.Duration)
	}

	fmt.Fprintf(w, "# HELP compute_platform_step_start_timestamp_seconds Unix timestamp when step started.\n")
	fmt.Fprintf(w, "# TYPE compute_platform_step_start_timestamp_seconds gauge\n")
	for _, s := range steps {
		if s.StartTs > 0 {
			fmt.Fprintf(w, "compute_platform_step_start_timestamp_seconds{step=\"%s\",cr=\"%s\",owner=\"%s\",node=\"%s\"} %d\n",
				s.Name, s.CR, s.Owner, s.Node, s.StartTs)
		}
	}

	// Current workflow phase (string-valued via label)
	fmt.Fprintf(w, "# HELP compute_platform_workflow_current_step Current step index (1-based) in the workflow.\n")
	fmt.Fprintf(w, "# TYPE compute_platform_workflow_current_step gauge\n")
	currentStep := 0
	for i, s := range steps {
		if s.Status == "running" || s.Status == "waiting" {
			currentStep = i + 1
		} else if s.Status == "completed" && currentStep == 0 {
			currentStep = i + 1
		}
	}
	fmt.Fprintf(w, "compute_platform_workflow_current_step{cr=\"assign-gpu-01\",workflow=\"node-assignment\"} %d\n", currentStep)
}

func simulate() {
	cr := "assign-gpu-01"
	owner := "team-alpha"
	node := "gpu-node-01"

	// Define workflow steps with realistic timings
	workflowSteps := []struct {
		name     string
		duration time.Duration
		isWait   bool // true if this step waits for an external signal
	}{
		{"1-validate-spec", 200 * time.Millisecond, false},
		{"2-fetch-node", 800 * time.Millisecond, false},
		{"3-set-owner-label", 1200 * time.Millisecond, false},
		{"4-wait-agent-ready", 12 * time.Second, true},
		{"5-update-configmap", 600 * time.Millisecond, false},
	}

	// Initialize all steps as pending
	mu.Lock()
	steps = make([]StepMetric, len(workflowSteps))
	for i, ws := range workflowSteps {
		steps[i] = StepMetric{
			Name: ws.name, CR: cr, Owner: owner, Node: node,
			Status: "pending", Duration: 0,
		}
	}
	mu.Unlock()

	fmt.Println("🚀 Scenario 1: Node Assignment — starting workflow")
	fmt.Printf("   CR=%s  owner=%s  node=%s\n\n", cr, owner, node)

	for i, ws := range workflowSteps {
		startTime := time.Now()

		// Mark step as running (or waiting for external signal)
		mu.Lock()
		if ws.isWait {
			steps[i].Status = "waiting"
			fmt.Printf("   ⏳ [%s] WAITING for external signal...\n", ws.name)
		} else {
			steps[i].Status = "running"
			fmt.Printf("   🔄 [%s] RUNNING...\n", ws.name)
		}
		steps[i].StartTs = startTime.Unix()
		reconcileTotal += 1 + rand.Intn(2)
		if ws.isWait {
			reconcileRequeue += 1 + rand.Intn(2)
			queueDepth = 1
		}
		mu.Unlock()

		// Simulate step execution time
		time.Sleep(ws.duration)

		// Mark step as completed
		mu.Lock()
		elapsed := time.Since(startTime).Seconds()
		steps[i].Status = "completed"
		steps[i].Duration = elapsed
		steps[i].EndTs = time.Now().Unix()
		reconcileTotal += 1
		queueDepth = max(0, queueDepth-1)

		// Update phase
		switch i {
		case 0: // validate done
			phasePending = 1
		case 1: // fetch done
			phasePending = 1
		case 2: // label applied
			phasePending = 0
			phaseLabelApplied = 1
		case 3: // agent ready
			phaseLabelApplied = 0
			phaseAwaitingAgent = 0
			phaseReady = 0
			phaseLabelApplied = 0
		case 4: // configmap updated = READY
			phaseReady = 1
			phasePending = 0
			phaseLabelApplied = 0
			phaseAwaitingAgent = 0
		}

		goroutines = 44 + rand.Intn(6)
		memAlloc = int64(43+rand.Intn(5)) * 1024 * 1024
		mu.Unlock()

		fmt.Printf("   ✅ [%s] COMPLETED in %.1fs\n", ws.name, elapsed)
	}

	queueDepth = 0
	fmt.Println("\n   🎉 Workflow COMPLETE — CR is now READY")
	fmt.Println("   📊 Open Grafana → Workflow State Timeline to see the full lifecycle")
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func main() {
	fmt.Println("═══════════════════════════════════════════════════════")
	fmt.Println("  Compute Platform Operator — Metrics Server")
	fmt.Println("  Serving Prometheus metrics on :8080/metrics")
	fmt.Println("  Grafana: http://localhost:3000 (admin/admin)")
	fmt.Println("  Prometheus: http://localhost:9090")
	fmt.Println("═══════════════════════════════════════════════════════")

	http.HandleFunc("/metrics", metricsHandler)

	go func() {
		time.Sleep(5 * time.Second)
		simulate()
	}()

	fmt.Println("\n📡 Metrics server listening on :8080...")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		fmt.Printf("Failed to start metrics server: %v\n", err)
	}
}
