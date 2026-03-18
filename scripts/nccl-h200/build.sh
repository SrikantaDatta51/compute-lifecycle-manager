#!/bin/bash
###############################################################################
# NCCL Build Script for DGX H200 (Hopper Architecture, sm_90)
# VERSION 2 — with CUDA toolkit/driver auto-detection
#
# This script builds NCCL and NCCL-tests with the correct NVCC_GENCODE flags.
#
# KEY FIXES:
#   1. Embeds PTX (compute_90) alongside SASS (sm_90) for JIT fallback
#   2. Auto-detects CUDA driver version and warns if toolkit is too new
#   3. Forces clean build to prevent stale objects
#   4. Sets LD_LIBRARY_PATH correctly to avoid picking up wrong libnccl
#   5. Targets ONLY sm_90 for H200 — no unnecessary archs
#
# Usage:
#   chmod +x build.sh
#   ./build.sh [--clean] [--skip-cuda-install] [--cuda-home /path/to/cuda]
#
# Author: AI Compute Platform Team
# Date:   2026-03-11
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ROOT="${SCRIPT_DIR}/build"
BINS_DIR="${BUILD_ROOT}/bins"

# Configuration
CUDA_RUNFILE=""
CUDA_INSTALL_DIR="${BUILD_ROOT}/cuda"
SKIP_CUDA_INSTALL=false
CUSTOM_CUDA_HOME=""
HPCX_DIR="${SCRIPT_DIR}/hpcx-v2.24.1-gcc-doca_ofed-ubuntu24.04-cuda13-x86_64"
NCCL_REPO="https://github.com/NVIDIA/nccl.git"
NCCL_TESTS_REPO="https://github.com/NVIDIA/nccl-tests.git"
NCCL_BRANCH=""
CLEAN_BUILD=true   # DEFAULT TO CLEAN to avoid stale artifacts
NPROC="$(nproc)"

# ─────────────────────────────────────────────────────────────────────────────
# GENCODE FLAGS — HOPPER ONLY, WITH PTX FALLBACK
#
# This is the SINGLE MOST IMPORTANT configuration:
#   sm_90       = precompiled SASS for Hopper
#   compute_90  = PTX for JIT compilation (covers all 9.0 variants)
#
# We ONLY target sm_90 for H200. No sm_80, sm_75, sm_100, etc.
# This keeps build fast and avoids cross-arch compilation issues.
# ─────────────────────────────────────────────────────────────────────────────
NVCC_GENCODE_FLAGS="-gencode=arch=compute_90,code=sm_90 -gencode=arch=compute_90,code=compute_90"

# Color helpers
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[FATAL]${NC} $*"; exit 1; }
section() { echo -e "\n${BLUE}═══ $* ═══${NC}\n"; }

# ─── Arg parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean)             CLEAN_BUILD=true;         shift ;;
        --no-clean)          CLEAN_BUILD=false;        shift ;;
        --skip-cuda-install) SKIP_CUDA_INSTALL=true;   shift ;;
        --cuda-runfile)      CUDA_RUNFILE="$2";        shift 2 ;;
        --cuda-home)         CUSTOM_CUDA_HOME="$2";    shift 2 ;;
        --hpcx-dir)          HPCX_DIR="$2";            shift 2 ;;
        --nccl-branch)       NCCL_BRANCH="$2";         shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--clean|--no-clean] [--skip-cuda-install] [--cuda-home <path>]"
            echo "          [--cuda-runfile <path>] [--hpcx-dir <path>] [--nccl-branch <tag>]"
            exit 0 ;;
        *)                   die "Unknown option: $1" ;;
    esac
done

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          NCCL Build for DGX H200 (v2 — auto-detect)        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

###############################################################################
section "STEP 1: PRE-FLIGHT CHECKS"
###############################################################################

# Must be x86_64
[[ "$(uname -m)" == "x86_64" ]] || die "Requires x86_64"
# Must have gcc and make
command -v gcc &>/dev/null || die "gcc not found — install build-essential"
command -v make &>/dev/null || die "make not found"
ok "Build tools: gcc $(gcc -dumpversion), make"

###############################################################################
section "STEP 2: DETECT GPU & DRIVER"
###############################################################################

