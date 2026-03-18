#!/usr/bin/env bash
###############################################################################
# fleet-certify.sh — Main Orchestrator for Fleet Validation Framework
###############################################################################
# Entry point for daily node certification. Triggered by systemd timer or
# manual invocation. Enumerates non-protected nodes, runs configured test
# suite, transitions failed nodes, pushes metrics, writes cert records.
#
# Usage:
#   fleet-certify.sh [--suite <name>] [--nodes <node1,node2>] [--dry-run]
#   fleet-certify.sh --suite daily-quick
#   fleet-certify.sh --suite full-certification --nodes dgx-b200-001
#
# Environment:
#   FLEET_VALIDATOR_HOME — root of fleet-validator (default: script dir/..)
#   CMSH_BIN             — path to cmsh (default: /usr/bin/cmsh)
#   PUSHGATEWAY_URL      — Prometheus pushgateway (default: localhost:9091)
#   DRY_RUN              — if "true", skip state transitions and metrics push
###############################################################################
set -euo pipefail

# ── Paths ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_VALIDATOR_HOME="${FLEET_VALIDATOR_HOME:-$(dirname "$SCRIPT_DIR")}"
CONFIG_DIR="${FLEET_VALIDATOR_HOME}/config"
BIN_DIR="${FLEET_VALIDATOR_HOME}/bin"
LOG_DIR="${FLEET_VALIDATOR_HOME}/logs"
CERT_DIR="/var/lib/fleet-validator/certifications"

# ── Defaults ──
SUITE="daily-quick"
SPECIFIC_NODES=""
DRY_RUN="${DRY_RUN:-false}"
CMSH_BIN="${CMSH_BIN:-/usr/bin/cmsh}"
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
PROTECTED_NODES_FILE="/etc/fleet-validator/protected-nodes.txt"

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'
YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log_info()  { echo -e "${BLUE}[$(date -Iseconds)] [INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[$(date -Iseconds)] [OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[$(date -Iseconds)] [WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[$(date -Iseconds)] [ERROR]${NC} $*"; }
log_step()  { echo -e "${CYAN}[$(date -Iseconds)] [STEP]${NC}  $*"; }

# ── Argument Parsing ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --suite)      SUITE="$2";          shift 2 ;;
        --nodes)      SPECIFIC_NODES="$2"; shift 2 ;;
        --dry-run)    DRY_RUN="true";      shift ;;
        --help|-h)
            echo "Usage: $0 [--suite <name>] [--nodes <n1,n2>] [--dry-run]"
            echo ""
            echo "Suites: daily-quick, gpu-burn, nccl-multinode, full-certification"
            exit 0 ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Setup ──
SUITE_FILE="${CONFIG_DIR}/test-suites/${SUITE}.yml"
[[ -f "$SUITE_FILE" ]] || { log_error "Suite file not found: ${SUITE_FILE}"; exit 1; }

mkdir -p "$LOG_DIR" "$CERT_DIR"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="${LOG_DIR}/run-${RUN_ID}.log"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Continuous Monitoring & Fleet Validation Framework      ║${NC}"
echo -e "${CYAN}║                    Daily Certification                      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Suite:     ${SUITE}"
log_info "Run ID:    ${RUN_ID}"
log_info "Dry run:   ${DRY_RUN}"
log_info "Log:       ${RUN_LOG}"
echo ""

###############################################################################
# Helper: Parse YAML (lightweight — uses grep/awk, no python dependency)
###############################################################################
yaml_value() {
    local file="$1" key="$2"
    grep "^${key}:" "$file" 2>/dev/null | head -1 | sed "s/^${key}:[[:space:]]*//" | tr -d '"'
}

yaml_list() {
    local file="$1" key="$2"
    awk "/^${key}:/{found=1; next} found && /^  - /{print substr(\$0, 5); next} found && /^[^ ]/{exit}" "$file"
}

###############################################################################
# Step 1: Enumerate Nodes
###############################################################################
enumerate_nodes() {
    log_step "Step 1/6 — Enumerating nodes..."

    if [[ -n "$SPECIFIC_NODES" ]]; then
        echo "$SPECIFIC_NODES" | tr ',' '\n'
        return
    fi

    # Get all compute nodes from BCM
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY_RUN: Returning sample nodes"
        echo "dgx-b200-001"
        echo "dgx-b200-002"
        return
    fi

    ${CMSH_BIN} -c "device; list" 2>/dev/null | \
        grep -E "^\s+\S+" | \
        awk '{print $1}' | \
        grep -v "^$" | \
        sort
}

