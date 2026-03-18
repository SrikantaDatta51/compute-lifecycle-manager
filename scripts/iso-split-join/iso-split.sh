#!/usr/bin/env bash
#===============================================================================
# iso-split.sh — Split a large ISO (or any file) into chunks with checksums
#
# Designed for macOS (source machine).
# Works on Linux too — auto-detects sha256sum vs shasum.
#
# Usage:
#   ./iso-split.sh <ISO_FILE> [CHUNK_SIZE] [OUTPUT_DIR]
#
# Arguments:
#   ISO_FILE    — Path to the ISO file to split
#   CHUNK_SIZE  — Size per chunk (default: 4000m  = ~4 GB, FAT32-safe)
#                 Accepts split(1) size suffixes: b, k, m, g
#   OUTPUT_DIR  — Directory for output (default: <basename>-split)
#
# Output structure:
#   <OUTPUT_DIR>/
#     ├── chunks/
#     │   ├── part-aa
#     │   ├── part-ab
#     │   └── ...
#     ├── chunk-checksums.sha256      # per-chunk checksums
#     ├── original-checksum.sha256    # whole-file checksum
#     └── manifest.txt                # metadata (name, size, chunk count, etc.)
#
# After splitting, compress with:
#   cd <OUTPUT_DIR> && zip -r ../<basename>-split.zip .
# Or if destination is Linux, use tar:
#   tar czf <basename>-split.tar.gz -C <OUTPUT_DIR> .
#===============================================================================
set -euo pipefail

#--- Colors -------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { printf "${CYAN}[INFO]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
die()   { printf "${RED}[ERROR]${NC} %s\n" "$*" >&2; exit 1; }

#--- Detect sha256 tool -------------------------------------------------------
if command -v sha256sum &>/dev/null; then
    SHA256="sha256sum"
elif command -v shasum &>/dev/null; then
    SHA256="shasum -a 256"
else
    die "Neither sha256sum nor shasum found. Install coreutils."
fi

#--- Arguments ----------------------------------------------------------------
ISO_FILE="${1:?Usage: $0 <ISO_FILE> [CHUNK_SIZE] [OUTPUT_DIR]}"
CHUNK_SIZE="${2:-4000m}"
BASENAME="$(basename "${ISO_FILE}" | sed 's/\.[^.]*$//')"
OUTPUT_DIR="${3:-${BASENAME}-split}"

[[ -f "$ISO_FILE" ]] || die "File not found: $ISO_FILE"

#--- Prep output dir ----------------------------------------------------------
mkdir -p "${OUTPUT_DIR}/chunks"
info "Splitting ${BOLD}$(basename "$ISO_FILE")${NC}"
info "Chunk size: ${CHUNK_SIZE}"
info "Output dir: ${OUTPUT_DIR}/"

#--- Compute whole-file checksum first ----------------------------------------
info "Computing SHA-256 checksum of original file (this may take a while)..."
ORIGINAL_HASH=$($SHA256 "$ISO_FILE" | awk '{print $1}')
echo "${ORIGINAL_HASH}  $(basename "$ISO_FILE")" > "${OUTPUT_DIR}/original-checksum.sha256"
ok "Original SHA-256: ${ORIGINAL_HASH}"

#--- Split --------------------------------------------------------------------
info "Splitting file into chunks..."
split -b "$CHUNK_SIZE" "$ISO_FILE" "${OUTPUT_DIR}/chunks/part-"
CHUNK_COUNT=$(ls -1 "${OUTPUT_DIR}/chunks/" | wc -l | tr -d ' ')
ok "Created ${CHUNK_COUNT} chunk(s)"

#--- Per-chunk checksums ------------------------------------------------------
info "Computing per-chunk checksums..."
(
    cd "${OUTPUT_DIR}/chunks"
    for f in part-*; do
        $SHA256 "$f"
    done
) > "${OUTPUT_DIR}/chunk-checksums.sha256"
ok "Chunk checksums written to chunk-checksums.sha256"

#--- Manifest -----------------------------------------------------------------
FILE_SIZE=$(wc -c < "$ISO_FILE" | tr -d ' ')
cat > "${OUTPUT_DIR}/manifest.txt" <<EOF
# ISO Split Manifest
# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# Generator: iso-split.sh

original_filename=$(basename "$ISO_FILE")
original_size_bytes=${FILE_SIZE}
original_sha256=${ORIGINAL_HASH}
chunk_size=${CHUNK_SIZE}
chunk_count=${CHUNK_COUNT}
chunk_prefix=part-
EOF
ok "Manifest written"

#--- Summary ------------------------------------------------------------------
echo ""
printf "${BOLD}========== SPLIT COMPLETE ==========${NC}\n"
echo "  File:       $(basename "$ISO_FILE")"
echo "  Size:       ${FILE_SIZE} bytes"
echo "  Chunks:     ${CHUNK_COUNT}"
echo "  Chunk size: ${CHUNK_SIZE}"
echo "  SHA-256:    ${ORIGINAL_HASH}"
echo "  Output:     ${OUTPUT_DIR}/"
printf "${BOLD}====================================${NC}\n"
echo ""
info "Next steps:"
echo "  1. Copy ${OUTPUT_DIR}/ to destination (USB, scp, rsync, etc.)"
echo "  2. On destination, run: ./iso-join.sh ${OUTPUT_DIR}/"
echo ""
echo "  Optional — compress for transfer:"
echo "    tar czf ${BASENAME}-split.tar.gz -C ${OUTPUT_DIR} ."
echo "    zip -r ${BASENAME}-split.zip ${OUTPUT_DIR}/"