if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    DRIVER_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
    DRIVER_CUDA=$(nvidia-smi 2>/dev/null | grep "CUDA Version" | awk '{print $NF}')
    DRIVER_MAJOR=$(echo "${DRIVER_VER}" | cut -d. -f1)
    ok "GPU: ${GPU_NAME}, Driver: ${DRIVER_VER}, Max CUDA: ${DRIVER_CUDA}"

    # ═══ CRITICAL: Check if CUDA 13.0 is compatible ═══
    DRIVER_CUDA_MAJOR=$(echo "${DRIVER_CUDA}" | cut -d. -f1)
    if (( DRIVER_CUDA_MAJOR < 13 )); then
        warn "═══════════════════════════════════════════════════════════════"
        warn "  YOUR DRIVER (${DRIVER_VER}) ONLY SUPPORTS CUDA UP TO ${DRIVER_CUDA}"
        warn "  BUILDING WITH CUDA 13.0 WILL PRODUCE BINARIES THAT CANNOT RUN!"
        warn "═══════════════════════════════════════════════════════════════"
        warn ""
        warn "  Recommended: Use CUDA ${DRIVER_CUDA} toolkit instead."
        warn "  e.g.: ./build.sh --cuda-home /usr/local/cuda-${DRIVER_CUDA%%.*}.${DRIVER_CUDA#*.}"
        warn ""
        warn "  OR upgrade driver to ≥ 580.65 for CUDA 13.0 support"
        warn ""
        echo -n "  Continue anyway? [y/N] "
        read -r answer
        if [[ "${answer}" != "y" ]] && [[ "${answer}" != "Y" ]]; then
            die "Aborted. Fix CUDA/driver mismatch first."
        fi
    fi
else
    warn "nvidia-smi not found — cross-compiling mode (no driver checks)"
    DRIVER_CUDA=""
fi

###############################################################################
section "STEP 3: SETUP CUDA TOOLKIT"
###############################################################################

mkdir -p "${BUILD_ROOT}" "${BINS_DIR}"

# Determine CUDA_HOME
if [[ -n "${CUSTOM_CUDA_HOME}" ]]; then
    CUDA_INSTALL_DIR="${CUSTOM_CUDA_HOME}"
    info "Using custom CUDA_HOME: ${CUDA_INSTALL_DIR}"
elif [[ "${SKIP_CUDA_INSTALL}" == "false" ]] && [[ -n "${CUDA_RUNFILE}" ]]; then
    [[ -f "${CUDA_RUNFILE}" ]] || die "CUDA runfile not found: ${CUDA_RUNFILE}"
    info "Installing CUDA from ${CUDA_RUNFILE}..."
    bash "${CUDA_RUNFILE}" --silent --toolkit --no-opengl-libs --no-drm --installpath="${CUDA_INSTALL_DIR}"
    ok "CUDA installed to ${CUDA_INSTALL_DIR}"
elif [[ -d "${CUDA_INSTALL_DIR}" ]] && [[ -x "${CUDA_INSTALL_DIR}/bin/nvcc" ]]; then
    info "Using existing CUDA at ${CUDA_INSTALL_DIR}"
elif command -v nvcc &>/dev/null; then
    CUDA_INSTALL_DIR="$(dirname "$(dirname "$(which nvcc)")")"
    info "Using system CUDA at ${CUDA_INSTALL_DIR}"
else
    die "No CUDA found. Use --cuda-home, --cuda-runfile, or install CUDA."
fi

# Set environment — EXPLICIT, no sourcing external env.sh
export CUDA_HOME="${CUDA_INSTALL_DIR}"
export PATH="${CUDA_HOME}/bin:${PATH}"
# IMPORTANT: Put our CUDA FIRST to override any HPC-X or system CUDA
export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

[[ -x "${CUDA_HOME}/bin/nvcc" ]] || die "nvcc not found at ${CUDA_HOME}/bin/nvcc"
NVCC_VER=$("${CUDA_HOME}/bin/nvcc" --version | grep "release" | sed 's/.*release //' | sed 's/,.*//')
ok "CUDA ${NVCC_VER} at ${CUDA_HOME}"

# ═══ SECOND CHECK: Compare nvcc version vs driver ═══
if [[ -n "${DRIVER_CUDA:-}" ]]; then
    TOOLKIT_MAJOR=$(echo "${NVCC_VER}" | cut -d. -f1)
    DRIVER_CUDA_MAJOR=$(echo "${DRIVER_CUDA}" | cut -d. -f1)
    if (( TOOLKIT_MAJOR > DRIVER_CUDA_MAJOR )); then
        echo ""
        die "FATAL: CUDA toolkit ${NVCC_VER} > driver max CUDA ${DRIVER_CUDA}!
    The GPU driver CANNOT execute code compiled with this CUDA version.
    The compiled binaries will fail with 'no kernel image available'.

    FIX: Use a CUDA toolkit ≤ ${DRIVER_CUDA}
         e.g.: ./build.sh --cuda-home /usr/local/cuda-${DRIVER_CUDA_MAJOR}

    OR upgrade the GPU driver to version ≥ 580.65 for CUDA 13.0 support."
    fi
