package workflow

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	cpv1alpha1 "github.com/compute-platform/tenant-node-assignment-operator/api/v1alpha1"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/labels"
)

func testScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	_ = clientgoscheme.AddToScheme(s)
	_ = cpv1alpha1.AddToScheme(s)
	return s
}

func newTestTNA(tenant, node string) *cpv1alpha1.TenantNodeAssignment {
	return &cpv1alpha1.TenantNodeAssignment{
		ObjectMeta: metav1.ObjectMeta{Name: "test-tna", Namespace: "default", Generation: 1},
		Spec: cpv1alpha1.TenantNodeAssignmentSpec{
			TenantRef:  cpv1alpha1.TenantRef{Name: tenant},
			NodeRef:    cpv1alpha1.NodeRef{Name: node},
			Activation: cpv1alpha1.Activation{Enabled: true},
		},
	}
}

func newTestEC(tna *cpv1alpha1.TenantNodeAssignment) *ExecutionContext {
	return &ExecutionContext{
		TNA:      tna,
		TmplData: labels.TemplateData{TenantName: tna.Spec.TenantRef.Name, NodeName: tna.Spec.NodeRef.Name},
	}
}

// --- validateSpec tests ---

func TestStep_ValidateSpec_Valid(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	result := ex.ExecuteStep(context.Background(), Step{Type: StepValidateSpec}, ec)
	if !result.Completed {
		t.Errorf("expected completed, got: %+v", result)
	}
}

func TestStep_ValidateSpec_EmptyTenant(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("", "node-1"))
	result := ex.ExecuteStep(context.Background(), Step{Type: StepValidateSpec}, ec)
	if !result.Failed {
		t.Error("expected failure for empty tenant")
	}
}

func TestStep_ValidateSpec_EmptyNode(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", ""))
	result := ex.ExecuteStep(context.Background(), Step{Type: StepValidateSpec}, ec)
	if !result.Failed {
		t.Error("expected failure for empty node")
	}
}

// --- fetchNode tests ---

func TestStep_FetchNode_Exists(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1"}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	result := ex.ExecuteStep(context.Background(), Step{Type: StepFetchNode}, ec)
	if !result.Completed {
		t.Errorf("expected completed: %s", result.Message)
	}
	if ec.Node == nil {
		t.Error("node should be populated")
	}
}

func TestStep_FetchNode_NotFound(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "missing-node"))
	result := ex.ExecuteStep(context.Background(), Step{Type: StepFetchNode}, ec)
	if !result.Failed {
		t.Error("expected failure for missing node")
	}
}

// --- setLabel tests ---

