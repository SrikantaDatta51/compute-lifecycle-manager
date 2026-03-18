#!/usr/bin/env bash
###############################################################################
# run-test-suite.sh — YAML-driven test executor
###############################################################################
# Reads a YAML test suite definition and runs each test on a target node
# via BCM cmsh. Returns structured JSON results.
#
# Usage:
#   run-test-suite.sh --suite <file> --node <name> --sku <file>
#                     --output-dir <dir> --cmsh <path> [--dry-run]
###############################################################################
set -euo pipefail

# ── Defaults ──
SUITE_FILE=""
NODE=""
SKU_FILE=""
OUTPUT_DIR="."
CMSH_BIN="/usr/bin/cmsh"
DRY_RUN="false"

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'
YELLOW='\033[0;33m'; NC='\033[0m'

log_info()  { echo -e "${BLUE}[$(date -Iseconds)] [TEST]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[$(date -Iseconds)] [PASS]${NC}  $*"; }
log_fail()  { echo -e "${RED}[$(date -Iseconds)] [FAIL]${NC}  $*"; }
log_skip()  { echo -e "${YELLOW}[$(date -Iseconds)] [SKIP]${NC}  $*"; }

# ── Argument Parsing ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --suite)      SUITE_FILE="$2";  shift 2 ;;
        --node)       NODE="$2";        shift 2 ;;
        --sku)        SKU_FILE="$2";    shift 2 ;;
        --output-dir) OUTPUT_DIR="$2";  shift 2 ;;
        --cmsh)       CMSH_BIN="$2";    shift 2 ;;
        --dry-run)    DRY_RUN="true";   shift ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

[[ -z "$SUITE_FILE" || -z "$NODE" || -z "$SKU_FILE" ]] && {
    echo "Usage: $0 --suite <file> --node <name> --sku <file> [--output-dir <dir>]"
    exit 1
}

mkdir -p "$OUTPUT_DIR"

###############################################################################
# Load SKU thresholds into environment variables
###############################################################################
load_sku_profile() {
    local file="$1"
    while IFS=': ' read -r key value; do
        key=$(echo "$key" | tr -d '[:space:]')
        value=$(echo "$value" | tr -d '"[:space:]')
        [[ -z "$key" || "$key" == "#"* || "$key" == "---" ]] && continue
        export "SKU_${key^^}=${value}"
    done < "$file"

    # Set convenience variables used by test commands
    export GPU_COUNT="${SKU_GPU_COUNT:-8}"
    export NCCL_CONTAINER_IMAGE="${SKU_NCCL_CONTAINER_IMAGE:-nvcr.io/nvidia/pytorch:24.04-py3}"
    export NCCL_TESTS_PATH="${SKU_NCCL_TESTS_PATH:-/opt/nccl_tests/build}"
    export HPL_CONTAINER_IMAGE="${SKU_HPL_CONTAINER_IMAGE:-nvcr.io/nvidia/hpc-benchmarks:24.03}"
    export NEMO_CONTAINER_IMAGE="${SKU_NEMO_CONTAINER_IMAGE:-nvcr.io/nvidia/nemo:24.03.01}"
    export NCCL_IB_DEVICES="${SKU_IB_DEVICES:-mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_9,mlx5_10,mlx5_11}"
    export UCX_DEVICE="${SKU_UCX_DEVICE:-mlx5_0:1}"
}

###############################################################################
# Parse test definitions from YAML suite file
# Returns: test_name|command|timeout|pass_type|pattern_or_threshold|failure_class
###############################################################################
parse_tests() {
    local file="$1"
    python3 -c "
import yaml, sys, json
with open('${file}') as f:
    suite = yaml.safe_load(f)
for t in suite.get('tests', []):
    pc = t.get('pass_criteria', {})
    name = t['name']
    cmd = t['command']
    timeout = t.get('timeout_seconds', 300)
    ptype = pc.get('type', 'exit_code')
    pattern = pc.get('pattern', pc.get('expected', pc.get('threshold_key', pc.get('threshold', ''))))
    fclass = t.get('failure_class', 'software')
    layer = t.get('layer', 0)
    print(f'{name}|{cmd}|{timeout}|{ptype}|{pattern}|{fclass}|{layer}')
" 2>/dev/null
}

