#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# BCM Cluster Monitoring Script
# Collects process metrics, service health, and system stats
# from BCM head node and compute nodes.
#
# Usage:
#   ./scripts/bcm-monitor.sh                    # All checks
#   ./scripts/bcm-monitor.sh --services         # Services only
#   ./scripts/bcm-monitor.sh --nodes            # Node status only
#   ./scripts/bcm-monitor.sh --processes        # Process metrics only
#   ./scripts/bcm-monitor.sh --continuous       # Run every 30s
#   ./scripts/bcm-monitor.sh --json             # JSON output
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
JSON_MODE=false
CONTINUOUS=false
CHECK_SERVICES=true
CHECK_NODES=true
CHECK_PROCESSES=true
CHECK_SYSTEM=true
INTERVAL=30

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --services)   CHECK_NODES=false; CHECK_PROCESSES=false; CHECK_SYSTEM=false ;;
        --nodes)      CHECK_SERVICES=false; CHECK_PROCESSES=false; CHECK_SYSTEM=false ;;
        --processes)  CHECK_SERVICES=false; CHECK_NODES=false; CHECK_SYSTEM=false ;;
        --system)     CHECK_SERVICES=false; CHECK_NODES=false; CHECK_PROCESSES=false ;;
        --json)       JSON_MODE=true ;;
        --continuous) CONTINUOUS=true ;;
        --interval)   shift; INTERVAL=$1 ;;
        --help|-h)
            echo "BCM Cluster Monitor — collect process & service metrics"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo "  --services     Check BCM services only"
            echo "  --nodes        Check node status only"
            echo "  --processes    Check process metrics only"
            echo "  --system       Check system resources only"
            echo "  --json         Output as JSON"
            echo "  --continuous   Run every 30s"
            echo "  --interval N   Set interval (default: 30s)"
            exit 0 ;;
    esac
    shift
done

# ─── Helper Functions ────────────────────────────────────────────────
header() {
    if ! $JSON_MODE; then
        echo ""
        echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║${NC}  ${BOLD}$1${NC}"
        echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    fi
}

status_line() {
    local name=$1
    local status=$2
    local detail=${3:-""}
    if $JSON_MODE; then
        echo "    {\"name\": \"$name\", \"status\": \"$status\", \"detail\": \"$detail\"},"
    else
        if [[ "$status" == "OK" || "$status" == "UP" || "$status" == "active" || "$status" == "RUNNING" ]]; then
            echo -e "  ${GREEN}✓${NC} ${BOLD}$name${NC}: $status $detail"
        elif [[ "$status" == "DOWN" || "$status" == "FAIL" || "$status" == "inactive" || "$status" == "STOPPED" ]]; then
            echo -e "  ${RED}✗${NC} ${BOLD}$name${NC}: $status $detail"
        else
            echo -e "  ${YELLOW}●${NC} ${BOLD}$name${NC}: $status $detail"
        fi
    fi
}

# ─── BCM Services Check ─────────────────────────────────────────────
check_services() {
    header "BCM SERVICES — $(hostname)"

    # Core BCM Services
    local services=(cmd slurmctld slurmdbd nfs-server dhcpd)
    for svc in "${services[@]}"; do
        local state
        state=$(systemctl is-active "$svc" 2>/dev/null || echo "not-found")
        local pid=""
        if [[ "$state" == "active" ]]; then
            pid="(PID $(systemctl show "$svc" --property=MainPID --value 2>/dev/null))"
        fi
        status_line "$svc" "$state" "$pid"
    done

    # TFTP (not systemd managed)
    local tftp_pid
    tftp_pid=$(pgrep in.tftpd 2>/dev/null || echo "")
    if [[ -n "$tftp_pid" ]]; then
        status_line "tftpd" "RUNNING" "(PID $tftp_pid)"
    else
        status_line "tftpd" "STOPPED"
    fi

    # DHCP manual check (may not be systemd managed)
    local dhcp_pid
    dhcp_pid=$(pgrep dhcpd 2>/dev/null || echo "")
    if [[ -n "$dhcp_pid" ]]; then
        local dhcp_iface
        dhcp_iface=$(ps aux | grep "[d]hcpd" | grep -oP 'enp\w+' | head -1 || echo "unknown")
        status_line "dhcpd-manual" "RUNNING" "(PID $dhcp_pid, iface: $dhcp_iface)"
    fi

    # BCM Web UI
    local ui_port
    ui_port=$(ss -tln 2>/dev/null | grep ":8081 " || echo "")
    if [[ -n "$ui_port" ]]; then
        status_line "bcm-ui" "LISTENING" "(port 8081)"
    else
        status_line "bcm-ui" "NOT_LISTENING"
    fi

    # Firewall
    local fw_policy
    fw_policy=$(iptables -L INPUT -n 2>/dev/null | head -1 | awk '{print $NF}' || echo "unknown")
    if [[ "$fw_policy" == "ACCEPT)" ]]; then
        status_line "firewall" "ACCEPT" "(safe)"
    else
        status_line "firewall" "$fw_policy" "(may block nodes!)"
    fi
}

