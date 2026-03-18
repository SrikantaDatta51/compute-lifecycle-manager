// Package labels provides label computation for tenant node assignments.
package labels

import (
	"bytes"
	"fmt"
	"text/template"
)

// TemplateData holds data available for label template expansion.
type TemplateData struct {
	TenantName string
	NodeName   string
}

// ComputeLabelValue expands a Go text/template with the given template data.
func ComputeLabelValue(tmpl string, data TemplateData) (string, error) {
	t, err := template.New("label").Parse(tmpl)
	if err != nil {
		return "", fmt.Errorf("failed to parse label template %q: %w", tmpl, err)
	}
	var buf bytes.Buffer
	if err := t.Execute(&buf, data); err != nil {
		return "", fmt.Errorf("failed to execute label template %q: %w", tmpl, err)
	}
	result := buf.String()
	if result == "" {
		return "", fmt.Errorf("label template %q produced empty value", tmpl)
	}
	return result, nil
}

// ComputeConfigMapKey expands a Go text/template for ConfigMap entry key.
func ComputeConfigMapKey(tmpl string, data TemplateData) (string, error) {
	t, err := template.New("cmkey").Parse(tmpl)
	if err != nil {
		return "", fmt.Errorf("failed to parse configmap key template %q: %w", tmpl, err)
	}
	var buf bytes.Buffer
	if err := t.Execute(&buf, data); err != nil {
		return "", fmt.Errorf("failed to execute configmap key template %q: %w", tmpl, err)
	}
	return buf.String(), nil
}

// ComputeConfigMapValue expands a Go text/template for ConfigMap entry value.
func ComputeConfigMapValue(tmpl string, data TemplateData) (string, error) {
	t, err := template.New("cmval").Parse(tmpl)
	if err != nil {
		return "", fmt.Errorf("failed to parse configmap value template %q: %w", tmpl, err)
	}
	var buf bytes.Buffer
	if err := t.Execute(&buf, data); err != nil {
		return "", fmt.Errorf("failed to execute configmap value template %q: %w", tmpl, err)
	}
	return buf.String(), nil
}
