#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# BCM cmsh Monitoring Setup — Process Metrics Integration
#
# Configures BCM's built-in monitoring framework to periodically
# run bcm-process-metrics.sh on compute nodes via cmsh healthchecks.
#
# BCM monitoring uses cmsh → monitoring → add → script
# Scripts are pushed to nodes and run on a configurable interval.
# Results are stored in BCM's monitoring database, queryable via cmsh.
#
# Usage:
#   ./scripts/setup-cmsh-monitoring.sh           # Configure on head node
#   ./scripts/setup-cmsh-monitoring.sh --remove  # Remove monitoring
#
# Prerequisites:
#   - Run on BCM head node
#   - bcm-process-metrics.sh must be in /cm/local/apps/cmd/scripts/monitoring/
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="/cm/local/apps/cmd/scripts/monitoring"
METRICS_SCRIPT="bcm-process-metrics.sh"
METRICS_OUTPUT="/var/spool/bcm-metrics"
CHECK_NAME="process-metrics"
INTERVAL=60  # seconds
REMOVE_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --remove)  REMOVE_MODE=true ;;
        --interval) shift; INTERVAL=$1 ;;
        --help|-h)
            echo "BCM cmsh Monitoring Setup"
            echo "  --remove     Remove the monitoring check"
            echo "  --interval N Set check interval in seconds (default: 60)"
            exit 0 ;;
    esac
    shift
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   BCM Process Metrics — cmsh Monitoring Integration     ║"
echo "╚══════════════════════════════════════════════════════════╝"

if $REMOVE_MODE; then
    echo "Removing monitoring check: $CHECK_NAME"
    cmsh -c "monitoring; remove $CHECK_NAME; commit" 2>/dev/null && echo "✓ Removed" || echo "Not found"
    exit 0
fi

# ─── Step 1: Deploy metrics script to BCM monitoring directory ───────
echo ""
echo "Step 1: Deploying metrics script..."
mkdir -p "$SCRIPT_DIR"
mkdir -p "$METRICS_OUTPUT"

# Copy the metrics script to BCM's monitoring directory
if [[ -f "$(dirname "$0")/$METRICS_SCRIPT" ]]; then
    cp "$(dirname "$0")/$METRICS_SCRIPT" "$SCRIPT_DIR/$METRICS_SCRIPT"
elif [[ -f "/root/$METRICS_SCRIPT" ]]; then
    cp "/root/$METRICS_SCRIPT" "$SCRIPT_DIR/$METRICS_SCRIPT"
else
    echo "ERROR: Cannot find $METRICS_SCRIPT"
    exit 1
fi
chmod +x "$SCRIPT_DIR/$METRICS_SCRIPT"
echo "  ✓ Deployed to $SCRIPT_DIR/$METRICS_SCRIPT"

# ─── Step 2: Create the wrapper for cmsh monitoring ──────────────────
echo ""
echo "Step 2: Creating monitoring wrapper..."

cat > "$SCRIPT_DIR/run-process-metrics.sh" << 'WRAPPER'
#!/bin/bash
# BCM cmsh monitoring wrapper — collects process metrics
# Output format: BCM monitoring expects exit code + stdout
# Exit 0 = healthy, Exit 1 = warning, Exit 2 = critical

METRICS_SCRIPT="/cm/local/apps/cmd/scripts/monitoring/bcm-process-metrics.sh"
OUTPUT_DIR="/var/spool/bcm-metrics"
PROM_DIR="/var/lib/prometheus/node-exporter"
HOSTNAME=$(hostname)
TIMESTAMP=$(date +%s)
WEKA_LIMIT=17

# Collect metrics
mkdir -p "$OUTPUT_DIR" "$PROM_DIR" 2>/dev/null

# Run the collector, output to both Prometheus textfile and BCM metrics dir
bash "$METRICS_SCRIPT" --output "$OUTPUT_DIR/metrics-${HOSTNAME}-latest.prom" 2>/dev/null

