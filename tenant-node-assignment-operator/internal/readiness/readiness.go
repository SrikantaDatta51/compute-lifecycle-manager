// Package readiness provides logic for updating the readiness ConfigMap.
package readiness

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// Manager handles readiness ConfigMap operations.
type Manager struct {
	client    client.Client
	namespace string
	name      string
}

// NewManager creates a new readiness ConfigMap manager.
func NewManager(c client.Client, namespace, name string) *Manager {
	return &Manager{
		client:    c,
		namespace: namespace,
		name:      name,
	}
}

// SetEntry sets a key-value pair in the readiness ConfigMap.
// Creates the ConfigMap if it does not exist.
func (m *Manager) SetEntry(ctx context.Context, key, value string) error {
	cm := &corev1.ConfigMap{}
	err := m.client.Get(ctx, types.NamespacedName{
		Namespace: m.namespace,
		Name:      m.name,
	}, cm)

	if errors.IsNotFound(err) {
		// Create the ConfigMap
		cm = &corev1.ConfigMap{
			ObjectMeta: metav1.ObjectMeta{
				Name:      m.name,
				Namespace: m.namespace,
				Labels: map[string]string{
					"app.kubernetes.io/name":       "tenant-node-readiness",
					"app.kubernetes.io/managed-by": "tenant-node-assignment-operator",
				},
			},
			Data: map[string]string{
				key: value,
			},
		}
		if err := m.client.Create(ctx, cm); err != nil {
			return fmt.Errorf("failed to create readiness ConfigMap %s/%s: %w", m.namespace, m.name, err)
		}
		return nil
	}
	if err != nil {
		return fmt.Errorf("failed to get readiness ConfigMap %s/%s: %w", m.namespace, m.name, err)
	}

	// Update existing ConfigMap
	if cm.Data == nil {
		cm.Data = make(map[string]string)
	}

	// Check if entry already exists with correct value (no-op)
	if existing, ok := cm.Data[key]; ok && existing == value {
		return nil
	}

	cm.Data[key] = value
	if err := m.client.Update(ctx, cm); err != nil {
		return fmt.Errorf("failed to update readiness ConfigMap %s/%s: %w", m.namespace, m.name, err)
	}
	return nil
}

// RemoveEntry removes a key from the readiness ConfigMap.
func (m *Manager) RemoveEntry(ctx context.Context, key string) error {
	cm := &corev1.ConfigMap{}
	err := m.client.Get(ctx, types.NamespacedName{
		Namespace: m.namespace,
		Name:      m.name,
	}, cm)

	if errors.IsNotFound(err) {
		// ConfigMap doesn't exist, nothing to remove
		return nil
	}
	if err != nil {
		return fmt.Errorf("failed to get readiness ConfigMap %s/%s: %w", m.namespace, m.name, err)
	}

	if cm.Data == nil {
		return nil
	}

	if _, ok := cm.Data[key]; !ok {
		// Key doesn't exist, no-op
		return nil
	}

	delete(cm.Data, key)
	if err := m.client.Update(ctx, cm); err != nil {
		return fmt.Errorf("failed to update readiness ConfigMap %s/%s: %w", m.namespace, m.name, err)
	}
	return nil
}

// HasEntry checks if a key exists in the readiness ConfigMap with the expected value.
func (m *Manager) HasEntry(ctx context.Context, key, expectedValue string) (bool, error) {
	cm := &corev1.ConfigMap{}
	err := m.client.Get(ctx, types.NamespacedName{
		Namespace: m.namespace,
		Name:      m.name,
	}, cm)

	if errors.IsNotFound(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("failed to get readiness ConfigMap %s/%s: %w", m.namespace, m.name, err)
	}

	if cm.Data == nil {
		return false, nil
	}

	val, ok := cm.Data[key]
	return ok && val == expectedValue, nil
}