fi

###############################################################################
section "STEP 4: SETUP HPC-X (MPI)"
###############################################################################

# Try multiple HPC-X locations
HPCX_FOUND=false
for hpcx_candidate in "${HPCX_DIR}" "${SCRIPT_DIR}"/hpcx-*; do
    for init in "${hpcx_candidate}/hpcx-mt-init-ompi.sh" "${hpcx_candidate}/hpcx-init-ompi.sh"; do
        if [[ -f "${init}" ]]; then
            info "Sourcing HPC-X: ${init}"
            source "${init}"
            HPCX_FOUND=true
            break 2
        fi
    done
done

if [[ "${HPCX_FOUND}" == "false" ]]; then
    die "HPC-X not found. Set --hpcx-dir or place HPC-X alongside this script."
fi

# CRITICAL: Re-set CUDA env after HPC-X (HPC-X may override CUDA paths)
export CUDA_HOME="${CUDA_INSTALL_DIR}"
export PATH="${CUDA_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

ok "HPC-X loaded, OMPI_HOME=${OMPI_HOME:-?}"
[[ -n "${OMPI_HOME:-}" ]] || die "OMPI_HOME not set after sourcing HPC-X"

###############################################################################
section "STEP 5: BUILD NCCL"
###############################################################################

NCCL_SRC="${BUILD_ROOT}/nccl"

if [[ ! -d "${NCCL_SRC}" ]]; then
    info "Cloning NCCL..."
    if [[ -n "${NCCL_BRANCH}" ]]; then
        git clone --branch "${NCCL_BRANCH}" --depth 1 "${NCCL_REPO}" "${NCCL_SRC}"
    else
        git clone --depth 1 "${NCCL_REPO}" "${NCCL_SRC}"
    fi
fi

cd "${NCCL_SRC}"

# ALWAYS CLEAN to prevent picking up old .o files with wrong arch
if [[ "${CLEAN_BUILD}" == "true" ]]; then
    info "Cleaning previous NCCL build..."
    make clean 2>/dev/null || true
    rm -rf build/ 2>/dev/null || true
fi

info "Building NCCL..."
info "  CUDA_HOME=${CUDA_HOME}"
info "  NVCC_GENCODE=${NVCC_GENCODE_FLAGS}"
info "  Parallelism: ${NPROC} jobs"

make -j"${NPROC}" src.build \
    CUDA_HOME="${CUDA_HOME}" \
    NVCC_GENCODE="${NVCC_GENCODE_FLAGS}" \
    2>&1 | tail -20

NCCL_LIB_DIR="${NCCL_SRC}/build/lib"
[[ -f "${NCCL_LIB_DIR}/libnccl.so" ]] || [[ -L "${NCCL_LIB_DIR}/libnccl.so" ]] || \
    die "NCCL build failed — libnccl.so not found"
ok "NCCL built: $(ls "${NCCL_LIB_DIR}"/libnccl.so*)"

###############################################################################
section "STEP 6: BUILD NCCL-TESTS"
###############################################################################

NCCL_TESTS_SRC="${BUILD_ROOT}/nccl-tests"

if [[ ! -d "${NCCL_TESTS_SRC}" ]]; then
    info "Cloning NCCL-tests..."
    git clone --depth 1 "${NCCL_TESTS_REPO}" "${NCCL_TESTS_SRC}"
fi

cd "${NCCL_TESTS_SRC}"

if [[ "${CLEAN_BUILD}" == "true" ]]; then
    info "Cleaning previous NCCL-tests build..."
    make clean 2>/dev/null || true
    rm -rf build/ 2>/dev/null || true
fi

info "Building NCCL-tests..."
info "  NCCL_HOME=${NCCL_SRC}/build"
info "  MPI_HOME=${OMPI_HOME}"

make -j"${NPROC}" \
    CUDA_HOME="${CUDA_HOME}" \
    NCCL_HOME="${NCCL_SRC}/build" \
    MPI=1 \
    MPI_HOME="${OMPI_HOME}" \
    NVCC_GENCODE="${NVCC_GENCODE_FLAGS}" \
    2>&1 | tail -20

