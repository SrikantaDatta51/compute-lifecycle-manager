#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Slurm Setup via cmsh — Configure partitions and nodes
# ═══════════════════════════════════════════════════════════════════
# Run this ON the BCM head node directly, or use:
#   ansible-playbook playbooks/slurm_manage.yml -e "action=setup"
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail
CMSH="/usr/bin/cmsh"

echo "═══════════════════════════════════════════"
echo "  BCM Lab — Slurm Configuration"
echo "═══════════════════════════════════════════"

# 1. Set workload manager to Slurm
echo "Setting workload manager to Slurm..."
$CMSH -c "
  partition use default;
  set wlm slurm;
  commit
" 2>/dev/null || echo "WLM already set"

# 2. Create CPU partition
echo "Creating CPU partition..."
$CMSH -c "
  partition;
  add cpu;
  set default yes;
  set oversubscribe no;
  set maximumtime 24:00:00;
  commit
" 2>/dev/null || echo "CPU partition exists"

# 3. Create GPU partition
echo "Creating GPU partition..."
$CMSH -c "
  partition;
  add gpu;
  set default no;
  set oversubscribe no;
  set maximumtime 48:00:00;
  commit
" 2>/dev/null || echo "GPU partition exists"

# 4. Assign nodes to CPU partition
echo "Assigning cpu-n01, cpu-n02 to CPU partition..."
$CMSH -c "
  partition use cpu;
  append nodes cpu-n01,cpu-n02;
  commit
" 2>/dev/null || echo "Nodes already assigned"

# 5. Assign nodes to GPU partition
echo "Assigning gpu-n01 to GPU partition..."
$CMSH -c "
  partition use gpu;
  append nodes gpu-n01;
  commit
" 2>/dev/null || echo "Node already assigned"

# 6. Restart Slurm
echo "Restarting Slurm controller..."
systemctl restart slurmctld 2>/dev/null || echo "slurmctld not running"

sleep 3

# 7. Verify
echo ""
echo "═══ SLURM STATUS ═══"
sinfo 2>/dev/null || echo "Slurm not configured yet"
echo ""
echo "═══ PARTITIONS ═══"
$CMSH -c "partition; list" 2>/dev/null || echo "No partitions"

echo ""
echo "═══ Setup complete ═══"
