#!/bin/bash
# Verify BCM cluster health
# Run from the BCM head node
set -e

echo "============================================"
echo "  BCM Lab Cluster Verification"
echo "============================================"
echo ""

echo "=== 1. Node Status ==="
cmsh -c "device; list" 2>/dev/null || echo "cmsh not available (run on head node)"
echo ""

echo "=== 2. Slurm Status ==="
sinfo 2>/dev/null || echo "Slurm not configured yet"
echo ""

echo "=== 3. Slurm Nodes ==="
scontrol show nodes 2>/dev/null | grep -E "^NodeName|State|CPUTot|Gres" || true
echo ""

echo "=== 4. Job Queue ==="
squeue 2>/dev/null || echo "Slurm not running"
echo ""

echo "=== 5. Network ==="
ip -br addr
echo ""

echo "=== 6. Services ==="
for svc in slurmctld slurmd cmd cmdaemon mariadbd sshd; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "not-found")
    printf "  %-15s %s\n" "$svc" "$status"
done
echo ""

echo "============================================"
echo "  Verification Complete"
echo "============================================"
