package controller

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	cpv1alpha1 "github.com/compute-platform/tenant-node-assignment-operator/api/v1alpha1"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/config"
)

func testScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	_ = clientgoscheme.AddToScheme(s)
	_ = cpv1alpha1.AddToScheme(s)
	return s
}

func newTNA(name, namespace, tenant, node string) *cpv1alpha1.TenantNodeAssignment {
	return &cpv1alpha1.TenantNodeAssignment{
		ObjectMeta: metav1.ObjectMeta{
			Name:       name,
			Namespace:  namespace,
			Generation: 1,
		},
		Spec: cpv1alpha1.TenantNodeAssignmentSpec{
			TenantRef:  cpv1alpha1.TenantRef{Name: tenant},
			NodeRef:    cpv1alpha1.NodeRef{Name: node},
			Activation: cpv1alpha1.Activation{Enabled: true},
		},
	}
}

func newNode(name string) *corev1.Node {
	return &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name:   name,
			Labels: make(map[string]string),
		},
	}
}

// TestReconcile_ResourceNotFound verifies no error when CR doesn't exist.
func TestReconcile_ResourceNotFound(t *testing.T) {
	scheme := testScheme()
	c := fake.NewClientBuilder().WithScheme(scheme).Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	result, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "nonexistent", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Requeue {
		t.Error("should not requeue")
	}
}

// TestReconcile_AddsFinalizer verifies finalizer is added on first reconciliation.
func TestReconcile_AddsFinalizer(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	node := newNode("node-1")
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	result, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Requeue {
		t.Error("should requeue after adding finalizer")
	}

	updated := &cpv1alpha1.TenantNodeAssignment{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "test-tna", Namespace: "default"}, updated)
	hasFinalizer := false
	for _, f := range updated.Finalizers {
		if f == ControllerFinalizer {
			hasFinalizer = true
		}
	}
	if !hasFinalizer {
		t.Error("expected finalizer")
	}
}

// TestReconcile_WorkflowAppliesLabel tests the full workflow applies a label.
func TestReconcile_WorkflowAppliesLabel(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	tna.Finalizers = []string{ControllerFinalizer}
	node := newNode("node-1")
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	updatedNode := &corev1.Node{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "node-1"}, updatedNode)
	if updatedNode.Labels["compute-platform.io/tenant"] != "tenant-a" {
		t.Errorf("expected label, got: %v", updatedNode.Labels)
	}
}

// TestReconcile_NodeNotFound tests workflow fails when node is missing.
func TestReconcile_NodeNotFound(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "missing-node")
	tna.Finalizers = []string{ControllerFinalizer}
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error (should be in status): %v", err)
	}

	updated := &cpv1alpha1.TenantNodeAssignment{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "test-tna", Namespace: "default"}, updated)
	if updated.Status.Phase != cpv1alpha1.PhaseFailed {
		t.Errorf("expected Failed, got %s", updated.Status.Phase)
	}
}

// TestReconcile_EmptyTenantRef tests spec validation catches empty tenant.
func TestReconcile_EmptyTenantRef(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "", "node-1")
	tna.Finalizers = []string{ControllerFinalizer}
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	updated := &cpv1alpha1.TenantNodeAssignment{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "test-tna", Namespace: "default"}, updated)
	if updated.Status.Phase != cpv1alpha1.PhaseFailed {
		t.Errorf("expected Failed for empty tenant, got %s", updated.Status.Phase)
	}
}

// TestReconcile_ActivationDisabled tests no action when not activated.
func TestReconcile_ActivationDisabled(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	tna.Spec.Activation.Enabled = false
	tna.Finalizers = []string{ControllerFinalizer}
	node := newNode("node-1")
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	updatedNode := &corev1.Node{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "node-1"}, updatedNode)
	if _, ok := updatedNode.Labels["compute-platform.io/tenant"]; ok {
		t.Error("should not label when deactivated")
	}
}

// TestReconcile_FullHappyPath tests complete flow: label → completion → readiness → Ready.
func TestReconcile_FullHappyPath(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	tna.Finalizers = []string{ControllerFinalizer}
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name: "node-1",
			Labels: map[string]string{
				"compute-platform.io/tenant": "tenant-a",
			},
			Annotations: map[string]string{
				"compute-platform.io/node-agent-ready": "true",
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	updated := &cpv1alpha1.TenantNodeAssignment{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "test-tna", Namespace: "default"}, updated)
	if updated.Status.Phase != cpv1alpha1.PhaseReady {
		t.Errorf("expected Ready, got %s", updated.Status.Phase)
	}
}