###############################################################################
# Step 2: Filter Protected Nodes
###############################################################################
is_node_protected() {
    local node="$1"

    # Check 1: Explicit exclusion file
    if [[ -f "$PROTECTED_NODES_FILE" ]] && grep -qx "$node" "$PROTECTED_NODES_FILE"; then
        return 0  # protected
    fi

    # Check 2: BCM allocation status (customer-assigned)
    if [[ "$DRY_RUN" != "true" ]]; then
        local alloc
        alloc=$(${CMSH_BIN} -c "device; use ${node}; get allocation" 2>/dev/null | tail -1 | tr -d '[:space:]')
        if [[ -n "$alloc" && "$alloc" != "none" && "$alloc" != "(null)" ]]; then
            return 0  # protected — has allocation
        fi
    fi

    # Check 3: Kubernetes node labels (if kubectl available)
    if command -v kubectl &>/dev/null; then
        local label
        label=$(kubectl get node "$node" -o jsonpath='{.metadata.labels.node-role\.kubernetes\.io/customer}' 2>/dev/null || true)
        if [[ "$label" == "true" ]]; then
            return 0  # protected — K8s customer label
        fi
    fi

    return 1  # not protected
}

filter_nodes() {
    local all_nodes=("$@")
    local eligible=()

    for node in "${all_nodes[@]}"; do
        if is_node_protected "$node"; then
            log_warn "Skipping protected node: ${node}"
        else
            eligible+=("$node")
        fi
    done

    printf '%s\n' "${eligible[@]}"
}

###############################################################################
# Step 3: Detect GPU SKU
###############################################################################
detect_sku() {
    local node="$1"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "b200"
        return
    fi

    local gpu_name
    gpu_name=$(${CMSH_BIN} -c "device; use ${node}; exec 'nvidia-smi --query-gpu=name --format=csv,noheader | head -1'" 2>/dev/null | tail -1)

    case "${gpu_name,,}" in
        *b200*|*blackwell*) echo "b200" ;;
        *h200*|*hopper*)    echo "h200" ;;
        *h100*)             echo "h100" ;;
        *)
            log_warn "Unknown GPU: ${gpu_name} on ${node}, defaulting to b200"
            echo "b200"
            ;;
    esac
}

###############################################################################
# Step 4: Run Test Suite
###############################################################################
run_suite_on_node() {
    local node="$1"
    local sku="$2"
    local suite_file="$3"
    local node_log_dir="${LOG_DIR}/${node}/${RUN_ID}"
    mkdir -p "$node_log_dir"

    log_step "Running suite '${SUITE}' on ${node} (SKU: ${sku})"

    # Transition node to testing state
    if [[ "$DRY_RUN" != "true" ]]; then
        "${BIN_DIR}/node-state-manager.sh" transition "$node" "testing" \
            "certification_started" 2>&1 | tee -a "${node_log_dir}/state.log" || true
    fi

    # Run the test suite
    local result
    result=$("${BIN_DIR}/run-test-suite.sh" \
        --suite "$suite_file" \
        --node "$node" \
        --sku "${CONFIG_DIR}/sku-profiles/${sku}.yml" \
        --output-dir "$node_log_dir" \
        --cmsh "$CMSH_BIN" \
        ${DRY_RUN:+--dry-run} 2>&1 | tee -a "${node_log_dir}/tests.log")

    local exit_code=$?
    echo "$result" > "${node_log_dir}/result.txt"

    echo "$exit_code"
}

