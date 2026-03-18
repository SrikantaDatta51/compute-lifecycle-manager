#!/usr/bin/env bash
###############################################################################
# nccl-multinode-runner.sh — Multi-Node NCCL Test Runner
###############################################################################
# Orchestrates multi-node NCCL tests across available node pairs.
# Auto-detects non-protected nodes, generates hostfiles, handles
# H200 vs B200 IB device mappings.
#
# Usage:
#   nccl-multinode-runner.sh --nodes <n1,n2> --sku <h200|b200>
#                            [--test <all_reduce|all_gather|reduce_scatter>]
#                            [--cmsh <path>] [--dry-run]
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"

NODES=""
SKU="b200"
TEST="all_reduce"
CMSH_BIN="${CMSH_BIN:-/usr/bin/cmsh}"
DRY_RUN="false"
OUTPUT_DIR="/tmp/fleet-validator/nccl-multinode"

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${BLUE}[$(date -Iseconds)] [NCCL]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[$(date -Iseconds)] [NCCL]${NC}  $*"; }
log_fail()  { echo -e "${RED}[$(date -Iseconds)] [NCCL]${NC}  $*"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --nodes)      NODES="$2";      shift 2 ;;
        --sku)        SKU="$2";        shift 2 ;;
        --test)       TEST="$2";       shift 2 ;;
        --cmsh)       CMSH_BIN="$2";   shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --dry-run)    DRY_RUN="true";  shift ;;
        *) shift ;;
    esac
done

[[ -z "$NODES" ]] && { echo "Usage: $0 --nodes <n1,n2> --sku <h200|b200>"; exit 1; }

mkdir -p "$OUTPUT_DIR"

###############################################################################
# Load SKU profile
###############################################################################
SKU_FILE="${CONFIG_DIR}/sku-profiles/${SKU}.yml"
[[ -f "$SKU_FILE" ]] || { log_fail "SKU profile not found: ${SKU_FILE}"; exit 1; }

# Parse SKU values
GPU_COUNT=$(grep "^gpu_count:" "$SKU_FILE" | awk '{print $2}')
IB_DEVICES=$(grep "^ib_devices:" "$SKU_FILE" | sed 's/^ib_devices:[[:space:]]*//' | tr -d '"')
UCX_DEVICE=$(grep "^ucx_device:" "$SKU_FILE" | sed 's/^ucx_device:[[:space:]]*//' | tr -d '"')
NCCL_SOCKET=$(grep "^nccl_socket_ifname:" "$SKU_FILE" | sed 's/^nccl_socket_ifname:[[:space:]]*//' | tr -d '"')

# Determine test binary
case "$TEST" in
    all_reduce)      BINARY="all_reduce_perf"; THRESHOLD_KEY="nccl_multinode_allreduce_min_busbw_gbps" ;;
    all_gather)      BINARY="all_gather_perf"; THRESHOLD_KEY="nccl_multinode_allgather_min_busbw_gbps" ;;
    reduce_scatter)  BINARY="reduce_scatter_perf"; THRESHOLD_KEY="nccl_multinode_reducescatter_min_busbw_gbps" ;;
    *) log_fail "Unknown test: ${TEST}"; exit 1 ;;
esac

THRESHOLD=$(grep "^${THRESHOLD_KEY}:" "$SKU_FILE" | awk '{print $2}')

# Parse nodes
IFS=',' read -ra NODE_ARRAY <<< "$NODES"
TOTAL_PROCS=$(( ${#NODE_ARRAY[@]} * GPU_COUNT ))

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Multi-Node NCCL Test (${SKU^^})                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Nodes:       ${NODES}"
log_info "Test:        ${TEST} (${BINARY})"
log_info "GPUs/node:   ${GPU_COUNT}"
log_info "Total procs: ${TOTAL_PROCS}"
log_info "IB devices:  ${IB_DEVICES}"
log_info "Threshold:   ${THRESHOLD} GB/s"

###############################################################################
# Generate hostfile
###############################################################################
HOSTFILE="${OUTPUT_DIR}/hostfile_$(date +%Y%m%d_%H%M%S)"
for node in "${NODE_ARRAY[@]}"; do
    # Resolve node IP via cmsh if not in dry-run
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "${node} slots=${GPU_COUNT}" >> "$HOSTFILE"
    else
        local node_ip
        node_ip=$(${CMSH_BIN} -c "device; use ${node}; get ip" 2>/dev/null | tail -1 | tr -d '[:space:]')
        echo "${node_ip:-$node} slots=${GPU_COUNT}" >> "$HOSTFILE"
    fi
done

log_info "Hostfile:    ${HOSTFILE}"
cat "$HOSTFILE" | while read -r line; do echo "    ${line}"; done

###############################################################################
# Run the test (executed FROM the headnode, reaching out to compute nodes)
###############################################################################
RESULT_LOG="${OUTPUT_DIR}/nccl_${TEST}_$(date +%Y%m%d_%H%M%S).log"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "DRY_RUN: Would run mpirun with ${TOTAL_PROCS} procs across ${#NODE_ARRAY[@]} nodes"
    echo "DRY_RUN: simulated pass" > "$RESULT_LOG"
    exit 0
fi

log_info "Launching multi-node NCCL test..."
echo ""

mpirun --allow-run-as-root \
    -mca pml ucx \
    -mca coll ^hcoll \
    -mca btl ^openib,smcuda \
    --bind-to none \
    --hostfile "${HOSTFILE}" \
    -np "${TOTAL_PROCS}" \
    --npernode "${GPU_COUNT}" \
    --report-bindings \
    -x LD_LIBRARY_PATH \
    -x PATH \
    -x NCCL_DEBUG=INFO \
    -x NCCL_IB_HCA=mlx5 \
    -x NCCL_NET_DEVICES="${IB_DEVICES}" \
    -x UCX_NET_DEVICES="${UCX_DEVICE}" \
    -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
    -x NCCL_IB_GDR_PEER_CONNECTION=1 \
    -x CUDA_MODULE_LOADING=EAGER \
    -x NCCL_SOCKET_IFNAME="${NCCL_SOCKET}" \
    -x NCCL_IB_DISABLE=0 \
    "${BINARY}" \
    -b 8 -e 8G -f 2 -g 1 -c 0 2>&1 | tee "${RESULT_LOG}"

RC=${PIPESTATUS[0]}

echo ""
if [[ ${RC} -eq 0 ]]; then
    # Extract peak bus bandwidth
    PEAK_BW=$(grep -E '^\s+[0-9]' "$RESULT_LOG" | tail -1 | awk '{print $(NF-1)}')
    PEAK_INT=$(echo "${PEAK_BW:-0}" | cut -d. -f1)

    if [[ "${PEAK_INT}" -ge "${THRESHOLD}" ]]; then
        log_ok "✅ ${TEST} PASSED — ${PEAK_BW} GB/s ≥ ${THRESHOLD} GB/s"
    else
        log_fail "⚠️  ${TEST} BELOW THRESHOLD — ${PEAK_BW} GB/s < ${THRESHOLD} GB/s"
        exit 1
    fi
else
    log_fail "❌ ${TEST} FAILED with exit code ${RC}"
    exit 1
fi
