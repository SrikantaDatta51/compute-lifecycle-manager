#!/bin/bash
###############################################################################
# NCCL H200 Diagnostic Script
#
# Run this ON THE H200 NODE to collect all information needed to diagnose
# the "no kernel image is available for execution on the device" error.
#
# Usage: chmod +x diagnose.sh && ./diagnose.sh
#
# This script is READ-ONLY — it does not modify anything.
###############################################################################
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

REPORT_FILE="${1:-/tmp/nccl-h200-diagnostic-$(date +%Y%m%d_%H%M%S).txt}"

# Tee everything to report file
exec > >(tee -a "${REPORT_FILE}") 2>&1

pass() { echo -e "  ${GREEN}✓ PASS${NC}: $*"; }
fail() { echo -e "  ${RED}✗ FAIL${NC}: $*"; }
warn() { echo -e "  ${YELLOW}⚠ WARN${NC}: $*"; }
info() { echo -e "  ${BLUE}ℹ INFO${NC}: $*"; }
header() { echo -e "\n${CYAN}════════════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"; }

echo -e "${RED}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     NCCL H200 DIAGNOSTIC — ROOT CAUSE ANALYSIS             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "Hostname: $(hostname)"
echo "Date:     $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Report:   ${REPORT_FILE}"

CRITICAL_ISSUES=0

###############################################################################
header "1. GPU HARDWARE"
###############################################################################

if ! command -v nvidia-smi &>/dev/null; then
    fail "nvidia-smi NOT FOUND — no NVIDIA driver installed"
    ((CRITICAL_ISSUES++))
else
    info "nvidia-smi output:"
    nvidia-smi 2>&1 | head -20

    echo ""
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    GPU_CC=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 2>/dev/null || echo "unknown")
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    DRIVER_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    CUDA_DRIVER_VER=$(nvidia-smi | grep "CUDA Version" | awk '{print $NF}' 2>/dev/null || echo "unknown")

    info "GPU:            ${GPU_NAME}"
    info "GPU Count:      ${GPU_COUNT}"
    info "Compute Cap:    ${GPU_CC}"
    info "Driver Version: ${DRIVER_VER}"
    info "CUDA (driver):  ${CUDA_DRIVER_VER}"

    # CHECK: Is it actually Hopper?
    if echo "${GPU_NAME}" | grep -qiE "H100|H200"; then
        pass "Confirmed Hopper GPU (${GPU_NAME})"
    else
        warn "GPU is ${GPU_NAME} — expected H100 or H200"
    fi

    # CHECK: Compute capability
    if [[ "${GPU_CC}" == "9.0" ]]; then
        pass "Compute capability is 9.0 (sm_90)"
    else
        fail "Compute capability is ${GPU_CC}, expected 9.0"
        ((CRITICAL_ISSUES++))
    fi

    # ═══════════════════════════════════════════════════════════════
    # CRITICAL CHECK: Driver version vs CUDA toolkit compatibility
    # ═══════════════════════════════════════════════════════════════
    DRIVER_MAJOR=$(echo "${DRIVER_VER}" | cut -d. -f1)

    echo ""
    info "═══ DRIVER/CUDA COMPATIBILITY CHECK ═══"

    if (( DRIVER_MAJOR >= 580 )); then
        pass "Driver ${DRIVER_VER} supports CUDA 13.0 (requires ≥ 580.65)"
    elif (( DRIVER_MAJOR >= 555 )); then
        warn "Driver ${DRIVER_VER} supports up to CUDA 12.5-12.6"
        warn "If building with CUDA 13.0, the driver CANNOT run CUDA 13.0 binaries!"
        warn "This is likely YOUR ROOT CAUSE"
        ((CRITICAL_ISSUES++))
    elif (( DRIVER_MAJOR >= 550 )); then
        warn "Driver ${DRIVER_VER} supports up to CUDA 12.4"
        fail "CANNOT run CUDA 13.0 compiled code!"
        fail ">>> THIS IS LIKELY YOUR ROOT CAUSE <<<"
        fail ">>> Build with CUDA 12.4 to match your driver, OR upgrade driver to 580+ <<<"
        ((CRITICAL_ISSUES++))
    elif (( DRIVER_MAJOR >= 535 )); then
        fail "Driver ${DRIVER_VER} only supports CUDA 12.2 — TOO OLD for CUDA 13.0 binaries"
        ((CRITICAL_ISSUES++))
    else
        fail "Driver ${DRIVER_VER} is very old — upgrade to 580+"
        ((CRITICAL_ISSUES++))
    fi

    echo ""
    info "Driver-to-CUDA Max Support Matrix:"
    info "  Driver 535.x  → CUDA ≤ 12.2"
    info "  Driver 545.x  → CUDA ≤ 12.3"
    info "  Driver 550.x  → CUDA ≤ 12.4"
    info "  Driver 555.x  → CUDA ≤ 12.5"
    info "  Driver 560.x  → CUDA ≤ 12.6"
    info "  Driver 565.x  → CUDA ≤ 12.7"
    info "  Driver 570.x  → CUDA ≤ 12.8"
    info "  Driver 580.x  → CUDA ≤ 13.0"
    info "  Driver 595.x  → CUDA ≤ 13.2"