###############################################################################
# Step 5: Process Results & State Transitions
###############################################################################
process_result() {
    local node="$1"
    local exit_code="$2"
    local node_log_dir="${LOG_DIR}/${node}/${RUN_ID}"

    if [[ "$exit_code" -eq 0 ]]; then
        log_ok "✅ ${node} — ALL TESTS PASSED"

        # Transition to healthy
        if [[ "$DRY_RUN" != "true" ]]; then
            "${BIN_DIR}/node-state-manager.sh" transition "$node" "healthy" \
                "all_tests_passed" 2>&1 | tee -a "${node_log_dir}/state.log"
        fi

        # Write certification record
        "${BIN_DIR}/certification-report.sh" \
            --node "$node" \
            --suite "$SUITE" \
            --status "CERTIFIED" \
            --log-dir "$node_log_dir" \
            --output-dir "$CERT_DIR"
    else
        # Determine failure class from test output
        local failure_class="software"  # default to less severe
        if grep -q '"failure_class":"hardware"' "${node_log_dir}/result.json" 2>/dev/null; then
            failure_class="hardware"
        fi

        if [[ "$failure_class" == "hardware" ]]; then
            log_error "❌ ${node} — HARDWARE FAILURE DETECTED → RMA"
            local target_state="rma"
            local trigger="hardware_failure_detected"
        else
            log_warn "⚠️  ${node} — SOFTWARE ISSUE DETECTED → MAINTENANCE"
            local target_state="maintenance"
            local trigger="software_failure_detected"
        fi

        # Transition node
        if [[ "$DRY_RUN" != "true" ]]; then
            "${BIN_DIR}/node-state-manager.sh" transition "$node" "$target_state" \
                "$trigger" 2>&1 | tee -a "${node_log_dir}/state.log"

            # Collect debug bundle for failed nodes
            log_info "Collecting debug bundle for ${node}..."
            "${BIN_DIR}/node-state-manager.sh" collect-debug "$node" \
                "${node_log_dir}" 2>&1 | tee -a "${node_log_dir}/debug.log" || true
        fi

        # Write failure record
        "${BIN_DIR}/certification-report.sh" \
            --node "$node" \
            --suite "$SUITE" \
            --status "FAILED:${target_state}" \
            --log-dir "$node_log_dir" \
            --output-dir "$CERT_DIR"
    fi
}

###############################################################################
# Step 6: Push Metrics & Summary
###############################################################################
push_metrics() {
    local total="$1" passed="$2" failed="$3"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY_RUN: Skipping metrics push"
        return
    fi

    "${BIN_DIR}/collect-metrics.sh" \
        --run-id "$RUN_ID" \
        --suite "$SUITE" \
        --total "$total" \
        --passed "$passed" \
        --failed "$failed" \
        --pushgateway "$PUSHGATEWAY_URL" \
        --log-dir "$LOG_DIR" 2>&1 || log_warn "Metrics push failed (non-fatal)"
}

###############################################################################
# Main Execution
###############################################################################
main() {
    local start_time
    start_time=$(date +%s)

    # Step 1: Get all nodes
    mapfile -t all_nodes < <(enumerate_nodes)
    log_info "Found ${#all_nodes[@]} total node(s)"

    # Step 2: Filter protected nodes
    mapfile -t eligible_nodes < <(filter_nodes "${all_nodes[@]}")
    log_info "Eligible for testing: ${#eligible_nodes[@]} node(s)"

    if [[ ${#eligible_nodes[@]} -eq 0 ]]; then
        log_warn "No eligible nodes to test. Exiting."
        exit 0
    fi

    # Run tests on each node
    local total=0 passed=0 failed=0

    for node in "${eligible_nodes[@]}"; do
        total=$((total + 1))
        echo ""
        echo -e "${CYAN}────────────────────────────────────────────────────${NC}"
        log_step "Node ${total}/${#eligible_nodes[@]}: ${node}"
        echo -e "${CYAN}────────────────────────────────────────────────────${NC}"

        # Step 3: Detect SKU
        local sku
        sku=$(detect_sku "$node")

        # Step 4: Run suite
        local exit_code
        exit_code=$(run_suite_on_node "$node" "$sku" "$SUITE_FILE")

        # Step 5: Process result
        process_result "$node" "$exit_code"

        if [[ "$exit_code" -eq 0 ]]; then
            passed=$((passed + 1))
        else
            failed=$((failed + 1))
        fi
    done

    # Step 6: Push metrics
    push_metrics "$total" "$passed" "$failed"

    # Summary
    local end_time duration
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                   CERTIFICATION SUMMARY                     ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log_info "Run ID:     ${RUN_ID}"
    log_info "Suite:      ${SUITE}"
    log_info "Duration:   ${duration}s"
    log_info "Total:      ${total}"
    log_ok   "Passed:     ${passed}"
    [[ $failed -gt 0 ]] && log_error "Failed:     ${failed}" || log_ok "Failed:     ${failed}"
    log_info "Cert rate:  $(( (passed * 100) / (total > 0 ? total : 1) ))%"
    log_info "Log dir:    ${LOG_DIR}"
    log_info "Cert dir:   ${CERT_DIR}"
    echo ""

    # Exit with failure if any node failed
    [[ $failed -eq 0 ]]
}

main 2>&1 | tee -a "$RUN_LOG"
