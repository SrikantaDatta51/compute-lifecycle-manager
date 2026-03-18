// Package main implements a demo harness for the Compute Platform Operator.
// It runs all 4 workflow scenarios end-to-end using the real workflow engine
// against a simulated Kubernetes API (fake client).
package main

import (
	"context"
	"fmt"
	"os"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	cpv1alpha1 "github.com/compute-platform/tenant-node-assignment-operator/api/v1alpha1"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/labels"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/workflow"
)

// ANSI colors
const (
	Reset   = "\033[0m"
	Bold    = "\033[1m"
	Red     = "\033[31m"
	Green   = "\033[32m"
	Yellow  = "\033[33m"
	Blue    = "\033[34m"
	Magenta = "\033[35m"
	Cyan    = "\033[36m"
	White   = "\033[37m"
	BgBlue  = "\033[44m"
	BgGreen = "\033[42m"
	Dim     = "\033[2m"
)

func banner(color, title, desc string) {
	w := 70
	fmt.Println()
	fmt.Printf("%s%s%s\n", color, Bold, strings.Repeat("═", w))
	pad := (w - len(title)) / 2
	if pad < 0 {
		pad = 0
	}
	fmt.Printf("%s%s%s%s\n", color, Bold, strings.Repeat(" ", pad)+title, Reset)
	fmt.Printf("%s%s%s\n", color, strings.Repeat("═", w), Reset)
	if desc != "" {
		fmt.Printf("%s  %s%s\n", Dim, desc, Reset)
	}
}

func stepHeader(num int, name, desc string) {
	fmt.Printf("\n  %s%s❯ Step %d: %s%s\n", Bold, Cyan, num, name, Reset)
	if desc != "" {
		fmt.Printf("    %s%s%s\n", Dim, desc, Reset)
	}
}

func stepResult(result workflow.StepResult) {
	if result.Completed {
		fmt.Printf("    %s✓ COMPLETED%s — %s\n", Green, Reset, result.Message)
	} else if result.Waiting {
		fmt.Printf("    %s⏳ WAITING%s — %s\n", Yellow, Reset, result.Message)
	} else if result.Failed {
		fmt.Printf("    %s✗ FAILED%s — %s\n", Red, Reset, result.Message)
	}
}

func showNodeState(node *corev1.Node) {
	fmt.Printf("\n  %s%s📋 Node State: %s%s\n", Bold, White, node.Name, Reset)
	if len(node.Labels) > 0 {
		fmt.Printf("    %sLabels:%s\n", Dim, Reset)
		for k, v := range node.Labels {
			if strings.HasPrefix(k, "compute-platform.io/") {
				fmt.Printf("      %s%s%s = %s%s%s\n", Cyan, k, Reset, Green, v, Reset)
			}
		}
	}
	if len(node.Annotations) > 0 {
		fmt.Printf("    %sAnnotations:%s\n", Dim, Reset)
		for k, v := range node.Annotations {
			if strings.HasPrefix(k, "compute-platform.io/") {
				fmt.Printf("      %s%s%s = %s%s%s\n", Magenta, k, Reset, Green, v, Reset)
			}
		}
	}
}

func showConfigMap(ctx context.Context, fakeClient interface{ Get(context.Context, types.NamespacedName, ...interface{}) error }, ns, name string) {
	// This is handled in the validation functions
}

func pass(msg string) {
	fmt.Printf("    %s%s✅  PASS: %s%s\n", Bold, Green, msg, Reset)
}

func fail(msg string) {
	fmt.Printf("    %s%s❌  FAIL: %s%s\n", Bold, Red, msg, Reset)
	os.Exit(1)
}

func separator() {
	fmt.Printf("\n%s%s%s\n", Dim, strings.Repeat("─", 70), Reset)
}