func TestStep_SetLabel_Success(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Labels: map[string]string{}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	ec.Node = node

	step := Step{
		Type: StepSetLabel,
		Params: StepParams{
			LabelKey:           "compute-platform.io/tenant",
			LabelValueTemplate: "{{ .TenantName }}",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed || !result.Modified {
		t.Errorf("expected completed+modified: %+v", result)
	}

	updated := &corev1.Node{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "node-1"}, updated)
	if updated.Labels["compute-platform.io/tenant"] != "tenant-a" {
		t.Errorf("label not set correctly: %v", updated.Labels)
	}
}

func TestStep_SetLabel_AlreadyCorrect(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Labels: map[string]string{"compute-platform.io/tenant": "tenant-a"}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	ec.Node = node

	step := Step{
		Type:   StepSetLabel,
		Params: StepParams{LabelKey: "compute-platform.io/tenant", LabelValueTemplate: "{{ .TenantName }}"},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed || result.Modified {
		t.Error("should be completed but NOT modified (no-op)")
	}
}

func TestStep_SetLabel_NodeNil(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	result := ex.ExecuteStep(context.Background(), Step{Type: StepSetLabel, Params: StepParams{LabelKey: "k", LabelValueTemplate: "v"}}, ec)
	if !result.Failed {
		t.Error("should fail when node is nil")
	}
}

// --- checkAnnotation tests ---

func TestStep_CheckAnnotation_Present(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Annotations: map[string]string{"ready": "true"}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	step := Step{Type: StepCheckAnnotation, Params: StepParams{AnnotationKey: "ready", AnnotationValue: "true"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed {
		t.Error("should complete when annotation present")
	}
}

func TestStep_CheckAnnotation_Missing_Wait(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1"}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	step := Step{Type: StepCheckAnnotation, WaitIfNotReady: true, Params: StepParams{AnnotationKey: "ready", AnnotationValue: "true"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Waiting {
		t.Error("should be waiting when annotation missing and waitIfNotReady=true")
	}
}

func TestStep_CheckAnnotation_Missing_Fail(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1"}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	step := Step{Type: StepCheckAnnotation, Params: StepParams{AnnotationKey: "ready", AnnotationValue: "true"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Failed {
		t.Error("should fail when annotation missing and waitIfNotReady=false")
	}
}

// --- updateConfigMap tests ---

func TestStep_UpdateConfigMap_Create(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))

	step := Step{
		Type: StepUpdateConfigMap,
		Params: StepParams{
			ConfigMapNamespace:     "default",
			ConfigMapName:          "readiness",
			ConfigMapKeyTemplate:   "{{ .TenantName }}.{{ .NodeName }}",
			ConfigMapValueTemplate: "ready",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed || !result.Modified {
		t.Errorf("expected completed+modified: %+v", result)
	}

	cm := &corev1.ConfigMap{}
	_ = c.Get(context.Background(), types.NamespacedName{Namespace: "default", Name: "readiness"}, cm)
	if cm.Data["tenant-a.node-1"] != "ready" {
		t.Errorf("configmap entry wrong: %v", cm.Data)
	}
}

func TestStep_UpdateConfigMap_Update(t *testing.T) {
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "readiness", Namespace: "default"},
		Data:       map[string]string{"other": "val"},
	}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(existingCM).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))

	step := Step{
		Type: StepUpdateConfigMap,
		Params: StepParams{
			ConfigMapNamespace:     "default",
			ConfigMapName:          "readiness",
			ConfigMapKeyTemplate:   "{{ .TenantName }}.{{ .NodeName }}",
			ConfigMapValueTemplate: "ready",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed {
		t.Errorf("expected completed: %s", result.Message)
	}
}

// --- removeLabel tests ---

func TestStep_RemoveLabel_Exists(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Labels: map[string]string{"key": "val"}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	result := ex.ExecuteStep(context.Background(), Step{Type: StepRemoveLabel, Params: StepParams{LabelKey: "key"}}, ec)
	if !result.Completed || !result.Modified {
		t.Error("expected completed+modified")
	}
}

func TestStep_RemoveLabel_Absent(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Labels: map[string]string{}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	result := ex.ExecuteStep(context.Background(), Step{Type: StepRemoveLabel, Params: StepParams{LabelKey: "missing"}}, ec)
	if !result.Completed || result.Modified {
		t.Error("should complete without modification for absent label")
	}
}

// --- removeConfigMapEntry tests ---

func TestStep_RemoveConfigMapEntry_Exists(t *testing.T) {
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "readiness", Namespace: "default"},
		Data:       map[string]string{"tenant-a.node-1": "ready"},
	}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(cm).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))

	step := Step{
		Type: StepRemoveConfigMapEntry,
		Params: StepParams{
			ConfigMapNamespace:   "default",
			ConfigMapName:        "readiness",
			ConfigMapKeyTemplate: "{{ .TenantName }}.{{ .NodeName }}",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed || !result.Modified {
		t.Error("expected completed+modified")
	}
}

func TestStep_RemoveConfigMapEntry_NotFound(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))

	step := Step{
		Type: StepRemoveConfigMapEntry,
		Params: StepParams{
			ConfigMapNamespace:   "default",
			ConfigMapName:        "missing",
			ConfigMapKeyTemplate: "{{ .TenantName }}.{{ .NodeName }}",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed {
		t.Error("should complete when configmap not found")
	}
}

// --- setPhase tests ---

func TestStep_SetPhase(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	tna := newTestTNA("t", "n")
	ec := newTestEC(tna)

	step := Step{Type: StepSetPhase, Params: StepParams{Phase: "Ready"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed {
		t.Error("expected completed")
	}
	if ec.TNA.Status.Phase != "Ready" {
		t.Errorf("expected phase Ready, got %s", ec.TNA.Status.Phase)
	}
}

// --- unknown step type ---

func TestStep_UnknownType(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "n"))

	result := ex.ExecuteStep(context.Background(), Step{Type: "unknownStep"}, ec)
	if !result.Failed {
		t.Error("expected failure for unknown step type")
	}
}

// --- setAnnotation tests ---

func TestStep_SetAnnotation_Success(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1"}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	step := Step{Type: StepSetAnnotation, Params: StepParams{AnnotationKey: "test/key", AnnotationValue: "true"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed || !result.Modified {
		t.Error("expected completed+modified")
	}

	updated := &corev1.Node{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "node-1"}, updated)
	if updated.Annotations["test/key"] != "true" {
		t.Error("annotation not set")
	}
}

