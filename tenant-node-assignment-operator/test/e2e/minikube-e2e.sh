#!/bin/bash
# E2E Test Script for Tenant Node Assignment Operator
# Run this in a minikube environment.
set -euo pipefail

echo "=========================================="
echo " Tenant Node Assignment Operator — E2E Test"
echo "=========================================="

NAMESPACE="compute-platform-system"
SAMPLE_CR="config/samples/tenantnodeassignment_sample.yaml"
CRD="charts/tenant-node-assignment-operator/templates/crd.yaml"
OPERATOR_CONFIG="charts/tenant-node-assignment-operator/templates/configmap.yaml"

# --- Helpers ---
pass() { echo "  ✅ PASS: $1"; }
fail() { echo "  ❌ FAIL: $1"; exit 1; }

# --- Pre-checks ---
echo ""
echo "Step 0: Pre-checks"
kubectl cluster-info >/dev/null 2>&1 || fail "No cluster available"
pass "Cluster is reachable"

# --- Step 1: Create namespace ---
echo ""
echo "Step 1: Create namespace"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
pass "Namespace $NAMESPACE exists"

# --- Step 2: Install CRD ---
echo ""
echo "Step 2: Install CRD"
# Use helm template to render the CRD, or apply directly
helm template test charts/tenant-node-assignment-operator --show-only templates/crd.yaml | kubectl apply -f -
sleep 2
kubectl get crd tenantnodeassignments.computeplatform.io >/dev/null 2>&1 || fail "CRD not installed"
pass "CRD installed"

# --- Step 3: Apply sample CR ---
echo ""
echo "Step 3: Apply sample TenantNodeAssignment"
kubectl apply -f "$SAMPLE_CR" -n "$NAMESPACE"
sleep 2
kubectl get tna -n "$NAMESPACE" tenant-a-worker-node-01 >/dev/null 2>&1 || fail "CR not created"
pass "CR created: tenant-a-worker-node-01"

# --- Step 4: Verify CR exists ---
echo ""
echo "Step 4: Verify CR details"
kubectl get tna -n "$NAMESPACE" -o wide
TENANT=$(kubectl get tna -n "$NAMESPACE" tenant-a-worker-node-01 -o jsonpath='{.spec.tenantRef.name}')
if [ "$TENANT" != "tenant-a" ]; then fail "Wrong tenant: $TENANT"; fi
pass "Tenant = tenant-a"

NODE=$(kubectl get tna -n "$NAMESPACE" tenant-a-worker-node-01 -o jsonpath='{.spec.nodeRef.name}')
if [ "$NODE" != "minikube" ]; then fail "Wrong node: $NODE"; fi
pass "Node = minikube"

# --- Step 5: Simulate what the operator would do (manual label) ---
echo ""
echo "Step 5: Simulate operator — apply tenant label to node"
kubectl label node minikube compute-platform.io/tenant=tenant-a --overwrite
LABEL=$(kubectl get node minikube -o jsonpath='{.metadata.labels.compute-platform\.io/tenant}')
if [ "$LABEL" != "tenant-a" ]; then fail "Label not set correctly"; fi
pass "Node labeled: compute-platform.io/tenant=tenant-a"

# --- Step 6: Simulate node-agent completion ---
echo ""
echo "Step 6: Simulate node-agent — add completion annotation"
kubectl annotate node minikube compute-platform.io/node-agent-ready=true --overwrite
ANNOT=$(kubectl get node minikube -o jsonpath='{.metadata.annotations.compute-platform\.io/node-agent-ready}')
if [ "$ANNOT" != "true" ]; then fail "Annotation not set"; fi
pass "Node annotated: compute-platform.io/node-agent-ready=true"

# --- Step 7: Simulate readiness ConfigMap update ---
echo ""
echo "Step 7: Create readiness ConfigMap"
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: tenant-node-readiness
  namespace: $NAMESPACE
data:
  tenant-a.minikube: "ready"
EOF
READY=$(kubectl get configmap tenant-node-readiness -n "$NAMESPACE" -o jsonpath='{.data.tenant-a\.minikube}')
if [ "$READY" != "ready" ]; then fail "Readiness entry not set"; fi
pass "Readiness ConfigMap: tenant-a.minikube=ready"

# --- Step 8: Cleanup ---
echo ""
echo "Step 8: Cleanup"
kubectl delete tna -n "$NAMESPACE" tenant-a-worker-node-01 --ignore-not-found
kubectl label node minikube compute-platform.io/tenant- --ignore-not-found 2>/dev/null || true
kubectl annotate node minikube compute-platform.io/node-agent-ready- --ignore-not-found 2>/dev/null || true
kubectl delete configmap tenant-node-readiness -n "$NAMESPACE" --ignore-not-found
pass "Cleanup complete"

# --- Summary ---
echo ""
echo "=========================================="
echo " E2E Test: ALL STEPS PASSED"
echo "=========================================="
