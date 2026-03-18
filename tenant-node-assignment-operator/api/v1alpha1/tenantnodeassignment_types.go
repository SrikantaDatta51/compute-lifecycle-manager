package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// TenantNodeAssignmentPhase represents the current phase of a TenantNodeAssignment.
type TenantNodeAssignmentPhase string

const (
	// PhasePending indicates the CR has been created but no action taken yet.
	PhasePending TenantNodeAssignmentPhase = "Pending"
	// PhaseLabelApplied indicates the node label has been set successfully.
	PhaseLabelApplied TenantNodeAssignmentPhase = "LabelApplied"
	// PhaseAwaitingNodeAgent indicates the operator is waiting for node-agent completion.
	PhaseAwaitingNodeAgent TenantNodeAssignmentPhase = "AwaitingNodeAgent"
	// PhaseReady indicates the assignment is complete and readiness ConfigMap updated.
	PhaseReady TenantNodeAssignmentPhase = "Ready"
	// PhaseFailed indicates a permanent or retriable failure.
	PhaseFailed TenantNodeAssignmentPhase = "Failed"
)

// TenantRef identifies the logical tenant.
type TenantRef struct {
	// Name is the logical tenant identifier.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Name string `json:"name"`
}

// NodeRef identifies the target Kubernetes node.
type NodeRef struct {
	// Name is the Kubernetes node name.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Name string `json:"name"`
}

// Activation controls whether this assignment is active.
type Activation struct {
	// Enabled controls whether this assignment should be processed.
	// Set to false for pause or dry-run modes.
	// +kubebuilder:default=true
	Enabled bool `json:"enabled"`
}

// TenantNodeAssignmentSpec defines the desired state of TenantNodeAssignment.
type TenantNodeAssignmentSpec struct {
	// TenantRef identifies which tenant should own this node.
	// +kubebuilder:validation:Required
	TenantRef TenantRef `json:"tenantRef"`

	// NodeRef identifies the target Kubernetes node.
	// +kubebuilder:validation:Required
	NodeRef NodeRef `json:"nodeRef"`

	// Activation controls whether this assignment is active.
	// +optional
	Activation Activation `json:"activation,omitempty"`
}

// AssignedLabel records the actual label applied to the node.
type AssignedLabel struct {
	// Key is the label key applied to the node.
	Key string `json:"key,omitempty"`
	// Value is the label value applied to the node.
	Value string `json:"value,omitempty"`
}

// CompletionStatus tracks node-agent completion state.
type CompletionStatus struct {
	// Acknowledged indicates the node-agent completion signal has been observed.
	Acknowledged bool `json:"acknowledged"`
}

// ReadinessStatus tracks readiness ConfigMap update state.
type ReadinessStatus struct {
	// ConfigMapUpdated indicates the readiness ConfigMap has been updated.
	ConfigMapUpdated bool `json:"configMapUpdated"`
}

// TenantNodeAssignmentStatus defines the observed state of TenantNodeAssignment.
type TenantNodeAssignmentStatus struct {
	// Phase represents the current lifecycle phase.
	// +kubebuilder:validation:Enum=Pending;LabelApplied;AwaitingNodeAgent;Ready;Failed
	Phase TenantNodeAssignmentPhase `json:"phase,omitempty"`

	// ObservedGeneration is the most recent generation observed.
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// Conditions represent the latest available observations of the resource's state.
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// AssignedLabel records the label key/value applied to the node.
	// +optional
	AssignedLabel AssignedLabel `json:"assignedLabel,omitempty"`

	// Completion tracks node-agent completion signal state.
	// +optional
	Completion CompletionStatus `json:"completion,omitempty"`

	// Readiness tracks readiness ConfigMap update state.
	// +optional
	Readiness ReadinessStatus `json:"readiness,omitempty"`

	// LastTransitionTime records when the phase last changed.
	// +optional
	LastTransitionTime *metav1.Time `json:"lastTransitionTime,omitempty"`

	// Message provides a human-readable message about the current state.
	// +optional
	Message string `json:"message,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=tna
// +kubebuilder:printcolumn:name="Tenant",type=string,JSONPath=`.spec.tenantRef.name`
// +kubebuilder:printcolumn:name="Node",type=string,JSONPath=`.spec.nodeRef.name`
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// TenantNodeAssignment is the Schema for the tenantnodeassignments API.
// It represents a tenant's intent to be assigned a specific Kubernetes node.
type TenantNodeAssignment struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   TenantNodeAssignmentSpec   `json:"spec,omitempty"`
	Status TenantNodeAssignmentStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// TenantNodeAssignmentList contains a list of TenantNodeAssignment.
type TenantNodeAssignmentList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []TenantNodeAssignment `json:"items"`
}

func init() {
	SchemeBuilder.Register(&TenantNodeAssignment{}, &TenantNodeAssignmentList{})
}
