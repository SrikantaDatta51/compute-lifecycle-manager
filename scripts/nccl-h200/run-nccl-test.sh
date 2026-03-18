#!/bin/bash
###############################################################################
# Multi-Node NCCL Test Runner for DGX H200
#
# Runs all_reduce_perf across multiple H200 nodes using MPI.
# Tailored for the H200 InfiniBand topology.
#
# Usage:
#   ./run-nccl-test.sh [--hostfile <path>] [--np <num_procs>] [--gpus-per-node <n>]
#
# Environment:
#   This script sources the CUDA and HPC-X environments automatically.
#   Make sure build.sh has been run first.
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ROOT="${SCRIPT_DIR}/build"
BINS_DIR="${BUILD_ROOT}/bins"

# ── Defaults ──
HOSTFILE="${SCRIPT_DIR}/hostfile"
NUM_PROCS=16           # Total MPI ranks (e.g., 2 nodes × 8 GPUs)
GPUS_PER_NODE=8
MIN_BYTES="8"
MAX_BYTES="8G"
STEP_FACTOR=2
TEST_BINARY="all_reduce_perf"
NCCL_DEBUG_LEVEL="INFO"
EXTRA_ARGS=""

# ── HPC-X path ──
HPCX_DIR="${SCRIPT_DIR}/hpcx-v2.24.1-gcc-doca_ofed-ubuntu24.04-cuda13-x86_64"

# ── H200 InfiniBand device mapping ──
# Adjust these for your specific H200 topology
# These are the IB HCAs used for GPU-Direct RDMA
NCCL_IB_DEVICES="mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_9,mlx5_10,mlx5_11"
UCX_DEVICE="mlx5_0:1"

# ── Argument parsing ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hostfile)     HOSTFILE="$2";         shift 2 ;;
        --np)           NUM_PROCS="$2";        shift 2 ;;
        --gpus-per-node) GPUS_PER_NODE="$2";   shift 2 ;;
        --min-bytes)    MIN_BYTES="$2";        shift 2 ;;
        --max-bytes)    MAX_BYTES="$2";        shift 2 ;;
        --test)         TEST_BINARY="$2";      shift 2 ;;
        --debug)        NCCL_DEBUG_LEVEL="TRACE"; shift ;;
        --help|-h)
            echo "Usage: $0 [--hostfile path] [--np N] [--gpus-per-node N] [--test binary] [--debug]"
            exit 0 ;;
        *)              EXTRA_ARGS="${EXTRA_ARGS} $1"; shift ;;
    esac
done

# ── Color helpers ──
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
fail()    { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          NCCL Multi-Node Test Runner (H200)                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Pre-checks ──
[[ -x "${BINS_DIR}/${TEST_BINARY}" ]] || fail "${TEST_BINARY} not found in ${BINS_DIR}. Run build.sh first."
[[ -f "${HOSTFILE}" ]] || fail "Hostfile not found: ${HOSTFILE}. Create it with one hostname per line."

info "Test binary:    ${BINS_DIR}/${TEST_BINARY}"
info "Hostfile:       ${HOSTFILE}"
info "Num processes:  ${NUM_PROCS}"
info "GPUs per node:  ${GPUS_PER_NODE}"
info "Data range:     ${MIN_BYTES} → ${MAX_BYTES} (factor ${STEP_FACTOR})"
info "NCCL debug:     ${NCCL_DEBUG_LEVEL}"
echo ""
info "Hosts:"
cat "${HOSTFILE}" | while read -r host; do echo "    ${host}"; done
echo ""

# ── Environment setup ──
info "Setting up environment..."

# Source CUDA
if [[ -f "${BUILD_ROOT}/cuda_env.sh" ]]; then
    source "${BUILD_ROOT}/cuda_env.sh"
fi

# Source HPC-X
if [[ -f "${HPCX_DIR}/hpcx-mt-init-ompi.sh" ]]; then
    source "${HPCX_DIR}/hpcx-mt-init-ompi.sh"
elif [[ -f "${HPCX_DIR}/hpcx-init-ompi.sh" ]]; then
    source "${HPCX_DIR}/hpcx-init-ompi.sh"
else
    fail "HPC-X init script not found"
fi

# Re-source CUDA to ensure priority
if [[ -f "${BUILD_ROOT}/cuda_env.sh" ]]; then
    source "${BUILD_ROOT}/cuda_env.sh"
fi

# Prepend our bins to LD_LIBRARY_PATH
export LD_LIBRARY_PATH="${BINS_DIR}:${LD_LIBRARY_PATH:-}"

ok "Environment ready (CUDA_HOME=${CUDA_HOME:-?}, OMPI_HOME=${OMPI_HOME:-?})"

# ── Run the test ──
info "Launching NCCL test..."
echo ""

RESULT_LOG="${SCRIPT_DIR}/nccl_result_$(date +%Y%m%d_%H%M%S).log"

mpirun --allow-run-as-root \
    -mca pml ucx \
    -mca coll ^hcoll \
    -mca btl ^openib,smcuda \
    --bind-to none \
    --hostfile "${HOSTFILE}" \
    -np "${NUM_PROCS}" \
    --npernode "${GPUS_PER_NODE}" \
    --report-bindings \
    -x LD_LIBRARY_PATH \
    -x PATH \
    -x NCCL_DEBUG="${NCCL_DEBUG_LEVEL}" \
    -x NCCL_IB_HCA="mlx5" \
    -x NCCL_NET_DEVICES="${NCCL_IB_DEVICES}" \
    -x UCX_NET_DEVICES="${UCX_DEVICE}" \
    -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
    -x NCCL_IB_GDR_PEER_CONNECTION=1 \
    -x CUDA_MODULE_LOADING=EAGER \
    -x NCCL_SOCKET_IFNAME="bond0" \
    -x NCCL_IB_DISABLE=0 \
    "${BINS_DIR}/${TEST_BINARY}" \
    -b "${MIN_BYTES}" \
    -e "${MAX_BYTES}" \
    -f "${STEP_FACTOR}" \
    -g 1 \
    -c 0 \
    ${EXTRA_ARGS} 2>&1 | tee "${RESULT_LOG}"

RC=${PIPESTATUS[0]}

echo ""
if [[ ${RC} -eq 0 ]]; then
    ok "NCCL test completed successfully!"
    ok "Results saved to: ${RESULT_LOG}"
    echo ""
    # Extract and display bandwidth summary
    if grep -q "Avg bus bandwidth" "${RESULT_LOG}"; then
        info "Bandwidth summary:"
        grep "Avg bus bandwidth" "${RESULT_LOG}"
    fi
else
    fail "NCCL test failed with exit code ${RC}. Check ${RESULT_LOG} for details."
fi
