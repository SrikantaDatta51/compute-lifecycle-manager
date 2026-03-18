#!/usr/bin/env bash
###############################################################################
# node-state-manager.sh — BCM Node State Management
###############################################################################
# Manages node state transitions via BCM cmsh. Handles:
#   - State transitions (healthy ↔ testing ↔ maintenance/rma)
#   - Debug bundle collection for failed nodes
#   - Alert generation for state changes
#
# Usage:
#   node-state-manager.sh transition <node> <target_state> <trigger>
#   node-state-manager.sh get-state <node>
#   node-state-manager.sh collect-debug <node> <output_dir>
###############################################################################
set -euo pipefail

CMSH_BIN="${CMSH_BIN:-/usr/bin/cmsh}"
STATE_DIR="/var/lib/fleet-validator/states"
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'
YELLOW='\033[0;33m'; NC='\033[0m'

log_info()  { echo -e "${BLUE}[$(date -Iseconds)] [STATE]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[$(date -Iseconds)] [STATE]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[$(date -Iseconds)] [STATE]${NC}  $*"; }
log_error() { echo -e "${RED}[$(date -Iseconds)] [STATE]${NC}  $*"; }

mkdir -p "$STATE_DIR"

###############################################################################
# Get current node state from local state file
###############################################################################
get_state() {
    local node="$1"
    local state_file="${STATE_DIR}/${node}.state"

    if [[ -f "$state_file" ]]; then
        cat "$state_file"
    else
        echo "unknown"
    fi
}

###############################################################################
# Set node state locally and in BCM
###############################################################################
set_state() {
    local node="$1" new_state="$2" trigger="$3"
    local old_state
    old_state=$(get_state "$node")
    local timestamp
    timestamp=$(date -Iseconds)

    log_info "State transition: ${node}: ${old_state} → ${new_state} (trigger: ${trigger})"

    # Write local state
    echo "$new_state" > "${STATE_DIR}/${node}.state"

    # Write state history
    echo "${timestamp}|${old_state}|${new_state}|${trigger}" >> "${STATE_DIR}/${node}.history"

    # Execute BCM commands based on target state
    case "$new_state" in
        testing)
            log_info "BCM: Setting ${node} to testing mode"
            ${CMSH_BIN} -c "device; use ${node}; set notes 'fleet-validator: testing since ${timestamp}'; commit" 2>/dev/null || true
            ;;

        healthy)
            log_info "BCM: Restoring ${node} to healthy/UP"
            ${CMSH_BIN} -c "device; use ${node}; set notes 'fleet-validator: certified ${timestamp}'; commit" 2>/dev/null || true
            ;;

        maintenance)
            log_warn "BCM: Draining ${node} for maintenance"
            ${CMSH_BIN} -c "device; use ${node}; set status DRAINED; commit" 2>/dev/null || true

            # If Slurm is available, drain the node
            if command -v scontrol &>/dev/null; then
                scontrol update NodeName="${node}" State=DRAIN Reason="fleet-validator:software-issue:${trigger}" 2>/dev/null || true
            fi

            # Set BCM notes
            ${CMSH_BIN} -c "device; use ${node}; set notes 'fleet-validator: MAINTENANCE since ${timestamp} - trigger: ${trigger}'; commit" 2>/dev/null || true

            # Send alert
            send_alert "$node" "maintenance" "$trigger" "warning"
            ;;

        rma)
            log_error "BCM: Draining ${node} for RMA — hardware failure"
            ${CMSH_BIN} -c "device; use ${node}; set status DRAINED; commit" 2>/dev/null || true

            # If Slurm is available, drain the node
            if command -v scontrol &>/dev/null; then
                scontrol update NodeName="${node}" State=DRAIN Reason="fleet-validator:hardware-failure:rma-required:${trigger}" 2>/dev/null || true
            fi

            # Set BCM notes
            ${CMSH_BIN} -c "device; use ${node}; set notes 'fleet-validator: RMA since ${timestamp} - trigger: ${trigger}'; commit" 2>/dev/null || true

            # Send critical alert
            send_alert "$node" "rma" "$trigger" "critical"
            ;;

        *)
            log_error "Unknown state: ${new_state}"
            return 1
            ;;
    esac

    log_ok "State transition complete: ${node} → ${new_state}"
}

###############################################################################
# Send alert via webhook or log
###############################################################################
send_alert() {
    local node="$1" state="$2" trigger="$3" severity="$4"
    local timestamp
    timestamp=$(date -Iseconds)

    local alert_message="[FLEET-VALIDATOR] Node ${node} → ${state^^} | Trigger: ${trigger} | Severity: ${severity} | Time: ${timestamp}"

    # Log the alert
    log_warn "ALERT: ${alert_message}"

    # Write alert to file (always)
    local alert_file="${STATE_DIR}/alerts.log"
    echo "${timestamp}|${node}|${state}|${trigger}|${severity}" >> "$alert_file"

    # Push to Prometheus Alertmanager via webhook if configured
    if [[ -n "$ALERT_WEBHOOK" ]]; then
        curl -s -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{
                \"status\": \"firing\",
                \"labels\": {
                    \"alertname\": \"FleetValidation${state^}Node\",
                    \"node\": \"${node}\",
                    \"severity\": \"${severity}\",
                    \"trigger\": \"${trigger}\"
                },
                \"annotations\": {
                    \"summary\": \"Node ${node} moved to ${state}\",
                    \"description\": \"${alert_message}\"
                }
            }" 2>/dev/null || log_warn "Alert webhook push failed (non-fatal)"
    fi

    # Push metric for alerting
    if [[ -n "${PUSHGATEWAY_URL:-}" ]]; then
        cat <<EOF | curl -s --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/fleet_validator/node/${node}" 2>/dev/null || true