// runScenario executes a complete workflow scenario
func runScenario(ctx context.Context, scenarioNum int, color, title, description string,
	steps []workflow.Step, tna *cpv1alpha1.TenantNodeAssignment, node *corev1.Node,
	preStepHooks map[int]func(context.Context, *workflow.ExecutionContext),
	validations func(context.Context, *workflow.ExecutionContext)) {

	banner(color, fmt.Sprintf("Scenario %d: %s", scenarioNum, title), description)

	// Build scheme and fake client
	scheme := runtime.NewScheme()
	_ = clientgoscheme.AddToScheme(scheme)
	_ = cpv1alpha1.AddToScheme(scheme)

	ns := &corev1.Namespace{ObjectMeta: metav1.ObjectMeta{Name: "compute-platform-system"}}

	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(node, ns).
		WithStatusSubresource(&cpv1alpha1.TenantNodeAssignment{}).
		Build()

	executor := workflow.NewExecutor(fakeClient)

	ec := &workflow.ExecutionContext{
		Client: fakeClient,
		TNA:    tna,
		TmplData: labels.TemplateData{
			TenantName: tna.Spec.TenantRef.Name,
			NodeName:   tna.Spec.NodeRef.Name,
		},
	}

	fmt.Printf("\n  %s%sCR:%s %s (owner=%s, node=%s)\n",
		Bold, White, Reset, tna.Name, tna.Spec.TenantRef.Name, tna.Spec.NodeRef.Name)

	allPassed := true
	for i, step := range steps {
		if hook, ok := preStepHooks[i]; ok {
			hook(ctx, ec)
		}

		stepHeader(i+1, step.Name, step.Description)
		result := executor.ExecuteStep(ctx, step, ec)
		stepResult(result)

		if result.Failed && !step.ContinueOnFailure {
			allPassed = false
			break
		}

		if result.Waiting {
			if hook, ok := preStepHooks[-(i + 1)]; ok {
				fmt.Printf("    %s🔔 Simulating external agent signal...%s\n", Yellow, Reset)
				hook(ctx, ec)
				// Re-fetch node after agent update
				updatedNode := &corev1.Node{}
				if err := fakeClient.Get(ctx, types.NamespacedName{Name: node.Name}, updatedNode); err == nil {
					ec.Node = updatedNode
				}
				result = executor.ExecuteStep(ctx, step, ec)
				stepResult(result)
			}
		}
	}

	// Show final node state
	updatedNode := &corev1.Node{}
	if err := fakeClient.Get(ctx, types.NamespacedName{Name: node.Name}, updatedNode); err == nil {
		ec.Node = updatedNode
		showNodeState(updatedNode)
	}

	// Run validations
	if validations != nil {
		separator()
		fmt.Printf("  %s%s🔍 Validations:%s\n", Bold, White, Reset)
		validations(ctx, ec)
	}

	if allPassed {
		fmt.Printf("\n  %s%s  ══════════════════════════════════════════  %s\n", BgGreen, Bold, Reset)
		fmt.Printf("  %s%s    ✅  SCENARIO %d PASSED                    %s\n", BgGreen, Bold, scenarioNum, Reset)
		fmt.Printf("  %s%s  ══════════════════════════════════════════  %s\n", BgGreen, Bold, Reset)
	}
}