###############################################################################
# Execute a single test on a node via cmsh
###############################################################################
run_single_test() {
    local name="$1" command="$2" timeout="$3" node="$4" output_file="$5"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "DRY_RUN: Would run '${command}' on ${node} (timeout: ${timeout}s)"
        echo '{"status":"dry_run","output":"simulated pass"}' > "$output_file"
        return 0
    fi

    # Execute via cmsh on the remote node
    local start_ts
    start_ts=$(date +%s)

    timeout "${timeout}" \
        ${CMSH_BIN} -c "device; use ${node}; exec '${command}'" \
        > "$output_file" 2>&1
    local rc=$?

    local end_ts duration
    end_ts=$(date +%s)
    duration=$((end_ts - start_ts))

    # Append metadata to output
    echo "" >> "$output_file"
    echo "--- FLEET-VALIDATOR-META ---" >> "$output_file"
    echo "exit_code=${rc}" >> "$output_file"
    echo "duration_seconds=${duration}" >> "$output_file"
    echo "node=${node}" >> "$output_file"
    echo "test=${name}" >> "$output_file"
    echo "timestamp=$(date -Iseconds)" >> "$output_file"

    return $rc
}

###############################################################################
# Evaluate pass criteria against test output
###############################################################################
evaluate_criteria() {
    local output_file="$1" pass_type="$2" pattern="$3"

    case "$pass_type" in
        grep_absent)
            ! grep -qi "$pattern" "$output_file"
            ;;
        grep_present)
            grep -qi "$pattern" "$output_file"
            ;;
        output_equals)
            local output
            output=$(head -1 "$output_file" | tr -d '[:space:]')
            [[ "$output" == "$pattern" ]]
            ;;
        field_equals)
            local value
            value=$(grep -oP "$pattern" "$output_file" | head -1 | grep -oP '\d+' | head -1)
            [[ "${value:-999}" == "0" ]]
            ;;
        exit_code)
            # Already handled by command return code
            return 0
            ;;
        all_values_below)
            local max_val
            max_val=$(grep -oP '\d+' "$output_file" | sort -n | tail -1)
            [[ "${max_val:-0}" -lt "${pattern}" ]]
            ;;
        value_gte)
            local val
            val=$(cat "$output_file" | tr -d '[:space:]')
            [[ "${val:-0}" -ge "${pattern}" ]]
            ;;
        bandwidth_gte)
            # Extract bus bandwidth from NCCL output (last data line, second-to-last col)
            local threshold_var="SKU_${pattern^^}"
            local threshold="${!threshold_var:-0}"
            local peak_bw
            peak_bw=$(grep -E '^\s+[0-9]' "$output_file" | tail -1 | awk '{print $(NF-1)}' | cut -d. -f1)
            [[ "${peak_bw:-0}" -ge "${threshold}" ]]
            ;;
        performance_gte)
            local threshold_var="SKU_${pattern^^}"
            local threshold="${!threshold_var:-0}"
            local perf
            perf=$(grep -E '^W' "$output_file" | tail -1 | awk '{print $NF}' | cut -d. -f1)
            [[ "${perf:-0}" -ge "${threshold}" ]]
            ;;
        *)
            log_fail "Unknown pass criteria type: ${pass_type}"
            return 1
            ;;
    esac
}

###############################################################################
# Extract metric value from test output
###############################################################################
extract_metric() {
    local output_file="$1" metric_type="$2"

    case "$metric_type" in
        exit_code)
            grep "exit_code=" "$output_file" | cut -d= -f2
            ;;
        busbw)
            grep -E '^\s+[0-9]' "$output_file" | tail -1 | awk '{print $(NF-1)}'
            ;;
        max_value)
            grep -oP '\d+' "$output_file" | sort -n | tail -1
            ;;
        output_value)
            head -1 "$output_file" | tr -d '[:space:]'
            ;;
        gflops)
            grep -E '^W' "$output_file" | tail -1 | awk '{print $NF}'
            ;;
        *)
            echo "0"
            ;;
    esac
}

