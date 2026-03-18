#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# BCM Process Metrics Collector — Prometheus-Style Output
#
# Collects per-process, per-core CPU metrics for contention analysis.
# Designed for Weka vs Slurm core contention monitoring.
#
# Output: Prometheus text exposition format on HTTP :9256/metrics
# Integration: BCM cmsh custom monitoring, Grafana dashboards
#
# Install on each compute node:
#   scp scripts/bcm-process-metrics.sh root@<node>:/opt/bcm/
#   # Start as systemd service or cron
#
# Usage:
#   ./bcm-process-metrics.sh                   # Print metrics once
#   ./bcm-process-metrics.sh --serve           # HTTP server on :9256
#   ./bcm-process-metrics.sh --output /tmp/m   # Write to file
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

HOSTNAME=$(hostname)
PORT=${METRICS_PORT:-9256}
OUTPUT_FILE=""
SERVE_MODE=false
WEKA_CORE_LIMIT=17

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --serve)       SERVE_MODE=true ;;
        --port)        shift; PORT=$1 ;;
        --output)      shift; OUTPUT_FILE=$1 ;;
        --weka-limit)  shift; WEKA_CORE_LIMIT=$1 ;;
        --help|-h)
            echo "BCM Process Metrics Collector — Prometheus-style"
            echo "  --serve         Start HTTP server on :9256"
            echo "  --port N        Set HTTP port (default: 9256)"
            echo "  --output FILE   Write metrics to file"
            echo "  --weka-limit N  Weka core limit alert (default: 17)"
            exit 0 ;;
    esac
    shift
done

# ─── Collect Process Metrics ────────────────────────────────────────
collect_metrics() {
    local ts
    ts=$(date +%s)
    local total_cores
    total_cores=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)

    cat <<EOF
# HELP bcm_node_info Node information
# TYPE bcm_node_info gauge
bcm_node_info{hostname="$HOSTNAME",cores="$total_cores"} 1

# HELP bcm_node_cpu_cores_total Total CPU cores on the node
# TYPE bcm_node_cpu_cores_total gauge
bcm_node_cpu_cores_total{hostname="$HOSTNAME"} $total_cores