[[ -f "${NCCL_TESTS_SRC}/build/all_reduce_perf" ]] || \
    die "NCCL-tests build failed — all_reduce_perf not found"
ok "NCCL-tests built: $(ls "${NCCL_TESTS_SRC}/build/"*_perf | wc -l) test binaries"

###############################################################################
section "STEP 7: COLLECT BINARIES"
###############################################################################

# Clean destination first
rm -rf "${BINS_DIR:?}"/*

# Copy test binaries
cp -v "${NCCL_TESTS_SRC}/build/"*_perf "${BINS_DIR}/"

# Copy NCCL libraries
cp -v "${NCCL_LIB_DIR}"/libnccl*.so* "${BINS_DIR}/"

# Remove junk
rm -f "${BINS_DIR}"/*.o "${BINS_DIR}"/verifiable 2>/dev/null

ok "Binaries collected in ${BINS_DIR}/"

###############################################################################
section "STEP 8: POST-BUILD VERIFICATION"
###############################################################################

VPASS=0; VFAIL=0

# Check 1: SASS in libnccl.so
if command -v cuobjdump &>/dev/null; then
    SM90=$(cuobjdump -lelf "${BINS_DIR}/libnccl.so" 2>/dev/null | grep -c "sm_90" || true)
    PTX90=$(cuobjdump -lptx "${BINS_DIR}/libnccl.so" 2>/dev/null | grep -c "compute_90" || true)

    if (( SM90 > 0 )); then ok "libnccl.so: ${SM90} sm_90 SASS sections"; ((VPASS++)); else
        echo -e "  ${RED}✗ libnccl.so: NO sm_90 SASS!${NC}"; ((VFAIL++)); fi
    if (( PTX90 > 0 )); then ok "libnccl.so: ${PTX90} compute_90 PTX sections"; ((VPASS++)); else
        echo -e "  ${RED}✗ libnccl.so: NO compute_90 PTX!${NC}"; ((VFAIL++)); fi

    # Check test binary too
    T_SM90=$(cuobjdump -lelf "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep -c "sm_90" || true)
    T_PTX90=$(cuobjdump -lptx "${BINS_DIR}/all_reduce_perf" 2>/dev/null | grep -c "compute_90" || true)
    if (( T_SM90 > 0 )); then ok "all_reduce_perf: ${T_SM90} sm_90 SASS"; ((VPASS++)); fi
    if (( T_PTX90 > 0 )); then ok "all_reduce_perf: ${T_PTX90} compute_90 PTX"; ((VPASS++)); fi
else
    warn "cuobjdump not in PATH — cannot verify binary content"
fi

# Check 2: Quick smoke test (single GPU)
if command -v nvidia-smi &>/dev/null; then
    info "Running single-GPU smoke test..."
    export LD_LIBRARY_PATH="${BINS_DIR}:${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"
    SMOKE=$(timeout 30 "${BINS_DIR}/all_reduce_perf" -b 8 -e 8M -f 2 -g 1 2>&1) || SMOKE_RC=$?

    if echo "${SMOKE}" | grep -q "no kernel image"; then
        echo -e "  ${RED}✗ SMOKE TEST FAILED: 'no kernel image' error!${NC}"
        echo -e "  ${RED}  This means CUDA toolkit ${NVCC_VER} is incompatible with driver ${DRIVER_VER:-?}${NC}"
        echo -e "  ${RED}  FIX: Use --cuda-home with a CUDA version matching your driver (${DRIVER_CUDA:-?})${NC}"
        ((VFAIL++))
    elif echo "${SMOKE}" | grep -q "Avg bus bandwidth"; then
        BW=$(echo "${SMOKE}" | grep "Avg bus bandwidth" | tail -1 | awk '{print $NF}')
        ok "Smoke test PASSED — bus bandwidth: ${BW} GB/s"
        ((VPASS++))
    else
        warn "Smoke test returned rc=${SMOKE_RC:-?}"
        echo "${SMOKE}" | tail -3
    fi
fi

# Final summary
echo ""
section "BUILD COMPLETE"
echo "  Passed: ${VPASS}, Failed: ${VFAIL}"
echo ""
if (( VFAIL > 0 )); then
    die "Build has verification failures — see above"
fi

ok "NCCL is ready for H200 testing!"
echo ""
info "Quick test:  cd ${BINS_DIR} && LD_LIBRARY_PATH=\$PWD:\$LD_LIBRARY_PATH ./all_reduce_perf -b 8 -e 256M -f 2 -g 8"
info "Multi-node:  ./run-nccl-test.sh"