// TestReconcile_AwaitingNodeAgent tests waiting state when completion missing.
func TestReconcile_AwaitingNodeAgent(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	tna.Finalizers = []string{ControllerFinalizer}
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name: "node-1",
			Labels: map[string]string{
				"compute-platform.io/tenant": "tenant-a",
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	result, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.RequeueAfter == 0 {
		t.Error("should requeue when waiting")
	}
}

// TestReconcile_DeletionCleansUp tests cleanup workflow on deletion.
func TestReconcile_DeletionCleansUp(t *testing.T) {
	scheme := testScheme()
	now := metav1.Now()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	tna.Finalizers = []string{ControllerFinalizer}
	tna.DeletionTimestamp = &now
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name:   "node-1",
			Labels: map[string]string{"compute-platform.io/tenant": "tenant-a"},
		},
	}
	readinessCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "tenant-node-readiness", Namespace: "compute-platform-system"},
		Data:       map[string]string{"tenant-a.node-1": "ready"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node, readinessCM).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Label should be removed
	updatedNode := &corev1.Node{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "node-1"}, updatedNode)
	if _, ok := updatedNode.Labels["compute-platform.io/tenant"]; ok {
		t.Error("label should be removed on deletion")
	}

	// Readiness entry should be removed
	updatedCM := &corev1.ConfigMap{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "tenant-node-readiness", Namespace: "compute-platform-system"}, updatedCM)
	if _, ok := updatedCM.Data["tenant-a.node-1"]; ok {
		t.Error("readiness entry should be removed")
	}

	// Finalizer should be removed
	updatedTNA := &cpv1alpha1.TenantNodeAssignment{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "test-tna", Namespace: "default"}, updatedTNA)
	for _, f := range updatedTNA.Finalizers {
		if f == ControllerFinalizer {
			t.Error("finalizer should be removed")
		}
	}
}

// TestReconcile_DeletionNodeGone tests cleanup succeeds when node is gone.
func TestReconcile_DeletionNodeGone(t *testing.T) {
	scheme := testScheme()
	now := metav1.Now()
	tna := newTNA("test-tna", "default", "tenant-a", "gone-node")
	tna.Finalizers = []string{ControllerFinalizer}
	tna.DeletionTimestamp = &now
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("cleanup should succeed when node is gone: %v", err)
	}
}

// TestReconcile_LabelDriftCorrection tests label is corrected when drifted.
func TestReconcile_LabelDriftCorrection(t *testing.T) {
	scheme := testScheme()
	tna := newTNA("test-tna", "default", "tenant-a", "node-1")
	tna.Finalizers = []string{ControllerFinalizer}
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name:   "node-1",
			Labels: map[string]string{"compute-platform.io/tenant": "wrong-tenant"},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).
		WithObjects(tna, node).
		WithStatusSubresource(tna).
		Build()
	r := &TenantNodeAssignmentReconciler{Client: c, Config: config.DefaultConfig()}

	_, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "test-tna", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	updatedNode := &corev1.Node{}
	_ = c.Get(context.Background(), types.NamespacedName{Name: "node-1"}, updatedNode)
	if updatedNode.Labels["compute-platform.io/tenant"] != "tenant-a" {
		t.Errorf("expected corrected label, got: %v", updatedNode.Labels)
	}
}

// TestSetCondition tests condition add and update logic.
func TestSetCondition(t *testing.T) {
	tna := newTNA("test", "default", "t", "n")

	setCondition(tna, "Test", metav1.ConditionTrue, "Reason1", "msg1")
	if len(tna.Status.Conditions) != 1 {
		t.Fatalf("expected 1 condition, got %d", len(tna.Status.Conditions))
	}

	// Same status, update reason
	setCondition(tna, "Test", metav1.ConditionTrue, "Reason2", "msg2")
	if len(tna.Status.Conditions) != 1 || tna.Status.Conditions[0].Reason != "Reason2" {
		t.Error("should update in place")
	}

	// Different status replaces
	setCondition(tna, "Test", metav1.ConditionFalse, "Reason3", "msg3")
	if tna.Status.Conditions[0].Status != metav1.ConditionFalse {
		t.Error("should change status")
	}
}