EOF

    # ─── Per-Process CPU Usage ───────────────────────────────────────
    echo "# HELP bcm_process_cpu_percent CPU usage percentage per process"
    echo "# TYPE bcm_process_cpu_percent gauge"
    echo "# HELP bcm_process_mem_percent Memory usage percentage per process"
    echo "# TYPE bcm_process_mem_percent gauge"
    echo "# HELP bcm_process_rss_bytes Resident set size in bytes per process"
    echo "# TYPE bcm_process_rss_bytes gauge"
    echo "# HELP bcm_process_threads Thread count per process"
    echo "# TYPE bcm_process_threads gauge"
    echo "# HELP bcm_process_cpu_cores_used Estimated core count used by process"
    echo "# TYPE bcm_process_cpu_cores_used gauge"

    # Collect all processes with >0.0% CPU — including which core they're on
    ps -eo pid,comm,%cpu,%mem,rss,nlwp,psr --sort=-%cpu --no-headers 2>/dev/null | \
    while read -r pid comm cpu mem rss threads core_id; do
        # Skip idle/zero processes
        if (( $(echo "$cpu > 0.0" | bc -l 2>/dev/null || echo 0) )); then
            # Classify process — NO "other" bucket, use actual process name
            local svc_class="$comm"
            case "$comm" in
                weka*|WekaIO*|weka_*)           svc_class="weka" ;;
                slurm*|srun|slurmstepd|sbatch)  svc_class="slurm" ;;
                nvsm*|nvidia*|dcgm*|nv-*)       svc_class="nvidia" ;;
                cmd|cmsh|cmjob|cmguiservlet)    svc_class="bcm" ;;
                python*|java|node)               svc_class="app" ;;
                ssh*|rsyslog*|systemd*|journald) svc_class="system" ;;
                mysqld|mariadbd)                 svc_class="mysql" ;;
                dhcpd)                           svc_class="dhcp" ;;
                atftpd|in.tftpd|tftpd)          svc_class="tftp" ;;
                nfsd|rpc.mountd|rpcbind|rpc.statd) svc_class="nfs" ;;
                cron|crond|atd)                  svc_class="cron" ;;
                mongod|postgres|redis*)          svc_class="database" ;;
                kworker*|ksoftirqd*|kswapd*|khugepaged|rcu_*|cpuhp*|migration*|watchdog*|kthreadd|irq*|scsi*|blkmapd|kdevtmpfs|netns|writeback|idle_inject*|kcompactd*|khungtaskd|oom_reaper|xfsaild*|ecryptfs*|pool_workqueue*|jfs*|NFSv4*|lockd|kauditd|hwrng) svc_class="kernel" ;;
            esac

            local cores_used
            cores_used=$(echo "scale=2; $cpu / 100" | bc 2>/dev/null || echo "0")
            local rss_bytes=$((rss * 1024))

            echo "bcm_process_cpu_percent{hostname=\"$HOSTNAME\",pid=\"$pid\",process=\"$comm\",service=\"$svc_class\"} $cpu"
            echo "bcm_process_mem_percent{hostname=\"$HOSTNAME\",pid=\"$pid\",process=\"$comm\",service=\"$svc_class\"} $mem"
            echo "bcm_process_rss_bytes{hostname=\"$HOSTNAME\",pid=\"$pid\",process=\"$comm\",service=\"$svc_class\"} $rss_bytes"
            echo "bcm_process_threads{hostname=\"$HOSTNAME\",pid=\"$pid\",process=\"$comm\",service=\"$svc_class\"} $threads"
            echo "bcm_process_cpu_cores_used{hostname=\"$HOSTNAME\",pid=\"$pid\",process=\"$comm\",service=\"$svc_class\"} $cores_used"
            echo "bcm_process_core_id{hostname=\"$HOSTNAME\",pid=\"$pid\",process=\"$comm\",service=\"$svc_class\"} ${core_id:-0}"
        fi
    done

    # ─── Process-to-Core Mapping (ALL processes, not just active) ─────
    echo ""
    echo "# HELP bcm_process_core_map Process to CPU core mapping (value=CPU%, label=core)"
    echo "# TYPE bcm_process_core_map gauge"
    echo "# HELP bcm_core_process_count Number of processes currently on each core"
    echo "# TYPE bcm_core_process_count gauge"

    # Get all non-kernel processes and their assigned core
    ps -eo pid,comm,%cpu,psr --no-headers 2>/dev/null | \
    awk -v hn="$HOSTNAME" '
    {
        pid=$1; comm=$2; cpu=$3; core=$4
        # Skip kernel threads for the mapping view
        if (comm ~ /^kworker/ || comm ~ /^ksoftirqd/ || comm ~ /^kswapd/ || \
            comm ~ /^rcu_/ || comm ~ /^cpuhp/ || comm ~ /^migration/ || \
            comm ~ /^watchdog/ || comm ~ /^idle_inject/ || comm ~ /^irq/) next
        # Only show processes with cpu > 0
        if (cpu + 0 > 0) {
            printf "bcm_process_core_map{hostname=\"%s\",pid=\"%s\",process=\"%s\",core=\"%s\"} %s\n", hn, pid, comm, core, cpu
        }
        # Count processes per core (all processes, not just active)
        core_count[core]++
    }
    END {
        for (c in core_count) {
            printf "bcm_core_process_count{hostname=\"%s\",core=\"%s\"} %d\n", hn, c, core_count[c]
        }
    }
    '

    # ─── Per-Core Usage ──────────────────────────────────────────────
    echo ""
    echo "# HELP bcm_cpu_core_usage_percent Usage per CPU core (user+system)"
    echo "# TYPE bcm_cpu_core_usage_percent gauge"

    # Snapshot /proc/stat, wait 1s, snapshot again, diff per-core
    local tmpA="/tmp/.bcm_stat_a.$$" tmpB="/tmp/.bcm_stat_b.$$"
    grep "^cpu[0-9]" /proc/stat > "$tmpA"
    sleep 1
    grep "^cpu[0-9]" /proc/stat > "$tmpB"

    awk '
        NR==FNR {
            split($0, a, " ")
            core = a[1]
            idle_a[core] = a[5] + a[6]
            total_a[core] = a[2] + a[3] + a[4] + a[5] + a[6] + a[7] + a[8]
            next
        }
        {
            split($0, b, " ")
            core = b[1]
            idle_b = b[5] + b[6]
            total_b = b[2] + b[3] + b[4] + b[5] + b[6] + b[7] + b[8]
            diff_idle = idle_b - idle_a[core]
            diff_total = total_b - total_a[core]
            if (diff_total > 0)
                usage = (1 - diff_idle / diff_total) * 100
            else
                usage = 0
            core_num = substr(core, 4)
            printf "bcm_cpu_core_usage_percent{hostname=\"'"$HOSTNAME"'\",core=\"%s\"} %.1f\n", core_num, usage
        }
    ' "$tmpA" "$tmpB"
    rm -f "$tmpA" "$tmpB"

    # ─── Per-Process-Name Aggregates (no "other" bucket) ──────────────
    echo ""
    echo "# HELP bcm_service_cpu_cores_total Total CPU cores used by service/process"
    echo "# TYPE bcm_service_cpu_cores_total gauge"
    echo "# HELP bcm_service_process_count Number of instances per service/process"
    echo "# TYPE bcm_service_process_count gauge"

    # Aggregate CPU by ACTUAL process name — every process gets its own metric line
    ps -eo comm,%cpu --no-headers 2>/dev/null | awk -v hn="$HOSTNAME" '
    {
        name = $1
        # Map known patterns to service names
        if (name ~ /^weka/) svc = "weka"
        else if (name ~ /^slurm/ || name == "srun" || name == "slurmstepd") svc = "slurm"
        else if (name ~ /^nvsm/ || name ~ /^nvidia/ || name ~ /^dcgm/) svc = "nvidia"
        else if (name == "cmd" || name == "cmsh" || name == "cmjob") svc = "bcm"
        else if (name ~ /^python/ || name == "java") svc = "app"
        else if (name ~ /^ssh/ || name ~ /^rsyslog/ || name ~ /^systemd/ || name == "journald") svc = "system"
        else if (name == "mysqld" || name == "mariadbd") svc = "mysql"
        else if (name == "dhcpd") svc = "dhcp"
        else if (name ~ /tftpd/) svc = "tftp"
        else if (name ~ /^nfsd/ || name ~ /^rpc/) svc = "nfs"
        else if (name ~ /^cron/ || name == "atd") svc = "cron"
        else if (name ~ /^kworker/ || name ~ /^ksoftirqd/ || name ~ /^kswapd/ || name == "khugepaged" || name ~ /^rcu_/ || name ~ /^cpuhp/ || name ~ /^migration/ || name ~ /^watchdog/ || name == "kthreadd" || name ~ /^irq/ || name ~ /^scsi/ || name == "blkmapd" || name == "kdevtmpfs" || name == "netns" || name == "writeback" || name ~ /^idle_inject/ || name ~ /^kcompactd/ || name == "khungtaskd" || name == "oom_reaper" || name ~ /^xfsaild/ || name ~ /^ecryptfs/ || name ~ /^pool_workqueue/ || name ~ /^jfs/ || name ~ /^NFSv4/ || name == "lockd" || name == "kauditd" || name == "hwrng") svc = "kernel"
        else svc = name  # USE ACTUAL PROCESS NAME

        cpu_total[svc] += $2
        proc_count[svc]++
    }
    END {
        for (svc in cpu_total) {
            printf "bcm_service_cpu_cores_total{hostname=\"%s\",service=\"%s\"} %.2f\n", hn, svc, cpu_total[svc]/100
            printf "bcm_service_process_count{hostname=\"%s\",service=\"%s\"} %d\n", hn, svc, proc_count[svc]
        }
    }
    '

    # ─── Weka Core Contention Alert ──────────────────────────────────
    echo ""
    echo "# HELP bcm_weka_core_limit_exceeded 1 if Weka exceeds core limit"
    echo "# TYPE bcm_weka_core_limit_exceeded gauge"
    echo "# HELP bcm_weka_core_limit Configured Weka core limit"
    echo "# TYPE bcm_weka_core_limit gauge"

    local weka_cores
    weka_cores=$(ps -eo comm,%cpu --no-headers 2>/dev/null | awk '
        /^weka/ { total += $2 }
        END { printf "%.2f", total/100 }
    ')
    local exceeded=0
    if (( $(echo "$weka_cores > $WEKA_CORE_LIMIT" | bc -l 2>/dev/null || echo 0) )); then
        exceeded=1
    fi
    echo "bcm_weka_core_limit_exceeded{hostname=\"$HOSTNAME\"} $exceeded"
    echo "bcm_weka_core_limit{hostname=\"$HOSTNAME\"} $WEKA_CORE_LIMIT"

    # ─── Contention Score ────────────────────────────────────────────
    echo ""
    echo "# HELP bcm_cpu_contention_score CPU contention score (0=none, 1=heavy)"
    echo "# TYPE bcm_cpu_contention_score gauge"

    local total_cpu_used
    total_cpu_used=$(ps -eo %cpu --no-headers 2>/dev/null | awk '{s+=$1}END{printf "%.2f",s/100}')
    local contention
    contention=$(echo "scale=2; $total_cpu_used / $total_cores" | bc 2>/dev/null || echo "0")
    echo "bcm_cpu_contention_score{hostname=\"$HOSTNAME\"} $contention"

    echo ""
    echo "# HELP bcm_metrics_timestamp_seconds Unix timestamp of collection"
    echo "# TYPE bcm_metrics_timestamp_seconds gauge"
    echo "bcm_metrics_timestamp_seconds{hostname=\"$HOSTNAME\"} $ts"
}

# ─── HTTP Server Mode ────────────────────────────────────────────────
serve_metrics() {
    echo "Starting metrics server on :$PORT/metrics"
    echo "Prometheus scrape: http://$HOSTNAME:$PORT/metrics"

    while true; do
        local metrics
        metrics=$(collect_metrics)
        local response
        response="HTTP/1.1 200 OK\r\nContent-Type: text/plain; version=0.0.4\r\nContent-Length: ${#metrics}\r\n\r\n$metrics"

        echo -e "$response" | nc -l -p "$PORT" -q 1 2>/dev/null || \
        echo -e "$response" | ncat -l -p "$PORT" --send-only 2>/dev/null || \
        {
            # Fallback: write to file for Prometheus node_exporter textfile collector
            echo "$metrics" > /var/lib/prometheus/node-exporter/bcm_process_metrics.prom
            sleep 15
        }
    done
}

# ─── Main ────────────────────────────────────────────────────────────
if $SERVE_MODE; then
    serve_metrics
elif [[ -n "$OUTPUT_FILE" ]]; then
    collect_metrics > "$OUTPUT_FILE"
    echo "Metrics written to $OUTPUT_FILE"
else
    collect_metrics
fi