func TestStep_SetAnnotation_AlreadyCorrect(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Annotations: map[string]string{"test/key": "true"}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	step := Step{Type: StepSetAnnotation, Params: StepParams{AnnotationKey: "test/key", AnnotationValue: "true"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed || result.Modified {
		t.Error("should complete without modification")
	}
}

// --- removeAnnotation tests ---

func TestStep_RemoveAnnotation_Exists(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Annotations: map[string]string{"key": "val"}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	result := ex.ExecuteStep(context.Background(), Step{Type: StepRemoveAnnotation, Params: StepParams{AnnotationKey: "key"}}, ec)
	if !result.Completed || !result.Modified {
		t.Error("expected completed+modified")
	}
}

func TestStep_RemoveAnnotation_Absent(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1"}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(node).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("t", "node-1"))
	ec.Node = node

	result := ex.ExecuteStep(context.Background(), Step{Type: StepRemoveAnnotation, Params: StepParams{AnnotationKey: "missing"}}, ec)
	if !result.Completed || result.Modified {
		t.Error("should complete without modification")
	}
}

// --- checkLabel tests ---

func TestStep_CheckLabel_Found(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Labels: map[string]string{"key": "tenant-a"}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	ec.Node = node

	step := Step{Type: StepCheckLabel, Params: StepParams{LabelKey: "key", LabelValueTemplate: "{{ .TenantName }}"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed {
		t.Error("should complete when label found")
	}
}

func TestStep_CheckLabel_NotFound_Wait(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1", Labels: map[string]string{}}}
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))
	ec.Node = node

	step := Step{Type: StepCheckLabel, WaitIfNotReady: true, Params: StepParams{LabelKey: "key", LabelValueTemplate: "{{ .TenantName }}"}}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Waiting {
		t.Error("should be waiting")
	}
}

// --- checkConfigMap tests ---

func TestStep_CheckConfigMap_Found(t *testing.T) {
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "cm", Namespace: "ns"},
		Data:       map[string]string{"tenant-a.node-1": "ready"},
	}
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(cm).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))

	step := Step{
		Type: StepCheckConfigMap,
		Params: StepParams{
			ConfigMapNamespace:     "ns",
			ConfigMapName:          "cm",
			ConfigMapKeyTemplate:   "{{ .TenantName }}.{{ .NodeName }}",
			ConfigMapValueTemplate: "ready",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Completed {
		t.Error("should complete when entry found")
	}
}

func TestStep_CheckConfigMap_NotFound_Wait(t *testing.T) {
	c := fake.NewClientBuilder().WithScheme(testScheme()).Build()
	ex := NewExecutor(c)
	ec := newTestEC(newTestTNA("tenant-a", "node-1"))

	step := Step{
		Type:           StepCheckConfigMap,
		WaitIfNotReady: true,
		Params: StepParams{
			ConfigMapNamespace:     "ns",
			ConfigMapName:          "missing",
			ConfigMapKeyTemplate:   "{{ .TenantName }}.{{ .NodeName }}",
			ConfigMapValueTemplate: "ready",
		},
	}
	result := ex.ExecuteStep(context.Background(), step, ec)
	if !result.Waiting {
		t.Error("should be waiting when configmap not found")
	}
}