###############################################################################
# Main Execution Loop
###############################################################################
main() {
    load_sku_profile "$SKU_FILE"

    local suite_name
    suite_name=$(python3 -c "import yaml; print(yaml.safe_load(open('${SUITE_FILE}'))['name'])" 2>/dev/null || basename "$SUITE_FILE" .yml)

    log_info "Suite: ${suite_name} | Node: ${NODE} | SKU: $(basename "$SKU_FILE" .yml)"
    echo ""

    local total=0 passed=0 failed=0 skipped=0
    local failed_hw=0 failed_sw=0
    local results_json="[]"

    # Parse all tests
    while IFS='|' read -r name command timeout pass_type pattern failure_class layer; do
        total=$((total + 1))
        local test_output="${OUTPUT_DIR}/${name}.txt"

        log_info "[${total}] Running: ${name} (timeout: ${timeout}s, layer: ${layer})"

        # Run the test
        local test_rc=0
        if ! run_single_test "$name" "$command" "$timeout" "$NODE" "$test_output"; then
            test_rc=1
        fi

        # Evaluate pass criteria (even if command exited 0, criteria might fail)
        local criteria_met=true
        if [[ "$test_rc" -eq 0 ]] && [[ "$pass_type" != "exit_code" ]]; then
            if ! evaluate_criteria "$test_output" "$pass_type" "$pattern"; then
                criteria_met=false
                test_rc=1
            fi
        fi

        # Extract metrics
        local metric_value="0"
        # Simple extraction for common types
        if [[ -f "$test_output" ]]; then
            case "$pass_type" in
                bandwidth_gte) metric_value=$(extract_metric "$test_output" "busbw") ;;
                performance_gte) metric_value=$(extract_metric "$test_output" "gflops") ;;
                *) metric_value=$(extract_metric "$test_output" "exit_code") ;;
            esac
        fi

        # Record result
        if [[ "$test_rc" -eq 0 ]]; then
            passed=$((passed + 1))
            log_ok "  ✅ ${name} — PASSED (metric: ${metric_value:-N/A})"
        else
            failed=$((failed + 1))
            if [[ "$failure_class" == "hardware" ]]; then
                failed_hw=$((failed_hw + 1))
            else
                failed_sw=$((failed_sw + 1))
            fi
            log_fail "  ❌ ${name} — FAILED (class: ${failure_class})"
        fi

        # Build JSON result
        results_json=$(python3 -c "
import json, sys
results = json.loads('''${results_json}''')
results.append({
    'name': '${name}',
    'status': 'passed' if ${test_rc} == 0 else 'failed',
    'failure_class': '${failure_class}',
    'layer': ${layer},
    'metric_value': '${metric_value:-0}',
    'duration_seconds': 0
})
print(json.dumps(results))
" 2>/dev/null || echo "$results_json")

    done < <(parse_tests "$SUITE_FILE")

    # Write result JSON
    python3 -c "
import json
results = json.loads('''${results_json}''')
summary = {
    'node': '${NODE}',
    'suite': '${suite_name}',
    'sku': '$(basename "$SKU_FILE" .yml)',
    'timestamp': '$(date -Iseconds)',
    'total': ${total},
    'passed': ${passed},
    'failed': ${failed},
    'failed_hardware': ${failed_hw},
    'failed_software': ${failed_sw},
    'certified': ${failed} == 0,
    'failure_class': 'hardware' if ${failed_hw} > 0 else ('software' if ${failed_sw} > 0 else 'none'),
    'tests': results
}
with open('${OUTPUT_DIR}/result.json', 'w') as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
" 2>/dev/null

    # Summary
    echo ""
    log_info "═══ SUITE RESULTS: ${suite_name} on ${NODE} ═══"
    log_info "Total: ${total} | Passed: ${passed} | Failed: ${failed}"
    [[ $failed_hw -gt 0 ]] && log_fail "Hardware failures: ${failed_hw}"
    [[ $failed_sw -gt 0 ]] && log_fail "Software failures: ${failed_sw}"
    [[ $failed -eq 0 ]] && log_ok "NODE CERTIFIED ✅" || log_fail "NODE FAILED CERTIFICATION ❌"

    return $failed
}

main
