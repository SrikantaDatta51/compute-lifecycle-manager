package labels

import (
	"testing"
)

func TestComputeLabelValue_Simple(t *testing.T) {
	data := TemplateData{TenantName: "tenant-a", NodeName: "worker-01"}
	result, err := ComputeLabelValue("{{ .TenantName }}", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "tenant-a" {
		t.Errorf("expected 'tenant-a', got '%s'", result)
	}
}

func TestComputeLabelValue_Combined(t *testing.T) {
	data := TemplateData{TenantName: "acme", NodeName: "node-1"}
	result, err := ComputeLabelValue("{{ .TenantName }}-{{ .NodeName }}", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "acme-node-1" {
		t.Errorf("expected 'acme-node-1', got '%s'", result)
	}
}

func TestComputeLabelValue_InvalidTemplate(t *testing.T) {
	data := TemplateData{TenantName: "test"}
	_, err := ComputeLabelValue("{{ .Invalid", data)
	if err == nil {
		t.Error("expected error for invalid template")
	}
}

func TestComputeLabelValue_EmptyResult(t *testing.T) {
	data := TemplateData{TenantName: ""}
	_, err := ComputeLabelValue("{{ .TenantName }}", data)
	if err == nil {
		t.Error("expected error for empty result")
	}
}

func TestComputeConfigMapKey(t *testing.T) {
	data := TemplateData{TenantName: "tenant-b", NodeName: "worker-02"}
	result, err := ComputeConfigMapKey("{{ .TenantName }}.{{ .NodeName }}", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "tenant-b.worker-02" {
		t.Errorf("expected 'tenant-b.worker-02', got '%s'", result)
	}
}

func TestComputeConfigMapKey_InvalidTemplate(t *testing.T) {
	data := TemplateData{TenantName: "test"}
	_, err := ComputeConfigMapKey("{{ .Bad", data)
	if err == nil {
		t.Error("expected error for invalid template")
	}
}

func TestComputeConfigMapValue(t *testing.T) {
	data := TemplateData{TenantName: "tenant-c", NodeName: "worker-03"}
	result, err := ComputeConfigMapValue("ready", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "ready" {
		t.Errorf("expected 'ready', got '%s'", result)
	}
}

func TestComputeConfigMapValue_InvalidTemplate(t *testing.T) {
	data := TemplateData{TenantName: "test"}
	_, err := ComputeConfigMapValue("{{ .Bad", data)
	if err == nil {
		t.Error("expected error for invalid template")
	}
}

func TestComputeLabelValue_StaticValue(t *testing.T) {
	data := TemplateData{TenantName: "tenant-x"}
	result, err := ComputeLabelValue("assigned", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "assigned" {
		t.Errorf("expected 'assigned', got '%s'", result)
	}
}
