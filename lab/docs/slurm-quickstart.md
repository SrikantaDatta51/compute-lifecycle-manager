# Slurm Quick Start Guide

## Overview

Slurm is the workload manager installed by BCM. It manages job scheduling across compute nodes.

## Key Commands

| Command | Description |
|---------|-------------|
| `sinfo` | Show partition and node status |
| `squeue` | Show job queue |
| `sbatch <script>` | Submit a batch job |
| `srun <command>` | Run a command on allocated node |
| `scancel <jobid>` | Cancel a job |
| `scontrol show node` | Detailed node info |
| `sacct` | Show job accounting |

## Partitions

| Partition | Nodes | Resources |
|-----------|-------|-----------|
| `cpu-partition` | cpu-n01, cpu-n02 | 2 CPU cores each |
| `gpu-partition` | gpu-n01 | 4 CPU cores + 1 GV100 GPU |

## Example Jobs

### Simple CPU Job
```bash
sbatch --partition=cpu-partition --wrap="echo Hello from \$(hostname)"
```

### Multi-Node CPU Job
```bash
sbatch --partition=cpu-partition --nodes=2 --wrap="hostname"
```

### GPU Job
```bash
sbatch --partition=gpu-partition --gres=gpu:1 --wrap="nvidia-smi"
```

### Job Script Example
Create `my-job.sh`:
```bash
#!/bin/bash
#SBATCH --job-name=test-job
#SBATCH --partition=cpu-partition
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:05:00
#SBATCH --output=result_%j.log

echo "Running on: $(hostname)"
echo "Start: $(date)"
sleep 10
echo "Done: $(date)"
```

Submit: `sbatch my-job.sh`

## GPU Job Script
```bash
#!/bin/bash
#SBATCH --job-name=gpu-test
#SBATCH --partition=gpu-partition
#SBATCH --gres=gpu:1
#SBATCH --time=00:10:00
#SBATCH --output=gpu_%j.log

echo "Node: $(hostname)"
nvidia-smi
echo "CUDA devices: $CUDA_VISIBLE_DEVICES"
```

## Monitoring

```bash
# Watch job queue
watch -n 5 squeue

# Node utilization
sinfo -N -l

# Specific job details
scontrol show job <jobid>
```
