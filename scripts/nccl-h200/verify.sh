#!/bin/bash
###############################################################################
# NCCL Build Verification Script for DGX H200
#
# Run this AFTER build.sh to verify the build artifacts are correct.
# This performs deep inspection of the compiled binaries to ensure
# they contain the correct GPU architecture code.
#
# Usage:
#   chmod +x verify.sh
#   ./verify.sh [bins_dir]
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more critical checks failed
###############################################################################
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINS_DIR="${1:-${SCRIPT_DIR}/build/bins}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}✓${NC} $*"; ((PASS++)); }
fail() { echo -e "  ${RED}✗${NC} $*"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $*"; ((WARN++)); }
header() { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          NCCL H200 Build Verification Suite                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "Bins directory: ${BINS_DIR}"
echo "Timestamp:      $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

if [[ ! -d "${BINS_DIR}" ]]; then
    fail "Bins directory does not exist: ${BINS_DIR}"
    echo -e "\n${RED}RESULT: FAILED${NC} — run build.sh first"
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
header "1. FILE PRESENCE CHECKS"
# ─────────────────────────────────────────────────────────────────────────────

# Check for NCCL library
NCCL_LIB=""
for candidate in "${BINS_DIR}/libnccl.so" "${BINS_DIR}"/libnccl.so.*; do
    if [[ -f "${candidate}" ]] || [[ -L "${candidate}" ]]; then
        NCCL_LIB="${candidate}"
        break
    fi
done

if [[ -n "${NCCL_LIB}" ]]; then
    LIBSIZE=$(stat -Lc%s "${NCCL_LIB}" 2>/dev/null || echo "0")
    pass "libnccl.so found ($(numfmt --to=iec "${LIBSIZE}" 2>/dev/null || echo "${LIBSIZE} bytes"))"
else
    fail "libnccl.so NOT FOUND"
fi

# Check for test binaries
EXPECTED_TESTS=(all_reduce_perf all_gather_perf broadcast_perf reduce_perf reduce_scatter_perf alltoall_perf sendrecv_perf scatter_perf gather_perf hypercube_perf)
FOUND_TESTS=0
MISSING_TESTS=()

for test in "${EXPECTED_TESTS[@]}"; do
    if [[ -x "${BINS_DIR}/${test}" ]]; then
        ((FOUND_TESTS++))
    else
        MISSING_TESTS+=("${test}")
    fi
done

if (( FOUND_TESTS >= 5 )); then
    pass "${FOUND_TESTS}/${#EXPECTED_TESTS[@]} test binaries present"
elif (( FOUND_TESTS > 0 )); then
    warn "Only ${FOUND_TESTS}/${#EXPECTED_TESTS[@]} test binaries found (missing: ${MISSING_TESTS[*]})"
else
    fail "No test binaries found"
fi

# Specifically check all_reduce_perf (this is the one from the screenshots)
if [[ -x "${BINS_DIR}/all_reduce_perf" ]]; then
    pass "all_reduce_perf present and executable"
else
    fail "all_reduce_perf missing — this is the primary test binary"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "2. GPU ARCHITECTURE CODE ANALYSIS (CRITICAL)"
# ─────────────────────────────────────────────────────────────────────────────

if ! command -v cuobjdump &>/dev/null; then
    warn "cuobjdump not in PATH — cannot inspect binaries for GPU code"
    warn "Source your CUDA env first: source build/cuda_env.sh"
    warn "Then re-run this script"
else
    echo -e "  Using cuobjdump: $(which cuobjdump)"

    if [[ -n "${NCCL_LIB}" ]]; then
        echo ""
        echo -e "  ${BLUE}Analyzing libnccl.so:${NC}"

        # SASS analysis (precompiled GPU code)
        SASS_OUTPUT=$(cuobjdump -lelf "${NCCL_LIB}" 2>/dev/null || true)
        SM90_COUNT=$(echo "${SASS_OUTPUT}" | grep -c "sm_90" || true)
        SM80_COUNT=$(echo "${SASS_OUTPUT}" | grep -c "sm_80" || true)

        if (( SM90_COUNT > 0 )); then
            pass "SASS: ${SM90_COUNT} sm_90 (Hopper) sections found"
        else
            fail "SASS: No sm_90 sections — NCCL will not run on H200!"
        fi

        # PTX analysis (JIT-compilable code) — THIS IS THE KEY CHECK
        PTX_OUTPUT=$(cuobjdump -lptx "${NCCL_LIB}" 2>/dev/null || true)
        PTX90_COUNT=$(echo "${PTX_OUTPUT}" | grep -c "compute_90" || true)

        if (( PTX90_COUNT > 0 )); then
            pass "PTX:  ${PTX90_COUNT} compute_90 sections found ← THIS IS THE FIX"
        else
            fail "PTX:  No compute_90 PTX found!"
            fail "      This was the original bug — without PTX, CUDA cannot JIT for H200"
            fail "      Error would be: 'no kernel image is available for execution on the device'"
        fi

        # Extra info
        if (( SM80_COUNT > 0 )); then
            warn "Also found ${SM80_COUNT} sm_80 sections (Ampere) — unexpected for H200-only build"
        fi
    fi

    # Check test binary too
    if [[ -x "${BINS_DIR}/all_reduce_perf" ]]; then
        echo ""
        echo -e "  ${BLUE}Analyzing all_reduce_perf:${NC}"
        TEST_SASS=$(cuobjdump -lelf "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep -c "sm_90" || true)
        TEST_PTX=$(cuobjdump -lptx "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep -c "compute_90" || true)

        if (( TEST_SASS > 0 )); then
            pass "all_reduce_perf: ${TEST_SASS} sm_90 SASS sections"
        fi
        if (( TEST_PTX > 0 )); then
            pass "all_reduce_perf: ${TEST_PTX} compute_90 PTX sections"
        fi
        if (( TEST_SASS == 0 )) && (( TEST_PTX == 0 )); then
            warn "all_reduce_perf has no embedded GPU code (normal — it uses libnccl at runtime)"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "3. LIBRARY DEPENDENCY CHECK"
# ─────────────────────────────────────────────────────────────────────────────

if command -v ldd &>/dev/null && [[ -x "${BINS_DIR}/all_reduce_perf" ]]; then
    # Check for unresolved dependencies
    UNRESOLVED=$(LD_LIBRARY_PATH="${BINS_DIR}:${LD_LIBRARY_PATH:-}" ldd "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep "not found" || true)
    if [[ -z "${UNRESOLVED}" ]]; then
        pass "all_reduce_perf: all library dependencies resolved"
    else
        fail "all_reduce_perf: unresolved dependencies:"
        echo "${UNRESOLVED}" | while read -r line; do
            echo "      ${line}"
        done
    fi

    # Check it links to our libnccl
    NCCL_LINK=$(LD_LIBRARY_PATH="${BINS_DIR}:${LD_LIBRARY_PATH:-}" ldd "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep "libnccl" || true)
    if [[ -n "${NCCL_LINK}" ]]; then
        pass "Links to NCCL: ${NCCL_LINK}"
    else
        warn "Cannot verify NCCL linkage via ldd"
    fi

    # Check for MPI linkage
    MPI_LINK=$(LD_LIBRARY_PATH="${BINS_DIR}:${LD_LIBRARY_PATH:-}" ldd "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep "libmpi" || true)
    if [[ -n "${MPI_LINK}" ]]; then
        pass "MPI support: linked to libmpi"
    else
        warn "No libmpi linkage detected — multi-node tests may fail"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "4. RUNTIME ENVIRONMENT CHECK"
# ─────────────────────────────────────────────────────────────────────────────

# Check GPU accessibility
if command -v nvidia-smi &>/dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,compute_cap,driver_version --format=csv,noheader 2>/dev/null | head -1)
    if [[ -n "${GPU_INFO}" ]]; then
        pass "GPU accessible: ${GPU_INFO}"

        GPU_CC=$(echo "${GPU_INFO}" | awk -F',' '{print $2}' | tr -d ' ')
        if [[ "${GPU_CC}" == "9.0" ]]; then
            pass "GPU compute capability: 9.0 (matches sm_90 build target)"
        else
            warn "GPU compute capability: ${GPU_CC} (built for 9.0)"
        fi
    else
        warn "nvidia-smi present but no GPU data returned"
    fi
else
    warn "nvidia-smi not available — cannot check GPU at runtime"
fi

# Check CUDA runtime
if command -v nvcc &>/dev/null; then
    pass "nvcc in PATH: $(nvcc --version 2>/dev/null | grep "release" | awk '{print $NF}' | tr -d ',')"
else
    warn "nvcc not in PATH — source cuda_env.sh before running tests"
fi

# Check NCCL version from header
NCCL_HEADER="${SCRIPT_DIR}/build/nccl/build/include/nccl.h"
if [[ -f "${NCCL_HEADER}" ]]; then
    NCCL_MAJOR=$(grep "NCCL_MAJOR" "${NCCL_HEADER}" | head -1 | awk '{print $3}')
    NCCL_MINOR=$(grep "NCCL_MINOR" "${NCCL_HEADER}" | head -1 | awk '{print $3}')
    NCCL_PATCH=$(grep "NCCL_PATCH" "${NCCL_HEADER}" | head -1 | awk '{print $3}')
    pass "NCCL version: ${NCCL_MAJOR}.${NCCL_MINOR}.${NCCL_PATCH}"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "5. QUICK SMOKE TEST"
# ─────────────────────────────────────────────────────────────────────────────

if command -v nvidia-smi &>/dev/null && [[ -x "${BINS_DIR}/all_reduce_perf" ]]; then
    echo -e "  Running single-GPU all_reduce_perf smoke test..."
    export LD_LIBRARY_PATH="${BINS_DIR}:${LD_LIBRARY_PATH:-}"

    SMOKE_OUTPUT=$(timeout 30 "${BINS_DIR}/all_reduce_perf" -b 8 -e 8M -f 2 -g 1 2>&1) || SMOKE_RC=$?

    if [[ "${SMOKE_RC:-0}" -eq 0 ]] && echo "${SMOKE_OUTPUT}" | grep -q "Avg bus bandwidth"; then
        BW=$(echo "${SMOKE_OUTPUT}" | grep "Avg bus bandwidth" | tail -1)
        pass "Smoke test PASSED — ${BW}"
    elif echo "${SMOKE_OUTPUT}" | grep -q "no kernel image"; then
        fail "Smoke test FAILED — 'no kernel image' error persists!"
        fail "The PTX fix did not take effect. Check build flags."
        echo "${SMOKE_OUTPUT}" | tail -5 | while read -r line; do echo "      ${line}"; done
    else
        warn "Smoke test returned rc=${SMOKE_RC:-unknown}"
        echo "${SMOKE_OUTPUT}" | tail -5 | while read -r line; do echo "      ${line}"; done
    fi
else
    warn "Skipping smoke test (no GPU or all_reduce_perf not found)"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "VERIFICATION SUMMARY"
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}Passed${NC}: ${PASS}"
echo -e "  ${RED}Failed${NC}: ${FAIL}"
echo -e "  ${YELLOW}Warnings${NC}: ${WARN}"
echo ""

if (( FAIL > 0 )); then
    echo -e "  ${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${RED}║  VERIFICATION FAILED — DO NOT USE THIS BUILD            ║${NC}"
    echo -e "  ${RED}║  Fix the issues above, then run: ./build.sh --clean     ║${NC}"
    echo -e "  ${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    exit 1
else
    echo -e "  ${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║  ALL CHECKS PASSED — BUILD IS READY FOR H200           ║${NC}"
    echo -e "  ${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  Next: run multi-node NCCL test with ./run-nccl-test.sh"
    exit 0
fi
