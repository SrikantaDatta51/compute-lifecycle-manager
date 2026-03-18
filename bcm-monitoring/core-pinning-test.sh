#!/bin/bash
# Core Pinning Contention Test on node002 (2 cores)
# Core 0: Pinned stress test (simulating Weka I/O thread)
# Core 1: Reserved for Slurm jobs
set -e

echo "============================================="
echo " CORE PINNING CONTENTION TEST"
echo " Host: $(hostname), Cores: $(nproc)"
echo "============================================="
echo ""

# Step 1: Start metrics server
echo "--- Step 1: Starting metrics server on :9256 ---"
pkill -f metrics-server.py 2>/dev/null || true
sleep 1
nohup python3 /tmp/metrics-server.py 9256 > /var/log/ms.log 2>&1 &
sleep 2
echo "Metrics server PID: $(pgrep -f metrics-server.py)"

# Step 2: Pin stress-ng to Core 0 (simulate Weka pinned I/O)
echo ""
echo "--- Step 2: Pinning stress-ng to Core 0 for 6 minutes ---"
pkill -f stress-ng 2>/dev/null || true
sleep 1
taskset -c 0 stress-ng --cpu 1 --cpu-method matrixprod --timeout 360 &
STRESS_PID=$!
echo "stress-ng PID: $STRESS_PID, pinned to Core 0"
echo "Verify: $(taskset -p $STRESS_PID)"

# Step 3: Create a CPU-bound Slurm job pinned to Core 1
echo ""
echo "--- Step 3: Creating Slurm job for Core 1 ---"
cat > /tmp/slurm-core1-job.sh << 'JOB'
#!/bin/bash
#SBATCH --job-name=core1-test
#SBATCH --output=/tmp/slurm-core1-output.log
#SBATCH --time=00:06:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1

# Pin this job to Core 1 only
taskset -c 1 stress-ng --cpu 1 --cpu-method matrixprod --timeout 330 &
SPID=$!
echo "Slurm job stress PID: $SPID, pinned to Core 1"
echo "Verify: $(taskset -p $SPID)"

# Log every 30 seconds
for i in $(seq 1 11); do
    sleep 30
    echo "=== $(date) === Core0: $(cat /proc/stat | awk '/^cpu0/ {print $2+$4}') Core1: $(cat /proc/stat | awk '/^cpu1/ {print $2+$4}')"
    ps -eo pid,comm,%cpu,psr --sort=-%cpu --no-headers | head -5
done

wait $SPID
echo "Slurm job complete"
JOB

chmod +x /tmp/slurm-core1-job.sh

# Submit via Slurm
echo "Submitting job..."
sbatch /tmp/slurm-core1-job.sh 2>&1 || echo "sbatch failed, running directly with taskset"

# Also run the core-1 stress directly in case sbatch fails
echo ""
echo "--- Also running Core 1 stress directly as backup ---"
taskset -c 1 stress-ng --cpu 1 --cpu-method matrixprod --timeout 360 &
STRESS2_PID=$!
echo "Core 1 stress PID: $STRESS2_PID, pinned to Core 1"
echo "Verify: $(taskset -p $STRESS2_PID)"

echo ""
echo "============================================="
echo " TEST RUNNING:"
echo "   Core 0: stress-ng PID $STRESS_PID (simulating Weka)"
echo "   Core 1: stress-ng PID $STRESS2_PID (simulating Slurm job)"
echo "   Duration: 6 minutes"
echo "   Metrics: http://$(hostname):9256"
echo "============================================="
echo ""
echo "Quick core check:"
ps -eo pid,comm,%cpu,psr --sort=-%cpu --no-headers | head -10