fi

###############################################################################
header "2. CUDA TOOLKIT"
###############################################################################

# Check all nvcc versions
info "Searching for nvcc installations..."
for nvcc_path in $(which -a nvcc 2>/dev/null) /usr/local/cuda/bin/nvcc /usr/local/cuda-*/bin/nvcc; do
    if [[ -x "${nvcc_path}" ]]; then
        VER=$("${nvcc_path}" --version 2>/dev/null | grep "release" | awk '{print $NF}' | tr -d ',' || echo "?")
        info "  ${nvcc_path} → CUDA ${VER}"
    fi
done

# Check CUDA_HOME
if [[ -n "${CUDA_HOME:-}" ]]; then
    info "CUDA_HOME=${CUDA_HOME}"
    if [[ -x "${CUDA_HOME}/bin/nvcc" ]]; then
        TOOLKIT_VER=$("${CUDA_HOME}/bin/nvcc" --version | grep "release" | awk '{print $NF}' | tr -d ',')
        info "CUDA_HOME nvcc version: ${TOOLKIT_VER}"

        # CHECK: Does toolkit CUDA match driver CUDA?
        if [[ -n "${CUDA_DRIVER_VER:-}" ]] && [[ "${CUDA_DRIVER_VER}" != "unknown" ]]; then
            TOOLKIT_MAJOR=$(echo "${TOOLKIT_VER}" | cut -d. -f1)
            DRIVER_CUDA_MAJOR=$(echo "${CUDA_DRIVER_VER}" | cut -d. -f1)

            if (( TOOLKIT_MAJOR > DRIVER_CUDA_MAJOR )); then
                fail "CUDA TOOLKIT (${TOOLKIT_VER}) IS NEWER THAN DRIVER SUPPORTS (${CUDA_DRIVER_VER})"
                fail ">>> THIS IS YOUR ROOT CAUSE <<<"
                fail ">>> The driver cannot execute code compiled with a newer CUDA toolkit <<<"
                fail ">>> FIX: Build with CUDA ${CUDA_DRIVER_VER} instead, OR upgrade driver <<<"
                ((CRITICAL_ISSUES++))
            elif (( TOOLKIT_MAJOR == DRIVER_CUDA_MAJOR )); then
                pass "CUDA toolkit major version (${TOOLKIT_MAJOR}) matches driver capability (${CUDA_DRIVER_VER})"
            else
                pass "CUDA toolkit (${TOOLKIT_VER}) is older than driver capability (${CUDA_DRIVER_VER}) — OK"
            fi
        fi
    else
        fail "CUDA_HOME set to ${CUDA_HOME} but nvcc not found there"
    fi
else
    warn "CUDA_HOME not set"
fi

# Check LD_LIBRARY_PATH for conflicting CUDA versions
echo ""
info "LD_LIBRARY_PATH CUDA libraries:"
echo "${LD_LIBRARY_PATH:-}" | tr ':' '\n' | while read -r p; do
    if [[ -f "${p}/libcudart.so" ]] 2>/dev/null; then
        ver=$(ls -la "${p}/libcudart.so"* 2>/dev/null | head -1)
        info "  ${p} → ${ver}"
    fi
done

###############################################################################
header "3. NCCL BUILD ARTIFACTS"
###############################################################################

# Look for NCCL libs in common locations
SEARCH_DIRS=(
    "$(pwd)/build/bins"
    "$(pwd)/bins"
    "$(pwd)/build/nccl/build/lib"
    "/tmp/mnt/baremetal-nccl-h200/build/bins"
    "/tmp/mnt/baremetal-nccl-h200/build/nccl/build/lib"
)