# ─── Process Metrics ─────────────────────────────────────────────────
check_processes() {
    header "PROCESS METRICS — Top BCM Processes"

    if ! $JSON_MODE; then
        printf "  ${BOLD}%-6s %-20s %8s %8s %8s  %-s${NC}\n" "PID" "PROCESS" "CPU%" "MEM%" "RSS(MB)" "COMMAND"
        echo "  ────── ──────────────────── ──────── ──────── ────────  ──────────"
    fi

    # Key BCM processes to monitor
    local procs=("cmd" "slurmctld" "slurmdbd" "dhcpd" "in.tftpd" "mysqld" "nfsd" "rpcbind" "sshd" "python3")

    for proc in "${procs[@]}"; do
        local pids
        pids=$(pgrep -x "$proc" 2>/dev/null | head -3 || echo "")
        for pid in $pids; do
            if [[ -n "$pid" && -d "/proc/$pid" ]]; then
                local cpu mem rss cmdline
                cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ')
                mem=$(ps -p "$pid" -o %mem= 2>/dev/null | tr -d ' ')
                rss=$(ps -p "$pid" -o rss= 2>/dev/null | tr -d ' ')
                rss_mb=$(echo "scale=1; ${rss:-0}/1024" | bc 2>/dev/null || echo "0")
                cmdline=$(ps -p "$pid" -o args= 2>/dev/null | cut -c1-50)

                if $JSON_MODE; then
                    echo "    {\"pid\": $pid, \"name\": \"$proc\", \"cpu\": $cpu, \"mem\": $mem, \"rss_mb\": $rss_mb},"
                else
                    printf "  %-6s %-20s %7s%% %7s%% %7sMB  %-s\n" \
                        "$pid" "$proc" "$cpu" "$mem" "$rss_mb" "$cmdline"
                fi
            fi
        done
    done

    # Thread counts for key processes
    if ! $JSON_MODE; then
        echo ""
        echo -e "  ${BOLD}Thread counts:${NC}"
        for proc in cmd slurmctld dhcpd; do
            local pid threads
            pid=$(pgrep -x "$proc" 2>/dev/null | head -1 || echo "")
            if [[ -n "$pid" ]]; then
                threads=$(ls /proc/$pid/task 2>/dev/null | wc -l)
                echo "    $proc (PID $pid): $threads threads"
            fi
        done
    fi
}

# ─── Node Status ─────────────────────────────────────────────────────
check_nodes() {
    header "NODE STATUS"

    # BCM device list
    local node_info
    node_info=$(cmsh -c "device list" 2>/dev/null || echo "cmsh unavailable")

    if ! $JSON_MODE; then
        echo -e "  ${BOLD}BCM Device Status:${NC}"
        echo "$node_info" | while IFS= read -r line; do
            if echo "$line" | grep -q "UP"; then
                echo -e "  ${GREEN}▲${NC} $line"
            elif echo "$line" | grep -q "DOWN"; then
                echo -e "  ${RED}▼${NC} $line"
            elif echo "$line" | grep -q "INSTALLING"; then
                echo -e "  ${YELLOW}◆${NC} $line"
            else
                echo "  $line"
            fi
        done
    else
        echo "$node_info"
    fi

    # Slurm node state
    echo ""
    if ! $JSON_MODE; then
        echo -e "  ${BOLD}Slurm Status:${NC}"
        sinfo 2>/dev/null | while IFS= read -r line; do
            echo "    $line"
        done

        echo ""
        echo -e "  ${BOLD}Slurm Queue:${NC}"
        local jobs
        jobs=$(squeue -l 2>/dev/null | tail -n +2 | wc -l)
        echo "    Running/pending jobs: $jobs"
    fi

    # Ping check
    echo ""
    if ! $JSON_MODE; then
        echo -e "  ${BOLD}Network Reachability:${NC}"
        for node_ip in 192.168.200.1 192.168.200.2 192.168.200.3; do
            if ping -c1 -W1 "$node_ip" &>/dev/null; then
                status_line "  $node_ip" "UP" "(reachable)"
            else
                status_line "  $node_ip" "DOWN" "(unreachable)"
            fi
        done
    fi
}

