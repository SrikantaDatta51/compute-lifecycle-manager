#!/usr/bin/env bash
#===============================================================================
# iso-join.sh — Reassemble a split ISO from chunks, with full integrity checks
#
# Designed for Linux (destination machine).
# Works on macOS too — auto-detects sha256sum vs shasum.
#
# Usage:
#   ./iso-join.sh <SPLIT_DIR> [OUTPUT_FILE]
#
# Arguments:
#   SPLIT_DIR   — Directory created by iso-split.sh (contains chunks/, manifest, etc.)
#   OUTPUT_FILE — Path for the reassembled file (default: read from manifest)
#
# Verification steps performed:
#   1. Validates manifest.txt exists and is readable
#   2. Verifies expected chunk count matches actual
#   3. Validates SHA-256 of every chunk against chunk-checksums.sha256
#   4. Concatenates chunks in order
#   5. Validates SHA-256 of reassembled file against original-checksum.sha256
#   6. Validates reassembled file size matches original
#===============================================================================
set -euo pipefail

#--- Colors -------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { printf "${CYAN}[INFO]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[ OK ]${NC}  %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
fail()  { printf "${RED}[FAIL]${NC}  %s\n" "$*"; }
die()   { printf "${RED}[ERROR]${NC} %s\n" "$*" >&2; exit 1; }

PASS=0
FAIL=0
check_pass() { ok "$1"; ((PASS++)); }
check_fail() { fail "$1"; ((FAIL++)); }

#--- Detect sha256 tool -------------------------------------------------------
if command -v sha256sum &>/dev/null; then
    SHA256="sha256sum"
    SHA256_CHECK="sha256sum -c"
elif command -v shasum &>/dev/null; then
    SHA256="shasum -a 256"
    SHA256_CHECK="shasum -a 256 -c"
else
    die "Neither sha256sum nor shasum found. Install coreutils."
fi

#--- Arguments ----------------------------------------------------------------
SPLIT_DIR="${1:?Usage: $0 <SPLIT_DIR> [OUTPUT_FILE]}"
[[ -d "$SPLIT_DIR" ]] || die "Directory not found: $SPLIT_DIR"

#--- Parse manifest -----------------------------------------------------------
MANIFEST="${SPLIT_DIR}/manifest.txt"
[[ -f "$MANIFEST" ]] || die "Manifest not found: $MANIFEST"

get_manifest() { grep "^$1=" "$MANIFEST" | cut -d= -f2; }

ORIG_FILENAME=$(get_manifest "original_filename")
ORIG_SIZE=$(get_manifest "original_size_bytes")
ORIG_SHA256=$(get_manifest "original_sha256")
EXPECTED_CHUNKS=$(get_manifest "chunk_count")
CHUNK_PREFIX=$(get_manifest "chunk_prefix")

OUTPUT_FILE="${2:-${ORIG_FILENAME}}"

echo ""
printf "${BOLD}========== ISO JOIN & VERIFY ==========${NC}\n"
echo "  Source dir:  ${SPLIT_DIR}/"
echo "  Original:    ${ORIG_FILENAME}"
echo "  Expect size: ${ORIG_SIZE} bytes"
echo "  Expect SHA:  ${ORIG_SHA256}"
echo "  Chunks:      ${EXPECTED_CHUNKS}"
echo "  Output:      ${OUTPUT_FILE}"
printf "${BOLD}=======================================${NC}\n"
echo ""

#--- Step 1: Verify chunk count -----------------------------------------------
info "Step 1/5: Verifying chunk count..."
ACTUAL_CHUNKS=$(ls -1 "${SPLIT_DIR}/chunks/${CHUNK_PREFIX}"* 2>/dev/null | wc -l | tr -d ' ')
if [[ "$ACTUAL_CHUNKS" -eq "$EXPECTED_CHUNKS" ]]; then
    check_pass "Chunk count: ${ACTUAL_CHUNKS}/${EXPECTED_CHUNKS}"
else
    check_fail "Chunk count mismatch: found ${ACTUAL_CHUNKS}, expected ${EXPECTED_CHUNKS}"
    die "Missing chunks — cannot proceed. Re-copy the split directory."