FOUND_NCCL=false
for dir in "${SEARCH_DIRS[@]}"; do
    if [[ -d "${dir}" ]]; then
        NCCL_SO=$(find "${dir}" -name "libnccl.so*" -type f 2>/dev/null | head -1)
        if [[ -n "${NCCL_SO}" ]]; then
            FOUND_NCCL=true
            info "Found NCCL at: ${NCCL_SO}"

            if command -v cuobjdump &>/dev/null; then
                echo ""
                info "SASS architectures in ${NCCL_SO}:"
                SASS=$(cuobjdump -lelf "${NCCL_SO}" 2>/dev/null | grep -oP "sm_\d+" | sort -u || true)
                if [[ -n "${SASS}" ]]; then
                    echo "${SASS}" | while read -r arch; do info "  SASS: ${arch}"; done
                else
                    fail "No SASS found in libnccl.so!"
                fi

                info "PTX architectures in ${NCCL_SO}:"
                PTX=$(cuobjdump -lptx "${NCCL_SO}" 2>/dev/null | grep -oP "compute_\d+" | sort -u || true)
                if [[ -n "${PTX}" ]]; then
                    echo "${PTX}" | while read -r arch; do info "  PTX: ${arch}"; done
                else
                    warn "No PTX found in libnccl.so"
                fi
            fi

            # Check which CUDA runtime it was linked against
            if command -v ldd &>/dev/null; then
                echo ""
                info "Library dependencies:"
                ldd "${NCCL_SO}" 2>/dev/null | grep -E "cuda|nccl|librt" | while read -r line; do
                    info "  ${line}"
                done
            fi
            break
        fi
    fi
done

if [[ "${FOUND_NCCL}" == "false" ]]; then
    warn "No libnccl.so found in common locations"
fi

# Check for test binary
for dir in "${SEARCH_DIRS[@]}"; do
    TEST_BIN="${dir}/all_reduce_perf"
    if [[ -x "${TEST_BIN}" ]]; then
        info "Found test binary: ${TEST_BIN}"
        if command -v cuobjdump &>/dev/null; then
            info "SASS in all_reduce_perf:"
            cuobjdump -lelf "${TEST_BIN}" 2>/dev/null | grep -oP "sm_\d+" | sort -u | while read -r a; do info "  ${a}"; done
            info "PTX in all_reduce_perf:"
            cuobjdump -lptx "${TEST_BIN}" 2>/dev/null | grep -oP "compute_\d+" | sort -u | while read -r a; do info "  ${a}"; done
        fi
        break
    fi
done

###############################################################################
header "4. SIMPLE CUDA RUNTIME TEST"
###############################################################################

# Write and compile a minimal CUDA test
TMPDIR=$(mktemp -d)
cat > "${TMPDIR}/test.cu" << 'CUDAEOF'
#include <cstdio>
__global__ void kernel() { }
int main() {
    int dev;
    cudaGetDevice(&dev);
    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, dev);
    printf("Device: %s\n", prop.name);
    printf("Compute: %d.%d\n", prop.major, prop.minor);
    printf("Driver CUDA: ");
    int driverVersion;
    cudaDriverGetVersion(&driverVersion);
    printf("%d.%d\n", driverVersion/1000, (driverVersion%1000)/10);
    printf("Runtime CUDA: ");
    int runtimeVersion;
    cudaRuntimeGetVersion(&runtimeVersion);
    printf("%d.%d\n", runtimeVersion/1000, (runtimeVersion%1000)/10);

    // Launch a trivial kernel
    kernel<<<1,1>>>();
    cudaError_t err = cudaDeviceSynchronize();
    if (err != cudaSuccess) {
        printf("KERNEL LAUNCH FAILED: %s\n", cudaGetErrorString(err));
        return 1;
    }
    printf("Kernel launch: SUCCESS\n");
    return 0;
}
CUDAEOF