# TYPE fleet_cert_alert gauge
fleet_cert_alert{node="${node}",state="${state}",severity="${severity}",trigger="${trigger}"} 1
EOF
    fi
}

###############################################################################
# Collect debug bundle for a failed node
###############################################################################
collect_debug() {
    local node="$1" output_dir="$2"
    mkdir -p "$output_dir"

    log_info "Collecting debug bundle for ${node}..."

    # GPU diagnostics
    ${CMSH_BIN} -c "device; use ${node}; exec 'nvidia-smi -q'" \
        > "${output_dir}/nvidia-smi-q.txt" 2>&1 || true

    # DCGM health
    ${CMSH_BIN} -c "device; use ${node}; exec 'dcgmi health -c -j'" \
        > "${output_dir}/dcgmi-health.json" 2>&1 || true

    # NVLink status
    ${CMSH_BIN} -c "device; use ${node}; exec 'nvidia-smi nvlink --status'" \
        > "${output_dir}/nvlink-status.txt" 2>&1 || true

    # NVLink errors
    ${CMSH_BIN} -c "device; use ${node}; exec 'nvidia-smi nvlink -e'" \
        > "${output_dir}/nvlink-errors.txt" 2>&1 || true

    # ECC errors
    ${CMSH_BIN} -c "device; use ${node}; exec 'nvidia-smi -q -d ECC'" \
        > "${output_dir}/ecc-errors.txt" 2>&1 || true

    # IB status
    ${CMSH_BIN} -c "device; use ${node}; exec 'ibstat'" \
        > "${output_dir}/ibstat.txt" 2>&1 || true

    # System logs
    ${CMSH_BIN} -c "device; use ${node}; exec 'dmesg --time-format iso | tail -500'" \
        > "${output_dir}/dmesg.txt" 2>&1 || true

    # IPMI SEL
    ${CMSH_BIN} -c "device; use ${node}; exec 'ipmitool sel elist'" \
        > "${output_dir}/ipmi-sel.txt" 2>&1 || true

    # Xid errors
    ${CMSH_BIN} -c "device; use ${node}; exec 'dmesg | grep -i xid'" \
        > "${output_dir}/xid-errors.txt" 2>&1 || true

    # PCIe errors
    ${CMSH_BIN} -c "device; use ${node}; exec 'dmesg | grep -i \"AER\\|pcie\\|error\"'" \
        > "${output_dir}/pcie-errors.txt" 2>&1 || true

    log_ok "Debug bundle collected: ${output_dir}"
}

###############################################################################
# Show state summary for all nodes
###############################################################################
show_summary() {
    echo ""
    echo "═══ FLEET NODE STATE SUMMARY ═══"
    echo ""
    printf "%-30s %-15s %-25s\n" "NODE" "STATE" "LAST UPDATED"
    echo "────────────────────────────────────────────────────────────────────"

    for state_file in "${STATE_DIR}"/*.state; do
        [[ -f "$state_file" ]] || continue
        local node
        node=$(basename "$state_file" .state)
        local state
        state=$(cat "$state_file")
        local updated
        updated=$(stat -c '%y' "$state_file" 2>/dev/null | cut -d. -f1)

        local color="$NC"
        case "$state" in
            healthy)            color="$GREEN" ;;
            testing)            color="$BLUE" ;;
            maintenance)        color="$YELLOW" ;;
            rma)                color="$RED" ;;
        esac

        printf "%-30s ${color}%-15s${NC} %-25s\n" "$node" "$state" "${updated:-unknown}"
    done
    echo ""
}

###############################################################################
# Main dispatch
###############################################################################
case "${1:-help}" in
    transition)
        [[ $# -ge 4 ]] || { echo "Usage: $0 transition <node> <state> <trigger>"; exit 1; }
        set_state "$2" "$3" "$4"
        ;;
    get-state)
        [[ $# -ge 2 ]] || { echo "Usage: $0 get-state <node>"; exit 1; }
        get_state "$2"
        ;;
    collect-debug)
        [[ $# -ge 3 ]] || { echo "Usage: $0 collect-debug <node> <output_dir>"; exit 1; }
        collect_debug "$2" "$3"
        ;;
    summary)
        show_summary
        ;;
    *)
        echo "Usage: $0 {transition|get-state|collect-debug|summary}"
        echo ""
        echo "Commands:"
        echo "  transition <node> <state> <trigger>  — Change node state"
        echo "  get-state <node>                     — Get current state"
        echo "  collect-debug <node> <output_dir>    — Collect debug bundle"
        echo "  summary                              — Show all node states"
        exit 1
        ;;
esac
