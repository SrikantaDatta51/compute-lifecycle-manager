// Package workflow provides a generic, YAML-configurable workflow engine
// for the tenant-node-assignment operator. Workflows are defined as ordered
// lists of steps in a ConfigMap, making the controller behavior fully
// externalized and extensible without code changes.
package workflow

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cpv1alpha1 "github.com/compute-platform/tenant-node-assignment-operator/api/v1alpha1"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/labels"
)

// StepType defines the type of workflow step.
type StepType string

const (
	// StepValidateSpec validates CR spec fields.
	StepValidateSpec StepType = "validateSpec"
	// StepFetchNode fetches the target node from the cluster.
	StepFetchNode StepType = "fetchNode"
	// StepSetLabel sets a label on the target node.
	StepSetLabel StepType = "setLabel"
	// StepCheckAnnotation checks for an annotation on the target node.
	StepCheckAnnotation StepType = "checkAnnotation"
	// StepCheckLabel checks for a label value on the target node.
	StepCheckLabel StepType = "checkLabel"
	// StepUpdateConfigMap updates a ConfigMap entry.
	StepUpdateConfigMap StepType = "updateConfigMap"
	// StepRemoveLabel removes a label from the target node.
	StepRemoveLabel StepType = "removeLabel"
	// StepRemoveAnnotation removes an annotation from the target node.
	StepRemoveAnnotation StepType = "removeAnnotation"
	// StepRemoveConfigMapEntry removes a ConfigMap entry.
	StepRemoveConfigMapEntry StepType = "removeConfigMapEntry"
	// StepSetAnnotation sets an annotation on the target node.
	StepSetAnnotation StepType = "setAnnotation"
	// StepSetPhase sets the CR phase.
	StepSetPhase StepType = "setPhase"
	// StepCheckConfigMap checks if a ConfigMap entry exists with expected value.
	StepCheckConfigMap StepType = "checkConfigMap"
)

// Step represents a single workflow step defined in YAML.
type Step struct {
	// Name is a human-readable name for this step.
	Name string `yaml:"name" json:"name"`
	// Type is the step type.
	Type StepType `yaml:"type" json:"type"`
	// Description is optional documentation for this step.
	Description string `yaml:"description,omitempty" json:"description,omitempty"`
	// Params contains step-type-specific parameters.
	Params StepParams `yaml:"params,omitempty" json:"params,omitempty"`
	// OnSuccess defines the phase to set on success (optional).
	OnSuccess string `yaml:"onSuccess,omitempty" json:"onSuccess,omitempty"`
	// OnFailure defines the phase to set on failure (optional, defaults to "Failed").
	OnFailure string `yaml:"onFailure,omitempty" json:"onFailure,omitempty"`
	// ContinueOnFailure if true, do not halt the workflow on failure (optional).
	ContinueOnFailure bool `yaml:"continueOnFailure,omitempty" json:"continueOnFailure,omitempty"`
	// WaitIfNotReady if true, requeue instead of failing when a check step is not satisfied.
	WaitIfNotReady bool `yaml:"waitIfNotReady,omitempty" json:"waitIfNotReady,omitempty"`
}

// StepParams holds type-specific parameters for workflow steps.
type StepParams struct {
	// Label key/value for setLabel, checkLabel, removeLabel steps.
	LabelKey           string `yaml:"labelKey,omitempty" json:"labelKey,omitempty"`
	LabelValueTemplate string `yaml:"labelValueTemplate,omitempty" json:"labelValueTemplate,omitempty"`

	// Annotation key/value for setAnnotation, checkAnnotation, removeAnnotation steps.
	AnnotationKey   string `yaml:"annotationKey,omitempty" json:"annotationKey,omitempty"`
	AnnotationValue string `yaml:"annotationValue,omitempty" json:"annotationValue,omitempty"`

	// ConfigMap parameters for updateConfigMap, removeConfigMapEntry, checkConfigMap.
	ConfigMapNamespace      string `yaml:"configMapNamespace,omitempty" json:"configMapNamespace,omitempty"`
	ConfigMapName           string `yaml:"configMapName,omitempty" json:"configMapName,omitempty"`
	ConfigMapKeyTemplate    string `yaml:"configMapKeyTemplate,omitempty" json:"configMapKeyTemplate,omitempty"`
	ConfigMapValueTemplate  string `yaml:"configMapValueTemplate,omitempty" json:"configMapValueTemplate,omitempty"`

	// Phase to set for setPhase step.
	Phase string `yaml:"phase,omitempty" json:"phase,omitempty"`

	// Required fields for validateSpec (comma-separated: "tenantRef,nodeRef").
	RequiredFields string `yaml:"requiredFields,omitempty" json:"requiredFields,omitempty"`
}

