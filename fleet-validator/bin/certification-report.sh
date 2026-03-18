#!/usr/bin/env bash
###############################################################################
# certification-report.sh — Generate JSON certification record
###############################################################################
# Creates a timestamped certification record for each node.
# Records are stored in /var/lib/fleet-validator/certifications/
#
# Usage:
#   certification-report.sh --node <name> --suite <name> --status <CERTIFIED|FAILED:reason>
#                           --log-dir <dir> --output-dir <dir>
###############################################################################
set -euo pipefail

NODE=""
SUITE=""
STATUS=""
LOG_DIR=""
OUTPUT_DIR="/var/lib/fleet-validator/certifications"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --node)       NODE="$2";       shift 2 ;;
        --suite)      SUITE="$2";      shift 2 ;;
        --status)     STATUS="$2";     shift 2 ;;
        --log-dir)    LOG_DIR="$2";    shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        *) shift ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date -Iseconds)
TIMESTAMP_EPOCH=$(date +%s)
CERT_FILE="${OUTPUT_DIR}/${NODE}-${TIMESTAMP_EPOCH}.json"

###############################################################################
# Build certification record
###############################################################################
generate_record() {
    local result_json="${LOG_DIR}/result.json"
    local certified="false"
    local tests_passed=0 tests_failed=0 tests_total=0
    local failure_class="none"
    local failed_tests="[]"

    if [[ -f "$result_json" ]]; then
        tests_passed=$(python3 -c "import json; d=json.load(open('${result_json}')); print(d.get('passed',0))" 2>/dev/null || echo 0)
        tests_failed=$(python3 -c "import json; d=json.load(open('${result_json}')); print(d.get('failed',0))" 2>/dev/null || echo 0)
        tests_total=$(python3 -c "import json; d=json.load(open('${result_json}')); print(d.get('total',0))" 2>/dev/null || echo 0)
        failure_class=$(python3 -c "import json; d=json.load(open('${result_json}')); print(d.get('failure_class','none'))" 2>/dev/null || echo "none")
        failed_tests=$(python3 -c "
import json
d = json.load(open('${result_json}'))
failed = [t['name'] for t in d.get('tests', []) if t.get('status') == 'failed']
print(json.dumps(failed))
" 2>/dev/null || echo "[]")
    fi

    if [[ "$STATUS" == "CERTIFIED" ]]; then
        certified="true"
    fi

    cat <<EOF
{
  "node": "${NODE}",
  "timestamp_utc": "${TIMESTAMP}",
  "timestamp_epoch": ${TIMESTAMP_EPOCH},
  "suite": "${SUITE}",
  "status": "${STATUS}",
  "certified": ${certified},
  "tests_total": ${tests_total},
  "tests_passed": ${tests_passed},
  "tests_failed": ${tests_failed},
  "failure_class": "${failure_class}",
  "failed_tests": ${failed_tests},
  "operator": "fleet-validator",
  "version": "1.0.0"
}
EOF
}

# Write record
RECORD=$(generate_record)
echo "$RECORD" > "$CERT_FILE"

# Also update the "latest" symlink for easy access
echo "$RECORD" > "${OUTPUT_DIR}/${NODE}-latest.json"

# Log
echo "[$(date -Iseconds)] [CERT] ${STATUS}: ${NODE} → ${CERT_FILE}"

# Print record to stdout
echo "$RECORD"