fi

#--- Step 2: Verify per-chunk checksums ---------------------------------------
info "Step 2/5: Verifying per-chunk SHA-256 checksums..."
CHECKSUM_FILE="${SPLIT_DIR}/chunk-checksums.sha256"
[[ -f "$CHECKSUM_FILE" ]] || die "Chunk checksum file not found: $CHECKSUM_FILE"

CHUNK_ERRORS=0
while IFS= read -r line; do
    EXPECTED_HASH=$(echo "$line" | awk '{print $1}')
    CHUNK_NAME=$(echo "$line" | awk '{print $2}')

    CHUNK_PATH="${SPLIT_DIR}/chunks/${CHUNK_NAME}"
    [[ -f "$CHUNK_PATH" ]] || { check_fail "Chunk not found: $CHUNK_NAME"; ((CHUNK_ERRORS++)); continue; }

    ACTUAL_HASH=$($SHA256 "$CHUNK_PATH" | awk '{print $1}')
    if [[ "$ACTUAL_HASH" == "$EXPECTED_HASH" ]]; then
        check_pass "Chunk ${CHUNK_NAME}: SHA-256 verified"
    else
        check_fail "Chunk ${CHUNK_NAME}: CHECKSUM MISMATCH"
        echo "    Expected: ${EXPECTED_HASH}"
        echo "    Got:      ${ACTUAL_HASH}"
        ((CHUNK_ERRORS++))
    fi
done < "$CHECKSUM_FILE"

if [[ "$CHUNK_ERRORS" -gt 0 ]]; then
    die "${CHUNK_ERRORS} chunk(s) failed verification. Re-copy corrupted chunks."
fi

#--- Step 3: Reassemble -------------------------------------------------------
info "Step 3/5: Reassembling chunks into ${OUTPUT_FILE}..."
cat "${SPLIT_DIR}/chunks/${CHUNK_PREFIX}"* > "$OUTPUT_FILE"
ok "Reassembly complete"

#--- Step 4: Verify file size -------------------------------------------------
info "Step 4/5: Verifying file size..."
ACTUAL_SIZE=$(wc -c < "$OUTPUT_FILE" | tr -d ' ')
if [[ "$ACTUAL_SIZE" -eq "$ORIG_SIZE" ]]; then
    check_pass "File size: ${ACTUAL_SIZE} bytes (matches original)"
else
    check_fail "File size mismatch: got ${ACTUAL_SIZE}, expected ${ORIG_SIZE}"
fi

#--- Step 5: Verify whole-file checksum ---------------------------------------
info "Step 5/5: Verifying SHA-256 of reassembled file (this may take a while)..."
ACTUAL_SHA256=$($SHA256 "$OUTPUT_FILE" | awk '{print $1}')
if [[ "$ACTUAL_SHA256" == "$ORIG_SHA256" ]]; then
    check_pass "SHA-256: ${ACTUAL_SHA256} (matches original)"
else
    check_fail "SHA-256 MISMATCH!"
    echo "    Expected: ${ORIG_SHA256}"
    echo "    Got:      ${ACTUAL_SHA256}"
fi

#--- Final report -------------------------------------------------------------
echo ""
printf "${BOLD}========== VERIFICATION REPORT ==========${NC}\n"
echo "  Checks passed: ${PASS}"
echo "  Checks failed: ${FAIL}"
if [[ "$FAIL" -eq 0 ]]; then
    printf "  Status: ${GREEN}${BOLD}ALL CHECKS PASSED ✓${NC}\n"
    echo ""
    echo "  Reassembled file: ${OUTPUT_FILE}"
    echo "  SHA-256: ${ACTUAL_SHA256}"
    echo ""
    echo "  The file is identical to the original. Safe to use."
else
    printf "  Status: ${RED}${BOLD}VERIFICATION FAILED ✗${NC}\n"
    echo ""
    echo "  ${FAIL} check(s) failed. The reassembled file may be corrupt."
    echo "  Re-copy the split directory from source and try again."
    exit 1
fi
printf "${BOLD}=========================================${NC}\n"
