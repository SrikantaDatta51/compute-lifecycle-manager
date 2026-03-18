#!/bin/bash
###############################################################################
# upload_to_s3.sh — Upload NVIDIA debug bundle to S3 + generate presigned URL
#
# Usage: ./upload_to_s3.sh <bundle_path> <bucket> <region> <expiry_seconds>
#
# Prerequisites:
#   - AWS CLI v2 installed on BCM head node
#   - IAM role or credentials configured (via instance profile or env vars)
#
# Output:
#   - Uploads bundle to s3://<bucket>/bundles/<node>/<timestamp>/
#   - Generates presigned URL (default 24h expiry)
#   - Writes URL to <bundle_path>.url file
###############################################################################

set -euo pipefail

BUNDLE_PATH="${1:?Usage: $0 <bundle_path> <bucket> <region> <expiry>}"
S3_BUCKET="${2:?Missing S3 bucket name}"
S3_REGION="${3:-us-west-2}"
PRESIGN_EXPIRY="${4:-86400}"

# ── Validate ──
if [ ! -f "$BUNDLE_PATH" ]; then
    echo "ERROR: Bundle file not found: $BUNDLE_PATH"
    exit 1
fi

BUNDLE_FILENAME=$(basename "$BUNDLE_PATH")
BUNDLE_SIZE=$(du -sh "$BUNDLE_PATH" | awk '{print $1}')

# Extract node name and timestamp from filename
# Format: nvidia-debug-bundle_<node>_<timestamp>.tar.gz
NODE_NAME=$(echo "$BUNDLE_FILENAME" | sed 's/nvidia-debug-bundle_//;s/_[0-9]\{8\}_[0-9]\{6\}\.tar\.gz//')
TIMESTAMP=$(echo "$BUNDLE_FILENAME" | grep -oP '\d{8}_\d{6}')

S3_KEY="bundles/${NODE_NAME}/${TIMESTAMP}/${BUNDLE_FILENAME}"

echo "═══════════════════════════════════════════════════"
echo "  NVIDIA Debug Bundle → S3 Upload"
echo "═══════════════════════════════════════════════════"
echo "  File:    $BUNDLE_FILENAME"
echo "  Size:    $BUNDLE_SIZE"
echo "  Node:    $NODE_NAME"
echo "  Bucket:  s3://${S3_BUCKET}/${S3_KEY}"
echo "  Region:  $S3_REGION"
echo "  Expiry:  ${PRESIGN_EXPIRY}s ($(( PRESIGN_EXPIRY / 3600 ))h)"
echo "═══════════════════════════════════════════════════"

# ── Upload ──
echo "Uploading to S3..."
aws s3 cp "$BUNDLE_PATH" "s3://${S3_BUCKET}/${S3_KEY}" \
    --region "$S3_REGION" \
    --no-progress \
    --metadata "node=${NODE_NAME},timestamp=${TIMESTAMP},fleet=cic-dgx-b200"

if [ $? -ne 0 ]; then
    echo "ERROR: S3 upload failed"
    exit 1
fi
echo "✅ Upload complete"

# ── Generate Presigned URL ──
echo "Generating presigned download URL (expiry: ${PRESIGN_EXPIRY}s)..."
PRESIGNED_URL=$(aws s3 presign "s3://${S3_BUCKET}/${S3_KEY}" \
    --region "$S3_REGION" \
    --expires-in "$PRESIGN_EXPIRY")

if [ -z "$PRESIGNED_URL" ]; then
    echo "ERROR: Failed to generate presigned URL"
    exit 1
fi

# ── Save URL to file ──
URL_FILE="${BUNDLE_PATH}.url"
cat > "$URL_FILE" <<EOF
═══════════════════════════════════════════════════
NVIDIA Debug Bundle — Download Link
═══════════════════════════════════════════════════
Node:       $NODE_NAME
Timestamp:  $TIMESTAMP
File:       $BUNDLE_FILENAME
Size:       $BUNDLE_SIZE
Expires:    $(date -d "+${PRESIGN_EXPIRY} seconds" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo "${PRESIGN_EXPIRY}s from upload")

Download URL:
$PRESIGNED_URL

Instructions:
1. Click or copy the URL above to download the debug bundle
2. Attach the .tar.gz to your NVIDIA Support Case
3. Portal: https://enterprise-support.nvidia.com/
═══════════════════════════════════════════════════
EOF

echo "✅ URL saved to: $URL_FILE"
echo ""
echo "═══ DOWNLOAD URL ═══"
echo "$PRESIGNED_URL"
echo "════════════════════"