NVCC_CMD="${CUDA_HOME:-/usr/local/cuda}/bin/nvcc"
if [[ -x "${NVCC_CMD}" ]]; then
    info "Compiling test with sm_90..."
    if "${NVCC_CMD}" -gencode=arch=compute_90,code=sm_90 -gencode=arch=compute_90,code=compute_90 \
        -o "${TMPDIR}/test" "${TMPDIR}/test.cu" 2>&1; then
        info "Running test..."
        OUTPUT=$("${TMPDIR}/test" 2>&1)
        echo "${OUTPUT}" | while read -r line; do info "  ${line}"; done

        if echo "${OUTPUT}" | grep -q "KERNEL LAUNCH FAILED"; then
            fail "CUDA kernel launch failed even with sm_90+PTX!"
            fail "This confirms a DRIVER/TOOLKIT version mismatch"
            ((CRITICAL_ISSUES++))
        elif echo "${OUTPUT}" | grep -q "SUCCESS"; then
            pass "Basic CUDA kernel launches successfully with sm_90"
        fi

        # Extract versions for analysis
        RUNTIME_CUDA=$(echo "${OUTPUT}" | grep "Runtime CUDA" | awk '{print $NF}')
        DRIVER_CUDA=$(echo "${OUTPUT}" | grep "Driver CUDA" | awk '{print $NF}')
        info "Runtime CUDA API: ${RUNTIME_CUDA}"
        info "Driver CUDA API:  ${DRIVER_CUDA}"

        R_MAJOR=$(echo "${RUNTIME_CUDA}" | cut -d. -f1)
        D_MAJOR=$(echo "${DRIVER_CUDA}" | cut -d. -f1)
        if (( R_MAJOR > D_MAJOR )); then
            fail "RUNTIME CUDA (${RUNTIME_CUDA}) > DRIVER CUDA (${DRIVER_CUDA})"
            fail ">>> CONFIRMED: CUDA TOOLKIT IS TOO NEW FOR YOUR DRIVER <<<"
            fail ">>> YOU MUST EITHER: <<<"
            fail ">>>   1. Downgrade CUDA toolkit to ${DRIVER_CUDA} <<<"
            fail ">>>   2. Upgrade GPU driver to support CUDA ${RUNTIME_CUDA} <<<"
            ((CRITICAL_ISSUES++))
        fi
    else
        fail "Compilation failed!"
    fi
else
    warn "nvcc not found, skipping CUDA runtime test"
fi

rm -rf "${TMPDIR}"

###############################################################################
header "5. NCCL-SPECIFIC CHECKS"
###############################################################################

# Check if NCCL environment plugins exist
info "NCCL plugins and libs:"
for p in /usr/lib/x86_64-linux-gnu/libnccl* /usr/local/lib/libnccl* /opt/*/lib/libnccl*; do
    [[ -f "${p}" ]] && info "  ${p}"
done

# Check for conflicting NCCL versions
info "Checking for multiple NCCL versions in LD_LIBRARY_PATH..."
echo "${LD_LIBRARY_PATH:-}" | tr ':' '\n' | while read -r p; do
    if [[ -f "${p}/libnccl.so" ]] 2>/dev/null || [[ -L "${p}/libnccl.so" ]] 2>/dev/null; then
        ver="unknown"
        if [[ -f "${p}/libnccl.so.2" ]]; then
            real=$(readlink -f "${p}/libnccl.so.2" 2>/dev/null)
            ver=$(basename "${real}" 2>/dev/null)
        fi
        info "  ${p}/libnccl.so → ${ver}"
    fi
done

###############################################################################
header "6. INFINIBAND / NETWORK"
###############################################################################

if command -v ibstat &>/dev/null; then
    info "InfiniBand ports:"
    ibstat | grep -E "CA |Port |State|Rate" | head -20
else
    warn "ibstat not found"
fi

if command -v ibv_devinfo &>/dev/null; then
    info "IB devices:"
    ibv_devinfo -l 2>/dev/null
fi

###############################################################################
header "DIAGNOSIS SUMMARY"
###############################################################################

echo ""
if (( CRITICAL_ISSUES > 0 )); then
    echo -e "  ${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${RED}║  ${CRITICAL_ISSUES} CRITICAL ISSUE(S) FOUND                               ║${NC}"
    echo -e "  ${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${RED}Most likely root cause: CUDA toolkit / driver version mismatch.${NC}"
    echo ""
    echo "  The CUDA toolkit used to BUILD nccl/nccl-tests must be"
    echo "  compatible with the GPU DRIVER on the H200 nodes."
    echo ""
    echo "  ┌──────────────────────────────────────────────────────┐"
    echo "  │ FIX OPTION 1 (recommended):                         │"
    echo "  │   Build with a CUDA toolkit that matches your        │"
    echo "  │   driver. Check 'nvidia-smi' CUDA Version field.     │"
    echo "  │                                                      │"
    echo "  │ FIX OPTION 2:                                        │"
    echo "  │   Upgrade the GPU driver to ≥ 580.65 to support      │"
    echo "  │   CUDA 13.0                                          │"
    echo "  └──────────────────────────────────────────────────────┘"
else
    echo -e "  ${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║  No critical issues detected from diagnostics              ║${NC}"
    echo -e "  ${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  If NCCL tests still fail, the issue might be:"
    echo "  1. Stale build artifacts (run: make clean && rebuild)"
    echo "  2. Wrong libnccl.so being picked up at runtime"
    echo "  3. LD_LIBRARY_PATH pointing to old NCCL"
fi

echo ""
echo "Full report saved to: ${REPORT_FILE}"
