#!/usr/bin/env bash
###############################################################################
# collect-metrics.sh — Push test results to Prometheus Pushgateway
###############################################################################
# Reads test results from the log directory and pushes metrics to Prometheus.
#
# Usage:
#   collect-metrics.sh --run-id <id> --suite <name> --total <n>
#                      --passed <n> --failed <n> --pushgateway <url>
#                      --log-dir <dir>
###############################################################################
set -euo pipefail

RUN_ID=""
SUITE=""
TOTAL=0
PASSED=0
FAILED=0
PUSHGATEWAY_URL="http://localhost:9091"
LOG_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --run-id)      RUN_ID="$2";          shift 2 ;;
        --suite)       SUITE="$2";           shift 2 ;;
        --total)       TOTAL="$2";           shift 2 ;;
        --passed)      PASSED="$2";          shift 2 ;;
        --failed)      FAILED="$2";          shift 2 ;;
        --pushgateway) PUSHGATEWAY_URL="$2"; shift 2 ;;
        --log-dir)     LOG_DIR="$2";         shift 2 ;;
        *) shift ;;
    esac
done

TIMESTAMP=$(date +%s)

###############################################################################
# Push fleet-level metrics
###############################################################################
push_fleet_metrics() {
    cat <<EOF | curl -s --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/fleet_validator/suite/${SUITE}" 2>/dev/null
# HELP fleet_cert_nodes_total Total nodes tested in this run
# TYPE fleet_cert_nodes_total gauge
fleet_cert_nodes_total{suite="${SUITE}",run_id="${RUN_ID}"} ${TOTAL}

# HELP fleet_cert_nodes_passed Nodes that passed certification
# TYPE fleet_cert_nodes_passed gauge
fleet_cert_nodes_passed{suite="${SUITE}",run_id="${RUN_ID}"} ${PASSED}

# HELP fleet_cert_nodes_failed Nodes that failed certification
# TYPE fleet_cert_nodes_failed gauge
fleet_cert_nodes_failed{suite="${SUITE}",run_id="${RUN_ID}"} ${FAILED}

# HELP fleet_cert_pass_rate Certification pass rate (0-100)
# TYPE fleet_cert_pass_rate gauge
fleet_cert_pass_rate{suite="${SUITE}",run_id="${RUN_ID}"} $(( TOTAL > 0 ? (PASSED * 100 / TOTAL) : 0 ))

# HELP fleet_cert_last_run_timestamp Unix timestamp of last certification run
# TYPE fleet_cert_last_run_timestamp gauge
fleet_cert_last_run_timestamp{suite="${SUITE}"} ${TIMESTAMP}

# HELP fleet_cert_last_run_duration_seconds Duration of last certification run
# TYPE fleet_cert_last_run_duration_seconds gauge
fleet_cert_last_run_duration_seconds{suite="${SUITE}",run_id="${RUN_ID}"} 0
EOF
}

###############################################################################
# Push per-node test results
###############################################################################
push_node_metrics() {
    [[ -z "$LOG_DIR" ]] && return

    for node_dir in "${LOG_DIR}"/*/; do
        [[ -d "$node_dir" ]] || continue
        local node
        node=$(basename "$node_dir")

        # Look for result.json in the latest run
        local result_file
        result_file=$(find "$node_dir" -name "result.json" -type f 2>/dev/null | sort -r | head -1)
        [[ -z "$result_file" ]] && continue

        # Parse results and push per-test metrics
        python3 -c "
import json, sys
with open('${result_file}') as f:
    data = json.load(f)

node = data['node']
suite = data['suite']
metrics = []

# Per-test metrics
for test in data.get('tests', []):
    name = test['name']
    status = 1 if test['status'] == 'passed' else 0
    value = test.get('metric_value', '0')

    metrics.append(f'fleet_cert_test_passed{{node=\"{node}\",test=\"{name}\",suite=\"{suite}\"}} {status}')

    try:
        float(value)
        metrics.append(f'fleet_cert_test_metric{{node=\"{node}\",test=\"{name}\",suite=\"{suite}\"}} {value}')
    except (ValueError, TypeError):
        pass

# Node-level certification metric
certified = 1 if data.get('certified', False) else 0
metrics.append(f'fleet_cert_node_certified{{node=\"{node}\",suite=\"{suite}\"}} {certified}')

# Node state
state = data.get('failure_class', 'none')
state_val = {'none': 0, 'software': 1, 'hardware': 2}.get(state, -1)
metrics.append(f'fleet_cert_node_failure_class{{node=\"{node}\",suite=\"{suite}\"}} {state_val}')

# Last certified timestamp
metrics.append(f'fleet_cert_last_certified_timestamp{{node=\"{node}\"}} $(date +%s)')

print('\n'.join(metrics))
" 2>/dev/null | curl -s --data-binary @- \
            "${PUSHGATEWAY_URL}/metrics/job/fleet_validator/node/${node}" 2>/dev/null || true
    done
}

###############################################################################
# Main
###############################################################################
echo "[$(date -Iseconds)] [METRICS] Pushing fleet metrics to ${PUSHGATEWAY_URL}..."
push_fleet_metrics && echo "[$(date -Iseconds)] [METRICS] Fleet metrics pushed" || true

echo "[$(date -Iseconds)] [METRICS] Pushing per-node metrics..."
push_node_metrics && echo "[$(date -Iseconds)] [METRICS] Node metrics pushed" || true

echo "[$(date -Iseconds)] [METRICS] Done"
