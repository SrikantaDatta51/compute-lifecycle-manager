// Package config provides runtime configuration loading for the operator.
// The configuration includes a generic workflow definition that drives
// all reconciliation behavior, making the operator fully YAML-configurable.
package config

import (
	"fmt"

	"gopkg.in/yaml.v3"

	"github.com/compute-platform/tenant-node-assignment-operator/internal/workflow"
)

// OperatorConfig holds the complete runtime configuration.
type OperatorConfig struct {
	// Workflow defines the ordered reconciliation and cleanup steps.
	Workflow    workflow.WorkflowDefinition `yaml:"workflow" json:"workflow"`
	// Reconciliation timing settings.
	Reconciliation ReconciliationConfig `yaml:"reconciliation" json:"reconciliation"`
}

// ReconciliationConfig defines reconciliation timing.
type ReconciliationConfig struct {
	// RequeueSeconds is the default requeue interval for waiting steps.
	RequeueSeconds int `yaml:"requeueSeconds" json:"requeueSeconds"`
}

// DefaultConfig returns the default operator configuration with the
// standard tenant-node-assignment workflow pre-defined.
func DefaultConfig() *OperatorConfig {
	return &OperatorConfig{
		Workflow: workflow.WorkflowDefinition{
			Name:        "tenant-node-assignment",
			Description: "Assigns a node to a tenant by labeling it for activation, waiting for node-agent completion, and updating a readiness ConfigMap.",
			Steps: []workflow.Step{
				{
					Name:        "validate-spec",
					Type:        workflow.StepValidateSpec,
					Description: "Validate that tenantRef and nodeRef are present",
				},
				{
					Name:        "fetch-target-node",
					Type:        workflow.StepFetchNode,
					Description: "Fetch the target Kubernetes node",
				},
				{
					Name:        "apply-tenant-label",
					Type:        workflow.StepSetLabel,
					Description: "Apply the tenant ownership label to the node",
					OnSuccess:   "LabelApplied",
					Params: workflow.StepParams{
						LabelKey:           "compute-platform.io/tenant",
						LabelValueTemplate: "{{ .TenantName }}",
					},
				},
				{
					Name:           "await-node-agent-completion",
					Type:           workflow.StepCheckAnnotation,
					Description:    "Wait for the node-agent to signal completion via annotation",
					WaitIfNotReady: true,
					OnSuccess:      "AwaitingNodeAgent",
					Params: workflow.StepParams{
						AnnotationKey:   "compute-platform.io/node-agent-ready",
						AnnotationValue: "true",
					},
				},
				{
					Name:        "update-readiness-configmap",
					Type:        workflow.StepUpdateConfigMap,
					Description: "Record node readiness in the platform ConfigMap",
					Params: workflow.StepParams{
						ConfigMapNamespace:     "compute-platform-system",
						ConfigMapName:          "tenant-node-readiness",
						ConfigMapKeyTemplate:   "{{ .TenantName }}.{{ .NodeName }}",
						ConfigMapValueTemplate: "ready",
					},
				},
			},
			CleanupSteps: []workflow.Step{
				{
					Name:              "fetch-node-for-cleanup",
					Type:              workflow.StepFetchNode,
					Description:       "Fetch node for label removal",
					ContinueOnFailure: true,
				},
				{
					Name:              "remove-tenant-label",
					Type:              workflow.StepRemoveLabel,
					Description:       "Remove the tenant label from the node",
					ContinueOnFailure: true,
					Params: workflow.StepParams{
						LabelKey: "compute-platform.io/tenant",
					},
				},
				{
					Name:              "remove-readiness-entry",
					Type:              workflow.StepRemoveConfigMapEntry,
					Description:       "Remove the readiness ConfigMap entry",
					ContinueOnFailure: true,
					Params: workflow.StepParams{
						ConfigMapNamespace:   "compute-platform-system",
						ConfigMapName:        "tenant-node-readiness",
						ConfigMapKeyTemplate: "{{ .TenantName }}.{{ .NodeName }}",
					},
				},
			},
		},
		Reconciliation: ReconciliationConfig{
			RequeueSeconds: 15,
		},
	}
}

// LoadFromYAML parses configuration from YAML bytes.
func LoadFromYAML(data []byte) (*OperatorConfig, error) {
	cfg := DefaultConfig()
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("failed to parse operator config YAML: %w", err)
	}
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("invalid operator config: %w", err)
	}
	return cfg, nil
}

// Validate checks configuration validity.
func (c *OperatorConfig) Validate() error {
	if len(c.Workflow.Steps) == 0 {
		return fmt.Errorf("workflow.steps must not be empty")
	}
	if c.Workflow.Name == "" {
		return fmt.Errorf("workflow.name must not be empty")
	}
	if c.Reconciliation.RequeueSeconds <= 0 {
		return fmt.Errorf("reconciliation.requeueSeconds must be positive")
	}
	for i, step := range c.Workflow.Steps {
		if step.Type == "" {
			return fmt.Errorf("workflow.steps[%d].type must not be empty", i)
		}
	}
	return nil
}