# Also write to node_exporter textfile collector dir if it exists
if [[ -d "$PROM_DIR" ]]; then
    cp "$OUTPUT_DIR/metrics-${HOSTNAME}-latest.prom" "$PROM_DIR/bcm_process_metrics.prom" 2>/dev/null
fi

# Calculate Weka core usage for health check result
WEKA_CORES=$(ps -eo comm,%cpu --no-headers 2>/dev/null | awk '
    /^weka/ { total += $2 }
    END { printf "%.1f", total/100 }
')

# Calculate contention score
TOTAL_CPU=$(ps -eo %cpu --no-headers 2>/dev/null | awk '{s+=$1}END{printf "%.1f",s/100}')
TOTAL_CORES=$(nproc 2>/dev/null || echo 1)
CONTENTION=$(echo "scale=2; $TOTAL_CPU / $TOTAL_CORES" | bc 2>/dev/null || echo "0")

# BCM health check output — printed to stdout for cmsh monitoring
echo "hostname=$HOSTNAME"
echo "weka_cores=$WEKA_CORES"
echo "weka_limit=$WEKA_LIMIT"
echo "total_cpu_cores_used=$TOTAL_CPU"
echo "total_cores=$TOTAL_CORES"
echo "contention_score=$CONTENTION"
echo "timestamp=$TIMESTAMP"
echo "metrics_file=$OUTPUT_DIR/metrics-${HOSTNAME}-latest.prom"

# Determine health status
if (( $(echo "$WEKA_CORES > $WEKA_LIMIT" | bc -l 2>/dev/null || echo 0) )); then
    echo "STATUS=CRITICAL: Weka using $WEKA_CORES cores (limit: $WEKA_LIMIT)"
    exit 2
elif (( $(echo "$CONTENTION > 0.9" | bc -l 2>/dev/null || echo 0) )); then
    echo "STATUS=WARNING: High CPU contention (score: $CONTENTION)"
    exit 1
else
    echo "STATUS=OK: Weka=$WEKA_CORES cores, Contention=$CONTENTION"
    exit 0
fi
WRAPPER

chmod +x "$SCRIPT_DIR/run-process-metrics.sh"
echo "  ✓ Created $SCRIPT_DIR/run-process-metrics.sh"

# ─── Step 3: Register with cmsh monitoring ───────────────────────────
echo ""
echo "Step 3: Registering with BCM monitoring..."

# cmsh monitoring setup
cmsh << CMSH_EOF 2>/dev/null || true
monitoring
add healthcheck $CHECK_NAME
set script $SCRIPT_DIR/run-process-metrics.sh
set interval $INTERVAL
set timeout 30
set description "Process metrics collector — CPU core contention, Weka limit monitoring"
commit
quit
CMSH_EOF

echo "  ✓ Registered health check: $CHECK_NAME (interval: ${INTERVAL}s)"

# ─── Step 4: Assign to node categories ───────────────────────────────
echo ""
echo "Step 4: Assigning to default category..."

cmsh << CMSH_EOF2 2>/dev/null || true
category
use default
monitoring
assign $CHECK_NAME
commit
quit
CMSH_EOF2

echo "  ✓ Assigned to 'default' category"

# ─── Step 5: Verify ─────────────────────────────────────────────────
echo ""
echo "Step 5: Verification..."
echo "  Monitoring checks:"
cmsh -c "monitoring; list" 2>/dev/null || echo "  (run manually: cmsh → monitoring → list)"
echo ""
echo "  Query results:"
echo "  cmsh -c 'monitoring; show $CHECK_NAME'"
echo "  cmsh -c 'device; use node001; monitoring; get $CHECK_NAME'"
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   ✓ BCM cmsh monitoring configured                     ║"
echo "║                                                         ║"
echo "║   Check: $CHECK_NAME                          ║"
echo "║   Interval: every ${INTERVAL}s                               ║"
echo "║   Script: run-process-metrics.sh                        ║"
echo "║   Prom output: /var/spool/bcm-metrics/                  ║"
echo "║                                                         ║"
echo "║   Query: cmsh -c 'monitoring; show $CHECK_NAME'║"
echo "╚══════════════════════════════════════════════════════════╝"
