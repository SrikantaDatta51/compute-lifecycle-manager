# NCCL Build for DGX H200

Builds NCCL and NCCL-tests with correct GPU architecture flags for **NVIDIA H200** (Hopper, sm_90).

## The Problem

Building NCCL with only `-gencode=arch=compute_90,code=sm_90` (SASS only, no PTX) causes this runtime error:

```
Test CUDA failure common.cu:262 'no kernel image is available for execution on the device'
```

## The Fix

Include **PTX fallback** alongside SASS:

```diff
- NVCC_GENCODE="-gencode=arch=compute_90,code=sm_90"
+ NVCC_GENCODE="-gencode=arch=compute_90,code=sm_90 -gencode=arch=compute_90,code=compute_90"
```

The `code=compute_90` embeds PTX (Parallel Thread Execution) intermediate representation, enabling CUDA to JIT-compile kernels at runtime for the exact H200 GPU variant.

## Prerequisites

| Component | Version | Notes |
|---|---|---|
| CUDA Toolkit | 12.4+ or 13.0 | Must match cluster nodes |
| HPC-X | v2.24.1+ | For MPI (multi-node tests) |
| NVIDIA Driver | 550+ | On target H200 nodes |
| GCC | 11+ | Build toolchain |

## Files

| File | Purpose |
|---|---|
| `build.sh` | Main build script — compiles NCCL + NCCL-tests with correct flags |
| `verify.sh` | Post-build verification — checks SASS/PTX in binaries, runs smoke test |
| `run-nccl-test.sh` | Multi-node NCCL test runner via MPI |
| `hostfile.example` | Sample hostfile for multi-node tests |

## Quick Start

### 1. Build

```bash
chmod +x build.sh verify.sh run-nccl-test.sh

# First time (install CUDA from runfile):
./build.sh --cuda-runfile /path/to/cuda_13.0_xxx_linux.run

# Subsequent builds (CUDA already installed):
./build.sh --skip-cuda-install

# Clean rebuild:
./build.sh --clean --skip-cuda-install
```

### 2. Verify

```bash
./verify.sh
```

This checks:
- ✅ `libnccl.so` has **sm_90 SASS** (precompiled GPU code)
- ✅ `libnccl.so` has **compute_90 PTX** (JIT fallback — **the fix**)
- ✅ All library dependencies resolve
- ✅ Single-GPU smoke test passes

### 3. Run Multi-Node Test

```bash
# Edit hostfile
cp hostfile.example hostfile
vi hostfile

# Run
./run-nccl-test.sh --np 16 --gpus-per-node 8
```

### 4. Expected Output

```
#       size    count   type  redop  root  time    algbw   busbw  #wrong
        8       2       float sum    -1    ...     ...     ...    0
       ...
    8589934592  ...     ...   ...    -1    ...     ...     ~400   0
Avg bus bandwidth: ~400 GB/s
```

## Network Device Mapping (H200)

The `run-nccl-test.sh` configures these IB devices for GPU-Direct RDMA:

```
NCCL_NET_DEVICES=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_9,mlx5_10,mlx5_11
```

Adjust via `--help` if your H200 topology differs.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no kernel image available` | Missing PTX in build | Rebuild with `code=compute_90` (this script does it) |
| `NCCL WARN` about IB | Wrong IB device names | Check `ibstat` and update `NCCL_NET_DEVICES` |
| Hangs on multi-node | Firewall / routing | Check `NCCL_SOCKET_IFNAME` matches your management NIC |
| Low bandwidth | Wrong RDMA config | Verify `NCCL_IB_GDR_PEER_CONNECTION=1` |