// WorkflowDefinition defines a complete workflow as an ordered list of steps.
type WorkflowDefinition struct {
	// Name is the workflow name (e.g., "tenant-node-assignment").
	Name string `yaml:"name" json:"name"`
	// Description documents what this workflow does.
	Description string `yaml:"description,omitempty" json:"description,omitempty"`
	// Steps is the ordered list of reconciliation steps.
	Steps []Step `yaml:"steps" json:"steps"`
	// CleanupSteps is the ordered list of steps to run on CR deletion.
	CleanupSteps []Step `yaml:"cleanupSteps,omitempty" json:"cleanupSteps,omitempty"`
}

// StepResult captures the outcome of executing a workflow step.
type StepResult struct {
	// Completed indicates the step executed successfully.
	Completed bool
	// Waiting indicates the step is waiting for an external condition.
	Waiting bool
	// Failed indicates the step encountered an error.
	Failed bool
	// Message is a human-readable description of the result.
	Message string
	// Modified indicates the step made a change (useful for status updates).
	Modified bool
}

// ExecutionContext holds the runtime context for workflow execution.
type ExecutionContext struct {
	Client    client.Client
	TNA       *cpv1alpha1.TenantNodeAssignment
	Node      *corev1.Node // lazily populated by fetchNode step
	TmplData  labels.TemplateData
	NodeFound bool
}

// Executor runs workflow steps against the Kubernetes API.
type Executor struct {
	client client.Client
}

// NewExecutor creates a new workflow executor.
func NewExecutor(c client.Client) *Executor {
	return &Executor{client: c}
}

// ExecuteStep runs a single workflow step.
func (e *Executor) ExecuteStep(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	logger := log.FromContext(ctx)
	logger.V(1).Info("Executing workflow step", "step", step.Name, "type", step.Type)

	switch step.Type {
	case StepValidateSpec:
		return e.executeValidateSpec(ctx, step, ec)
	case StepFetchNode:
		return e.executeFetchNode(ctx, step, ec)
	case StepSetLabel:
		return e.executeSetLabel(ctx, step, ec)
	case StepCheckAnnotation:
		return e.executeCheckAnnotation(ctx, step, ec)
	case StepCheckLabel:
		return e.executeCheckLabel(ctx, step, ec)
	case StepUpdateConfigMap:
		return e.executeUpdateConfigMap(ctx, step, ec)
	case StepRemoveLabel:
		return e.executeRemoveLabel(ctx, step, ec)
	case StepRemoveAnnotation:
		return e.executeRemoveAnnotation(ctx, step, ec)
	case StepRemoveConfigMapEntry:
		return e.executeRemoveConfigMapEntry(ctx, step, ec)
	case StepSetAnnotation:
		return e.executeSetAnnotation(ctx, step, ec)
	case StepSetPhase:
		return e.executeSetPhase(ctx, step, ec)
	case StepCheckConfigMap:
		return e.executeCheckConfigMap(ctx, step, ec)
	default:
		return StepResult{Failed: true, Message: fmt.Sprintf("unknown step type: %s", step.Type)}
	}
}

func (e *Executor) executeValidateSpec(_ context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.TNA.Spec.TenantRef.Name == "" {
		return StepResult{Failed: true, Message: "spec.tenantRef.name is required"}
	}
	if ec.TNA.Spec.NodeRef.Name == "" {
		return StepResult{Failed: true, Message: "spec.nodeRef.name is required"}
	}
	return StepResult{Completed: true, Message: "spec validation passed"}
}

func (e *Executor) executeFetchNode(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	node := &corev1.Node{}
	err := e.client.Get(ctx, types.NamespacedName{Name: ec.TNA.Spec.NodeRef.Name}, node)
	if err != nil {
		if errors.IsNotFound(err) {
			return StepResult{Failed: true, Message: fmt.Sprintf("node %q not found", ec.TNA.Spec.NodeRef.Name)}
		}
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to fetch node: %v", err)}
	}
	ec.Node = node
	ec.NodeFound = true
	return StepResult{Completed: true, Message: fmt.Sprintf("fetched node %q", node.Name)}
}

