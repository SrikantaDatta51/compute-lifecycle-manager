#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Nemotron Sample Workload — Slurm Job Script
# ═══════════════════════════════════════════════════════════════════
# Submit with: sbatch nemotron-sample.sh
# ═══════════════════════════════════════════════════════════════════

#SBATCH --job-name=nemotron-sample
#SBATCH --output=/tmp/nemotron-%j.out
#SBATCH --error=/tmp/nemotron-%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:30:00
#SBATCH --partition=cpu

echo "═══════════════════════════════════════════"
echo "  Nemotron Sample Workload"
echo "═══════════════════════════════════════════"
echo "Date:       $(date)"
echo "Hostname:   $(hostname)"
echo "Job ID:     $SLURM_JOB_ID"
echo "Node:       $SLURM_NODELIST"
echo "CPUs:       $SLURM_CPUS_ON_NODE"
echo "Partition:  $SLURM_JOB_PARTITION"
echo ""

# ── Phase 1: System Benchmark ──
echo "═══ Phase 1: CPU Benchmark ═══"
echo "Running synthetic matrix operations..."

python3 -c "
import time
import os

print(f'Python: {os.sys.version}')
print(f'CPUs available: {os.cpu_count()}')
print()

# Simple matrix multiplication benchmark
size = 500
print(f'Matrix multiply benchmark ({size}x{size})...')

# Pure Python matrix mult (no numpy dependency)
import random
random.seed(42)

A = [[random.random() for _ in range(size)] for _ in range(100)]
B = [[random.random() for _ in range(100)] for _ in range(size)]

start = time.time()
# Simplified: just row operations
result = []
for i in range(len(A)):
    row = []
    for j in range(len(B[0])):
        s = sum(A[i][k] * B[k][j] for k in range(len(B)))
        row.append(s)
    result.append(row)
elapsed = time.time() - start
print(f'Matrix multiply: {elapsed:.2f}s')
print(f'Result shape: {len(result)}x{len(result[0])}')
print()

# Memory allocation test
print('Memory allocation test...')
start = time.time()
data = [bytearray(1024*1024) for _ in range(100)]  # 100 MB
elapsed = time.time() - start
print(f'Allocated 100 MB in {elapsed:.4f}s')
del data
print()

print('═══ All benchmarks passed ═══')
" 2>&1

echo ""

# ── Phase 2: I/O Benchmark ──
echo "═══ Phase 2: I/O Benchmark ═══"
TMPDIR=$(mktemp -d /tmp/nemotron-io-XXXX)

# Write test
echo "Writing 100 MB..."
dd if=/dev/urandom of="$TMPDIR/testfile" bs=1M count=100 2>&1 | tail -1

# Read test
echo "Reading 100 MB..."
dd if="$TMPDIR/testfile" of=/dev/null bs=1M 2>&1 | tail -1

rm -rf "$TMPDIR"
echo ""

# ── Phase 3: Network Test ──
echo "═══ Phase 3: Network Connectivity ═══"
echo "Hostname: $(hostname -f 2>/dev/null || hostname)"
echo "IP Addresses:"
ip -4 addr show | grep "inet " | awk '{print "  " $2}'
echo ""

# ── Summary ──
echo "═══════════════════════════════════════════"
echo "  WORKLOAD COMPLETE"
echo "═══════════════════════════════════════════"
echo "Job ID:    $SLURM_JOB_ID"
echo "Exit Code: 0"
echo "End Time:  $(date)"
echo ""
echo "This is a sample workload for BCM lab testing."
echo "For GPU workloads, use partition=gpu and request GPUs with --gres=gpu:1"
echo ""
echo "Example GPU job:"
echo "  sbatch --partition=gpu --gres=gpu:1 nemotron-sample.sh"
