package config

import (
	"testing"
)

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Workflow.Name != "tenant-node-assignment" {
		t.Errorf("expected workflow name 'tenant-node-assignment', got '%s'", cfg.Workflow.Name)
	}
	if len(cfg.Workflow.Steps) == 0 {
		t.Error("default config should have workflow steps")
	}
	if len(cfg.Workflow.CleanupSteps) == 0 {
		t.Error("default config should have cleanup steps")
	}
	if cfg.Reconciliation.RequeueSeconds != 15 {
		t.Errorf("expected requeueSeconds = 15, got %d", cfg.Reconciliation.RequeueSeconds)
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("default config should be valid: %v", err)
	}
}

func TestLoadFromYAML_CustomWorkflow(t *testing.T) {
	yamlData := []byte(`
workflow:
  name: custom-workflow
  description: A custom workflow
  steps:
    - name: validate
      type: validateSpec
    - name: fetch
      type: fetchNode
    - name: set-label
      type: setLabel
      params:
        labelKey: custom.io/owner
        labelValueTemplate: "{{ .TenantName }}"
  cleanupSteps:
    - name: cleanup-label
      type: removeLabel
      continueOnFailure: true
      params:
        labelKey: custom.io/owner
reconciliation:
  requeueSeconds: 30
`)
	cfg, err := LoadFromYAML(yamlData)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Workflow.Name != "custom-workflow" {
		t.Errorf("expected 'custom-workflow', got '%s'", cfg.Workflow.Name)
	}
	if len(cfg.Workflow.Steps) != 3 {
		t.Errorf("expected 3 steps, got %d", len(cfg.Workflow.Steps))
	}
	if cfg.Reconciliation.RequeueSeconds != 30 {
		t.Errorf("expected 30, got %d", cfg.Reconciliation.RequeueSeconds)
	}
}

func TestLoadFromYAML_InvalidYAML(t *testing.T) {
	_, err := LoadFromYAML([]byte(`{invalid yaml`))
	if err == nil {
		t.Error("expected error for invalid YAML")
	}
}

func TestValidate_EmptySteps(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Workflow.Steps = nil
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for empty steps")
	}
}

func TestValidate_EmptyWorkflowName(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Workflow.Name = ""
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for empty workflow name")
	}
}

func TestValidate_ZeroRequeueSeconds(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Reconciliation.RequeueSeconds = 0
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for zero requeue seconds")
	}
}

func TestValidate_NegativeRequeueSeconds(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Reconciliation.RequeueSeconds = -5
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for negative requeue seconds")
	}
}

func TestValidate_StepWithEmptyType(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Workflow.Steps[0].Type = ""
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for step with empty type")
	}
}

func TestLoadFromYAML_PartialOverride(t *testing.T) {
	// Override only requeueSeconds, workflow should stay default
	yamlData := []byte(`
reconciliation:
  requeueSeconds: 60
`)
	cfg, err := LoadFromYAML(yamlData)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Reconciliation.RequeueSeconds != 60 {
		t.Errorf("expected 60, got %d", cfg.Reconciliation.RequeueSeconds)
	}
	// Workflow should still be default
	if cfg.Workflow.Name != "tenant-node-assignment" {
		t.Errorf("workflow name should remain default, got '%s'", cfg.Workflow.Name)
	}
}