func (e *Executor) executeSetLabel(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.Node == nil {
		return StepResult{Failed: true, Message: "node not fetched; add a fetchNode step before setLabel"}
	}

	key := step.Params.LabelKey
	valueTmpl := step.Params.LabelValueTemplate
	value, err := labels.ComputeLabelValue(valueTmpl, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute label value: %v", err)}
	}

	if ec.Node.Labels == nil {
		ec.Node.Labels = make(map[string]string)
	}

	// No-op if already correct
	if existing, ok := ec.Node.Labels[key]; ok && existing == value {
		return StepResult{Completed: true, Message: fmt.Sprintf("label %s=%s already correct", key, value)}
	}

	ec.Node.Labels[key] = value
	if err := e.client.Update(ctx, ec.Node); err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to set label: %v", err)}
	}

	// Record in TNA status
	ec.TNA.Status.AssignedLabel = cpv1alpha1.AssignedLabel{Key: key, Value: value}
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("set label %s=%s on node %s", key, value, ec.Node.Name)}
}

func (e *Executor) executeCheckAnnotation(_ context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.Node == nil {
		return StepResult{Failed: true, Message: "node not fetched; add a fetchNode step before checkAnnotation"}
	}

	key := step.Params.AnnotationKey
	expectedVal := step.Params.AnnotationValue

	if val, ok := ec.Node.Annotations[key]; ok && val == expectedVal {
		ec.TNA.Status.Completion.Acknowledged = true
		return StepResult{Completed: true, Message: fmt.Sprintf("annotation %s=%s found", key, expectedVal)}
	}

	if step.WaitIfNotReady {
		return StepResult{Waiting: true, Message: fmt.Sprintf("waiting for annotation %s=%s", key, expectedVal)}
	}
	return StepResult{Failed: true, Message: fmt.Sprintf("annotation %s=%s not found", key, expectedVal)}
}

func (e *Executor) executeCheckLabel(_ context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.Node == nil {
		return StepResult{Failed: true, Message: "node not fetched"}
	}

	key := step.Params.LabelKey
	expectedVal, err := labels.ComputeLabelValue(step.Params.LabelValueTemplate, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute expected label: %v", err)}
	}

	if val, ok := ec.Node.Labels[key]; ok && val == expectedVal {
		return StepResult{Completed: true, Message: fmt.Sprintf("label %s=%s found", key, expectedVal)}
	}

	if step.WaitIfNotReady {
		return StepResult{Waiting: true, Message: fmt.Sprintf("waiting for label %s=%s", key, expectedVal)}
	}
	return StepResult{Failed: true, Message: fmt.Sprintf("label %s=%s not found", key, expectedVal)}
}

func (e *Executor) executeUpdateConfigMap(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	ns := step.Params.ConfigMapNamespace
	name := step.Params.ConfigMapName
	keyTmpl := step.Params.ConfigMapKeyTemplate
	valTmpl := step.Params.ConfigMapValueTemplate

	cmKey, err := labels.ComputeConfigMapKey(keyTmpl, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute configmap key: %v", err)}
	}
	cmVal, err := labels.ComputeConfigMapValue(valTmpl, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute configmap value: %v", err)}
	}

	cm := &corev1.ConfigMap{}
	err = e.client.Get(ctx, types.NamespacedName{Namespace: ns, Name: name}, cm)
	if errors.IsNotFound(err) {
		cm = &corev1.ConfigMap{
			ObjectMeta: metav1.ObjectMeta{
				Name: name, Namespace: ns,
				Labels: map[string]string{
					"app.kubernetes.io/managed-by": "tenant-node-assignment-operator",
				},
			},
			Data: map[string]string{cmKey: cmVal},
		}
		if err := e.client.Create(ctx, cm); err != nil {
			return StepResult{Failed: true, Message: fmt.Sprintf("failed to create configmap: %v", err)}
		}
		ec.TNA.Status.Readiness.ConfigMapUpdated = true
		return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("created configmap %s/%s with %s=%s", ns, name, cmKey, cmVal)}
	}
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to get configmap: %v", err)}
	}

	if cm.Data == nil {
		cm.Data = make(map[string]string)
	}
	if existing, ok := cm.Data[cmKey]; ok && existing == cmVal {
		ec.TNA.Status.Readiness.ConfigMapUpdated = true
		return StepResult{Completed: true, Message: "configmap entry already correct"}
	}

	cm.Data[cmKey] = cmVal
	if err := e.client.Update(ctx, cm); err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to update configmap: %v", err)}
	}
	ec.TNA.Status.Readiness.ConfigMapUpdated = true
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("updated configmap %s/%s: %s=%s", ns, name, cmKey, cmVal)}
}

func (e *Executor) executeRemoveLabel(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.Node == nil {
		return StepResult{Failed: true, Message: "node not fetched"}
	}
	key := step.Params.LabelKey
	if _, ok := ec.Node.Labels[key]; !ok {
		return StepResult{Completed: true, Message: fmt.Sprintf("label %s already absent", key)}
	}
	delete(ec.Node.Labels, key)
	if err := e.client.Update(ctx, ec.Node); err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to remove label: %v", err)}
	}
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("removed label %s from node %s", key, ec.Node.Name)}
}