# ─── System Resources ───────────────────────────────────────────────
check_system() {
    header "SYSTEM RESOURCES — $(hostname)"

    # CPU
    local cpu_usage
    cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' 2>/dev/null || echo "N/A")
    local load
    load=$(cat /proc/loadavg | awk '{print $1, $2, $3}')
    status_line "CPU usage" "${cpu_usage}%" "load: $load"

    # Memory
    local mem_total mem_used mem_pct
    mem_total=$(free -m | awk '/Mem:/{print $2}')
    mem_used=$(free -m | awk '/Mem:/{print $3}')
    mem_pct=$(echo "scale=1; $mem_used * 100 / $mem_total" | bc 2>/dev/null || echo "N/A")
    if (( $(echo "$mem_pct > 90" | bc -l 2>/dev/null || echo 0) )); then
        status_line "Memory" "CRITICAL" "${mem_used}MB / ${mem_total}MB (${mem_pct}%)"
    elif (( $(echo "$mem_pct > 75" | bc -l 2>/dev/null || echo 0) )); then
        status_line "Memory" "WARNING" "${mem_used}MB / ${mem_total}MB (${mem_pct}%)"
    else
        status_line "Memory" "OK" "${mem_used}MB / ${mem_total}MB (${mem_pct}%)"
    fi

    # Disk
    if ! $JSON_MODE; then
        echo -e "  ${BOLD}Disk usage:${NC}"
        df -h / /cm 2>/dev/null | tail -n +2 | while IFS= read -r line; do
            local pct
            pct=$(echo "$line" | awk '{print $5}' | tr -d '%')
            if [[ "$pct" -gt 90 ]]; then
                echo -e "    ${RED}$line${NC}"
            elif [[ "$pct" -gt 75 ]]; then
                echo -e "    ${YELLOW}$line${NC}"
            else
                echo "    $line"
            fi
        done
    fi

    # NFS exports
    if ! $JSON_MODE; then
        echo -e "  ${BOLD}NFS exports:${NC}"
        exportfs -v 2>/dev/null | head -5 | while IFS= read -r line; do
            echo "    $line"
        done
    fi

    # DHCP leases
    local lease_count
    lease_count=$(cat /var/lib/dhcpd/dhcpd.leases 2>/dev/null | grep -c "^lease " || echo "0")
    status_line "DHCP leases" "$lease_count" "active"

    # Uptime
    local uptime_str
    uptime_str=$(uptime -p 2>/dev/null || uptime | awk -F'up' '{print $2}' | awk -F',' '{print $1}')
    status_line "Uptime" "$uptime_str"
}

# ─── JSON wrapper ────────────────────────────────────────────────────
json_start() {
    echo "{"
    echo "  \"timestamp\": \"$TIMESTAMP\","
    echo "  \"hostname\": \"$(hostname)\","
    echo "  \"metrics\": ["
}

json_end() {
    echo "    {}"
    echo "  ]"
    echo "}"
}

# ─── Main ────────────────────────────────────────────────────────────
run_checks() {
    if ! $JSON_MODE; then
        echo -e "${BOLD}BCM Cluster Monitor — $TIMESTAMP${NC}"
    else
        json_start
    fi

    $CHECK_SERVICES && check_services
    $CHECK_PROCESSES && check_processes
    $CHECK_NODES && check_nodes
    $CHECK_SYSTEM && check_system

    if $JSON_MODE; then
        json_end
    fi

    if ! $JSON_MODE; then
        echo ""
        echo -e "${CYAN}─── Monitor complete: $TIMESTAMP ───${NC}"
    fi
}

if $CONTINUOUS; then
    while true; do
        clear
        run_checks
        echo ""
        echo -e "${YELLOW}Refreshing in ${INTERVAL}s... (Ctrl+C to stop)${NC}"
        sleep "$INTERVAL"
    done
else
    run_checks
fi
