#!/bin/bash
# Submit test Slurm jobs to verify the cluster
set -e

echo "=== Submitting Test Jobs ==="
echo ""

# Test 1: CPU job
echo "--- Test 1: CPU hostname job ---"
sbatch --partition=cpu-partition --job-name=test-cpu \
    --wrap="echo 'CPU test from $(hostname)' && uptime" 2>/dev/null && \
    echo "  Submitted" || echo "  Failed (is Slurm running?)"
echo ""

# Test 2: Multi-node job
echo "--- Test 2: Multi-node job ---"
sbatch --partition=cpu-partition --nodes=2 --job-name=test-multi \
    --wrap="hostname" 2>/dev/null && \
    echo "  Submitted" || echo "  Failed"
echo ""

# Test 3: GPU job
echo "--- Test 3: GPU job ---"
sbatch --partition=gpu-partition --gres=gpu:1 --job-name=test-gpu \
    --wrap="nvidia-smi" 2>/dev/null && \
    echo "  Submitted" || echo "  Failed (GPU partition may not exist)"
echo ""

sleep 3

echo "=== Job Queue ==="
squeue 2>/dev/null || echo "squeue not available"
echo ""
echo "Check results with: squeue -u root"
echo "View output with:   cat slurm-<jobid>.out"