func main() {
	ctx := context.Background()

	fmt.Printf("\n%s%s%s\n", BgBlue, Bold,
		"  ╔══════════════════════════════════════════════════════════════════╗  ")
	fmt.Printf("%s%s%s\n", BgBlue, Bold,
		"  ║     COMPUTE PLATFORM OPERATOR — MVP DEMO                       ║  ")
	fmt.Printf("%s%s%s\n", BgBlue, Bold,
		"  ║     Running 4 scenarios with real workflow engine               ║  ")
	fmt.Printf("%s%s%s\n", BgBlue, Bold,
		"  ╚══════════════════════════════════════════════════════════════════╝  ")

	// ================================================================
	// SCENARIO 1: Node Assignment
	// ================================================================
	runScenario(ctx, 1, Blue, "NODE ASSIGNMENT",
		"Claim gpu-node-01 for team-alpha. Label, wait for agent, record readiness.",
		[]workflow.Step{
			{Name: "validate-spec", Type: workflow.StepValidateSpec, Description: "Ensure CR has owner and node references"},
			{Name: "fetch-target-node", Type: workflow.StepFetchNode, Description: "Fetch gpu-node-01 from Kubernetes API"},
			{Name: "apply-ownership-label", Type: workflow.StepSetLabel, Description: "Set compute-platform.io/owner=team-alpha",
				OnSuccess: "LabelApplied",
				Params:    workflow.StepParams{LabelKey: "compute-platform.io/owner", LabelValueTemplate: "{{ .TenantName }}"}},
			{Name: "await-node-agent", Type: workflow.StepCheckAnnotation, Description: "Wait for on-node agent: node-agent-ready=true",
				WaitIfNotReady: true, OnSuccess: "AwaitingNodeAgent",
				Params: workflow.StepParams{AnnotationKey: "compute-platform.io/node-agent-ready", AnnotationValue: "true"}},
			{Name: "update-readiness", Type: workflow.StepUpdateConfigMap, Description: "Record team-alpha.gpu-node-01=ready in ConfigMap",
				Params: workflow.StepParams{ConfigMapNamespace: "compute-platform-system", ConfigMapName: "node-readiness",
					ConfigMapKeyTemplate: "{{ .TenantName }}.{{ .NodeName }}", ConfigMapValueTemplate: "ready"}},
		},
		&cpv1alpha1.TenantNodeAssignment{
			ObjectMeta: metav1.ObjectMeta{Name: "assign-gpu-01", Namespace: "compute-platform-system"},
			Spec: cpv1alpha1.TenantNodeAssignmentSpec{
				TenantRef:  cpv1alpha1.TenantRef{Name: "team-alpha"},
				NodeRef:    cpv1alpha1.NodeRef{Name: "gpu-node-01"},
				Activation: cpv1alpha1.Activation{Enabled: true},
			},
		},
		&corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-node-01", Labels: map[string]string{"kubernetes.io/hostname": "gpu-node-01"}}},
		map[int]func(context.Context, *workflow.ExecutionContext){
			-4: func(ctx context.Context, ec *workflow.ExecutionContext) {
				if ec.Node != nil {
					if ec.Node.Annotations == nil {
						ec.Node.Annotations = map[string]string{}
					}
					ec.Node.Annotations["compute-platform.io/node-agent-ready"] = "true"
					_ = ec.Client.Update(ctx, ec.Node)
				}
			},
		},
		func(ctx context.Context, ec *workflow.ExecutionContext) {
			if v, ok := ec.Node.Labels["compute-platform.io/owner"]; ok && v == "team-alpha" {
				pass("Node label compute-platform.io/owner=team-alpha")
			} else {
				fail("Node label not set correctly")
			}
			cm := &corev1.ConfigMap{}
			if err := ec.Client.Get(ctx, types.NamespacedName{Namespace: "compute-platform-system", Name: "node-readiness"}, cm); err == nil {
				if v, ok := cm.Data["team-alpha.gpu-node-01"]; ok && v == "ready" {
					pass("ConfigMap node-readiness[team-alpha.gpu-node-01]=ready")
				} else {
					fail("ConfigMap entry incorrect")
				}
			} else {
				fail("ConfigMap not found: " + err.Error())
			}
		},
	)

	// ================================================================
	// SCENARIO 2: Node Decommission
	// ================================================================
	runScenario(ctx, 2, Red, "NODE DECOMMISSION",
		"Decommission gpu-node-02. Label, request drain, wait, record.",
		[]workflow.Step{
			{Name: "validate-spec", Type: workflow.StepValidateSpec, Description: "Ensure CR has valid references"},
			{Name: "fetch-target-node", Type: workflow.StepFetchNode, Description: "Fetch gpu-node-02"},
			{Name: "mark-decommissioning", Type: workflow.StepSetLabel, Description: "Set lifecycle=decommissioning",
				Params: workflow.StepParams{LabelKey: "compute-platform.io/lifecycle", LabelValueTemplate: "decommissioning"}},
			{Name: "request-drain", Type: workflow.StepSetAnnotation, Description: "Signal drain controller: request-drain=true",
				Params: workflow.StepParams{AnnotationKey: "compute-platform.io/request-drain", AnnotationValue: "true"}},
			{Name: "wait-drain", Type: workflow.StepCheckAnnotation, Description: "Wait for drain-complete=true",
				WaitIfNotReady: true,
				Params:         workflow.StepParams{AnnotationKey: "compute-platform.io/drain-complete", AnnotationValue: "true"}},
			{Name: "record-decommission", Type: workflow.StepUpdateConfigMap, Description: "Record in decommissioned-nodes ConfigMap",
				Params: workflow.StepParams{ConfigMapNamespace: "compute-platform-system", ConfigMapName: "decommissioned-nodes",
					ConfigMapKeyTemplate: "{{ .NodeName }}", ConfigMapValueTemplate: "{{ .TenantName }}"}},
		},
		&cpv1alpha1.TenantNodeAssignment{
			ObjectMeta: metav1.ObjectMeta{Name: "decommission-gpu-02", Namespace: "compute-platform-system"},
			Spec: cpv1alpha1.TenantNodeAssignmentSpec{
				TenantRef: cpv1alpha1.TenantRef{Name: "infra"}, NodeRef: cpv1alpha1.NodeRef{Name: "gpu-node-02"},
				Activation: cpv1alpha1.Activation{Enabled: true},
			},
		},
		&corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-node-02", Labels: map[string]string{"kubernetes.io/hostname": "gpu-node-02"}}},
		map[int]func(context.Context, *workflow.ExecutionContext){
			-5: func(ctx context.Context, ec *workflow.ExecutionContext) {
				if ec.Node.Annotations == nil {
					ec.Node.Annotations = map[string]string{}
				}
				ec.Node.Annotations["compute-platform.io/drain-complete"] = "true"
				_ = ec.Client.Update(ctx, ec.Node)
			},
		},
		func(ctx context.Context, ec *workflow.ExecutionContext) {
			if v := ec.Node.Labels["compute-platform.io/lifecycle"]; v == "decommissioning" {
				pass("Node label lifecycle=decommissioning")
			} else {
				fail("Decommission label not set")
			}
			if v := ec.Node.Annotations["compute-platform.io/request-drain"]; v == "true" {
				pass("Drain annotation request-drain=true")
			} else {
				fail("Drain annotation not set")
			}
			cm := &corev1.ConfigMap{}
			if err := ec.Client.Get(ctx, types.NamespacedName{Namespace: "compute-platform-system", Name: "decommissioned-nodes"}, cm); err == nil {
				if v := cm.Data["gpu-node-02"]; v == "infra" {
					pass("ConfigMap decommissioned-nodes[gpu-node-02]=infra")
				} else {
					fail("ConfigMap entry incorrect")
				}
			} else {
				fail("ConfigMap not found")
			}
		},
	)

	// ================================================================
	// SCENARIO 3: Node Health Gate
	// ================================================================
	runScenario(ctx, 3, Cyan, "NODE HEALTH GATE",
		"Block cpu-node-01 until GPU and network checks pass.",
		[]workflow.Step{
			{Name: "validate-spec", Type: workflow.StepValidateSpec, Description: "Ensure CR has valid references"},
			{Name: "fetch-target-node", Type: workflow.StepFetchNode, Description: "Fetch cpu-node-01"},
			{Name: "set-gate-pending", Type: workflow.StepSetLabel, Description: "Set health-gate=pending",
				Params: workflow.StepParams{LabelKey: "compute-platform.io/health-gate", LabelValueTemplate: "pending"}},
			{Name: "wait-gpu-check", Type: workflow.StepCheckAnnotation, Description: "Wait for gpu-check-passed=true",
				WaitIfNotReady: true,
				Params:         workflow.StepParams{AnnotationKey: "compute-platform.io/gpu-check-passed", AnnotationValue: "true"}},
			{Name: "wait-network-check", Type: workflow.StepCheckAnnotation, Description: "Wait for network-check-passed=true",
				WaitIfNotReady: true,
				Params: workflow.StepParams{AnnotationKey: "compute-platform.io/network-check-passed", AnnotationValue: "true"}},
			{Name: "mark-healthy", Type: workflow.StepSetLabel, Description: "Set health-gate=passed",
				Params: workflow.StepParams{LabelKey: "compute-platform.io/health-gate", LabelValueTemplate: "passed"}},
			{Name: "record-healthy", Type: workflow.StepUpdateConfigMap, Description: "Record in healthy-nodes ConfigMap",
				Params: workflow.StepParams{ConfigMapNamespace: "compute-platform-system", ConfigMapName: "healthy-nodes",
					ConfigMapKeyTemplate: "{{ .NodeName }}", ConfigMapValueTemplate: "ready"}},
		},
		&cpv1alpha1.TenantNodeAssignment{
			ObjectMeta: metav1.ObjectMeta{Name: "health-gate-cpu-01", Namespace: "compute-platform-system"},
			Spec: cpv1alpha1.TenantNodeAssignmentSpec{
				TenantRef: cpv1alpha1.TenantRef{Name: "team-gamma"}, NodeRef: cpv1alpha1.NodeRef{Name: "cpu-node-01"},
				Activation: cpv1alpha1.Activation{Enabled: true},
			},
		},
		&corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "cpu-node-01", Labels: map[string]string{"kubernetes.io/hostname": "cpu-node-01"}}},
		map[int]func(context.Context, *workflow.ExecutionContext){
			-4: func(ctx context.Context, ec *workflow.ExecutionContext) {
				if ec.Node.Annotations == nil {
					ec.Node.Annotations = map[string]string{}
				}
				ec.Node.Annotations["compute-platform.io/gpu-check-passed"] = "true"
				_ = ec.Client.Update(ctx, ec.Node)
			},
			-5: func(ctx context.Context, ec *workflow.ExecutionContext) {
				if ec.Node.Annotations == nil {
					ec.Node.Annotations = map[string]string{}
				}
				ec.Node.Annotations["compute-platform.io/network-check-passed"] = "true"
				_ = ec.Client.Update(ctx, ec.Node)
			},
		},
		func(ctx context.Context, ec *workflow.ExecutionContext) {
			if v := ec.Node.Labels["compute-platform.io/health-gate"]; v == "passed" {
				pass("Node label health-gate=passed")
			} else {
				fail("Health gate label not set")
			}
			cm := &corev1.ConfigMap{}
			if err := ec.Client.Get(ctx, types.NamespacedName{Namespace: "compute-platform-system", Name: "healthy-nodes"}, cm); err == nil {
				if v := cm.Data["cpu-node-01"]; v == "ready" {
					pass("ConfigMap healthy-nodes[cpu-node-01]=ready")
				} else {
					fail("ConfigMap entry incorrect")
				}
			} else {
				fail("ConfigMap not found")
			}
		},
	)

	// ================================================================
	// SCENARIO 4: Burn-In Orchestration
	// ================================================================
	runScenario(ctx, 4, Magenta, "BURN-IN ORCHESTRATION",
		"Burn-in gpu-node-03. Isolate, signal harness, wait for results, certify.",
		[]workflow.Step{
			{Name: "validate-spec", Type: workflow.StepValidateSpec, Description: "Ensure CR has valid references"},
			{Name: "fetch-target-node", Type: workflow.StepFetchNode, Description: "Fetch gpu-node-03"},
			{Name: "mark-burn-in", Type: workflow.StepSetLabel, Description: "Set phase=burn-in (isolate from production)",
				Params: workflow.StepParams{LabelKey: "compute-platform.io/phase", LabelValueTemplate: "burn-in"}},
			{Name: "signal-test-start", Type: workflow.StepSetAnnotation, Description: "Signal test harness: burn-in-start=true",
				Params: workflow.StepParams{AnnotationKey: "compute-platform.io/burn-in-start", AnnotationValue: "true"}},
			{Name: "wait-test-result", Type: workflow.StepCheckAnnotation, Description: "Wait for burn-in-result=pass",
				WaitIfNotReady: true,
				Params:         workflow.StepParams{AnnotationKey: "compute-platform.io/burn-in-result", AnnotationValue: "pass"}},
			{Name: "mark-production", Type: workflow.StepSetLabel, Description: "Set phase=production (schedulable)",
				Params: workflow.StepParams{LabelKey: "compute-platform.io/phase", LabelValueTemplate: "production"}},
			{Name: "record-certified", Type: workflow.StepUpdateConfigMap, Description: "Record in certified-nodes ConfigMap",
				Params: workflow.StepParams{ConfigMapNamespace: "compute-platform-system", ConfigMapName: "certified-nodes",
					ConfigMapKeyTemplate: "{{ .TenantName }}.{{ .NodeName }}", ConfigMapValueTemplate: "certified"}},
		},
		&cpv1alpha1.TenantNodeAssignment{
			ObjectMeta: metav1.ObjectMeta{Name: "burnin-gpu-03", Namespace: "compute-platform-system"},
			Spec: cpv1alpha1.TenantNodeAssignmentSpec{
				TenantRef: cpv1alpha1.TenantRef{Name: "team-beta"}, NodeRef: cpv1alpha1.NodeRef{Name: "gpu-node-03"},
				Activation: cpv1alpha1.Activation{Enabled: true},
			},
		},
		&corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-node-03", Labels: map[string]string{"kubernetes.io/hostname": "gpu-node-03"}}},
		map[int]func(context.Context, *workflow.ExecutionContext){
			-5: func(ctx context.Context, ec *workflow.ExecutionContext) {
				if ec.Node.Annotations == nil {
					ec.Node.Annotations = map[string]string{}
				}
				ec.Node.Annotations["compute-platform.io/burn-in-result"] = "pass"
				_ = ec.Client.Update(ctx, ec.Node)
			},
		},
		func(ctx context.Context, ec *workflow.ExecutionContext) {
			if v := ec.Node.Labels["compute-platform.io/phase"]; v == "production" {
				pass("Node label phase=production")
			} else {
				fail("Phase label not correct")
			}
			if v := ec.Node.Annotations["compute-platform.io/burn-in-start"]; v == "true" {
				pass("Test harness signal burn-in-start=true")
			} else {
				fail("Burn-in start annotation not set")
			}
			cm := &corev1.ConfigMap{}
			if err := ec.Client.Get(ctx, types.NamespacedName{Namespace: "compute-platform-system", Name: "certified-nodes"}, cm); err == nil {
				if v := cm.Data["team-beta.gpu-node-03"]; v == "certified" {
					pass("ConfigMap certified-nodes[team-beta.gpu-node-03]=certified")
				} else {
					fail("ConfigMap entry incorrect")
				}
			} else {
				fail("ConfigMap not found")
			}
		},
	)

	// ================================================================
	// FINAL SUMMARY
	// ================================================================
	fmt.Println()
	fmt.Printf("%s%s%s\n", BgGreen, Bold,
		"  ╔══════════════════════════════════════════════════════════════════╗  ")
	fmt.Printf("%s%s%s\n", BgGreen, Bold,
		"  ║    🎉  ALL 4 SCENARIOS PASSED — MVP DEMO COMPLETE              ║  ")
	fmt.Printf("%s%s%s\n", BgGreen, Bold,
		"  ╚══════════════════════════════════════════════════════════════════╝  ")
	fmt.Println()
	fmt.Printf("  %sScenario 1:%s Node Assignment     %s✅  PASS%s\n", Bold, Reset, Green, Reset)
	fmt.Printf("  %sScenario 2:%s Node Decommission   %s✅  PASS%s\n", Bold, Reset, Green, Reset)
	fmt.Printf("  %sScenario 3:%s Node Health Gate    %s✅  PASS%s\n", Bold, Reset, Green, Reset)
	fmt.Printf("  %sScenario 4:%s Burn-In Orchestrate %s✅  PASS%s\n", Bold, Reset, Green, Reset)
	fmt.Println()
	fmt.Printf("  %sEngine:%s Real workflow engine (internal/workflow/engine.go)\n", Dim, Reset)
	fmt.Printf("  %sClient:%s controller-runtime fake client (same as unit tests)\n", Dim, Reset)
	fmt.Printf("  %sSteps:%s  12 step types available, 4 scenarios demonstrated\n", Dim, Reset)
	fmt.Printf("  %sBinary:%s Same binary — different YAML = different behavior\n", Dim, Reset)
	fmt.Println()
}