func (e *Executor) executeRemoveAnnotation(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.Node == nil {
		return StepResult{Failed: true, Message: "node not fetched"}
	}
	key := step.Params.AnnotationKey
	if ec.Node.Annotations == nil {
		return StepResult{Completed: true, Message: fmt.Sprintf("annotation %s already absent", key)}
	}
	if _, ok := ec.Node.Annotations[key]; !ok {
		return StepResult{Completed: true, Message: fmt.Sprintf("annotation %s already absent", key)}
	}
	delete(ec.Node.Annotations, key)
	if err := e.client.Update(ctx, ec.Node); err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to remove annotation: %v", err)}
	}
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("removed annotation %s from node %s", key, ec.Node.Name)}
}

func (e *Executor) executeRemoveConfigMapEntry(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	ns := step.Params.ConfigMapNamespace
	name := step.Params.ConfigMapName
	keyTmpl := step.Params.ConfigMapKeyTemplate

	cmKey, err := labels.ComputeConfigMapKey(keyTmpl, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute configmap key: %v", err)}
	}

	cm := &corev1.ConfigMap{}
	err = e.client.Get(ctx, types.NamespacedName{Namespace: ns, Name: name}, cm)
	if errors.IsNotFound(err) {
		return StepResult{Completed: true, Message: "configmap not found, nothing to remove"}
	}
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to get configmap: %v", err)}
	}
	if cm.Data == nil {
		return StepResult{Completed: true, Message: "configmap has no data"}
	}
	if _, ok := cm.Data[cmKey]; !ok {
		return StepResult{Completed: true, Message: fmt.Sprintf("configmap key %s already absent", cmKey)}
	}

	delete(cm.Data, cmKey)
	if err := e.client.Update(ctx, cm); err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to update configmap: %v", err)}
	}
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("removed configmap entry %s from %s/%s", cmKey, ns, name)}
}

func (e *Executor) executeSetAnnotation(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	if ec.Node == nil {
		return StepResult{Failed: true, Message: "node not fetched"}
	}
	key := step.Params.AnnotationKey
	value := step.Params.AnnotationValue

	if ec.Node.Annotations == nil {
		ec.Node.Annotations = make(map[string]string)
	}
	if existing, ok := ec.Node.Annotations[key]; ok && existing == value {
		return StepResult{Completed: true, Message: fmt.Sprintf("annotation %s=%s already correct", key, value)}
	}

	ec.Node.Annotations[key] = value
	if err := e.client.Update(ctx, ec.Node); err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to set annotation: %v", err)}
	}
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("set annotation %s=%s on node %s", key, value, ec.Node.Name)}
}

func (e *Executor) executeSetPhase(_ context.Context, step Step, ec *ExecutionContext) StepResult {
	phase := cpv1alpha1.TenantNodeAssignmentPhase(step.Params.Phase)
	ec.TNA.Status.Phase = phase
	return StepResult{Completed: true, Modified: true, Message: fmt.Sprintf("set phase to %s", phase)}
}

func (e *Executor) executeCheckConfigMap(ctx context.Context, step Step, ec *ExecutionContext) StepResult {
	ns := step.Params.ConfigMapNamespace
	name := step.Params.ConfigMapName
	keyTmpl := step.Params.ConfigMapKeyTemplate
	valTmpl := step.Params.ConfigMapValueTemplate

	cmKey, err := labels.ComputeConfigMapKey(keyTmpl, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute key: %v", err)}
	}
	cmVal, err := labels.ComputeConfigMapValue(valTmpl, ec.TmplData)
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to compute value: %v", err)}
	}

	cm := &corev1.ConfigMap{}
	err = e.client.Get(ctx, types.NamespacedName{Namespace: ns, Name: name}, cm)
	if errors.IsNotFound(err) {
		if step.WaitIfNotReady {
			return StepResult{Waiting: true, Message: "configmap not found, waiting"}
		}
		return StepResult{Failed: true, Message: "configmap not found"}
	}
	if err != nil {
		return StepResult{Failed: true, Message: fmt.Sprintf("failed to get configmap: %v", err)}
	}

	if val, ok := cm.Data[cmKey]; ok && val == cmVal {
		return StepResult{Completed: true, Message: fmt.Sprintf("configmap %s/%s has %s=%s", ns, name, cmKey, cmVal)}
	}

	if step.WaitIfNotReady {
		return StepResult{Waiting: true, Message: fmt.Sprintf("waiting for configmap entry %s=%s", cmKey, cmVal)}
	}
	return StepResult{Failed: true, Message: fmt.Sprintf("configmap entry %s does not match expected value", cmKey)}
}
