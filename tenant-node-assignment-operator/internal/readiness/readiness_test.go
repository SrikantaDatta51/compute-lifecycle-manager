package readiness

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

func newScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	_ = clientgoscheme.AddToScheme(s)
	return s
}

func TestSetEntry_CreateNewConfigMap(t *testing.T) {
	scheme := newScheme()
	c := fake.NewClientBuilder().WithScheme(scheme).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.SetEntry(ctx, "tenant-a.node-1", "ready")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify ConfigMap was created
	cm := &corev1.ConfigMap{}
	err = c.Get(ctx, types.NamespacedName{Namespace: "test-ns", Name: "test-readiness"}, cm)
	if err != nil {
		t.Fatalf("expected ConfigMap to exist: %v", err)
	}
	if cm.Data["tenant-a.node-1"] != "ready" {
		t.Errorf("expected 'ready', got '%s'", cm.Data["tenant-a.node-1"])
	}
}

func TestSetEntry_UpdateExistingConfigMap(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
		Data:       map[string]string{"existing-key": "existing-value"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.SetEntry(ctx, "tenant-b.node-2", "ready")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	cm := &corev1.ConfigMap{}
	_ = c.Get(ctx, types.NamespacedName{Namespace: "test-ns", Name: "test-readiness"}, cm)
	if cm.Data["tenant-b.node-2"] != "ready" {
		t.Errorf("expected 'ready', got '%s'", cm.Data["tenant-b.node-2"])
	}
	if cm.Data["existing-key"] != "existing-value" {
		t.Error("existing data should be preserved")
	}
}

func TestSetEntry_NoOpIfAlreadyCorrect(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
		Data:       map[string]string{"tenant-a.node-1": "ready"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.SetEntry(ctx, "tenant-a.node-1", "ready")
	if err != nil {
		t.Fatalf("unexpected error for no-op: %v", err)
	}
}

func TestRemoveEntry_ExistingKey(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
		Data:       map[string]string{"tenant-a.node-1": "ready", "tenant-b.node-2": "ready"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.RemoveEntry(ctx, "tenant-a.node-1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	cm := &corev1.ConfigMap{}
	_ = c.Get(ctx, types.NamespacedName{Namespace: "test-ns", Name: "test-readiness"}, cm)
	if _, ok := cm.Data["tenant-a.node-1"]; ok {
		t.Error("expected key to be removed")
	}
	if cm.Data["tenant-b.node-2"] != "ready" {
		t.Error("other keys should be preserved")
	}
}

func TestRemoveEntry_ConfigMapNotFound(t *testing.T) {
	scheme := newScheme()
	c := fake.NewClientBuilder().WithScheme(scheme).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.RemoveEntry(ctx, "nonexistent")
	if err != nil {
		t.Fatalf("should not error when ConfigMap doesn't exist: %v", err)
	}
}

func TestRemoveEntry_KeyNotFound(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
		Data:       map[string]string{"other-key": "value"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.RemoveEntry(ctx, "nonexistent-key")
	if err != nil {
		t.Fatalf("should not error when key doesn't exist: %v", err)
	}
}

func TestHasEntry_Exists(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
		Data:       map[string]string{"tenant-a.node-1": "ready"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	has, err := mgr.HasEntry(ctx, "tenant-a.node-1", "ready")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !has {
		t.Error("expected entry to exist")
	}
}

func TestHasEntry_WrongValue(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
		Data:       map[string]string{"tenant-a.node-1": "not-ready"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	has, err := mgr.HasEntry(ctx, "tenant-a.node-1", "ready")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if has {
		t.Error("expected entry to not match")
	}
}

func TestHasEntry_ConfigMapNotFound(t *testing.T) {
	scheme := newScheme()
	c := fake.NewClientBuilder().WithScheme(scheme).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	has, err := mgr.HasEntry(ctx, "key", "value")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if has {
		t.Error("expected false when ConfigMap doesn't exist")
	}
}

func TestSetEntry_NilData(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.SetEntry(ctx, "key", "value")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	cm := &corev1.ConfigMap{}
	_ = c.Get(ctx, types.NamespacedName{Namespace: "test-ns", Name: "test-readiness"}, cm)
	if cm.Data["key"] != "value" {
		t.Errorf("expected 'value', got '%s'", cm.Data["key"])
	}
}

func TestRemoveEntry_NilData(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	err := mgr.RemoveEntry(ctx, "key")
	if err != nil {
		t.Fatalf("should not error on nil data: %v", err)
	}
}

func TestHasEntry_NilData(t *testing.T) {
	scheme := newScheme()
	existingCM := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "test-readiness", Namespace: "test-ns"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(existingCM).Build()
	mgr := NewManager(c, "test-ns", "test-readiness")

	ctx := context.Background()
	has, err := mgr.HasEntry(ctx, "key", "value")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if has {
		t.Error("expected false on nil data")
	}
}
