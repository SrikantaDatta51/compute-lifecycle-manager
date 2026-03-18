#!/bin/bash
###############################################################################
# generate_presigned_url.sh — Re-generate a presigned URL for an existing bundle
#
# Usage: ./generate_presigned_url.sh <node> <timestamp> [bucket] [region] [expiry]
#
# Example:
#   ./generate_presigned_url.sh dgx-b200-042 20260306_143022
###############################################################################

set -euo pipefail

NODE="${1:?Usage: $0 <node> <timestamp> [bucket] [region] [expiry]}"
TIMESTAMP="${2:?Missing timestamp (format: YYYYMMDD_HHMMSS)}"
S3_BUCKET="${3:-${NVIDIA_DEBUG_S3_BUCKET:-nvidia-debug-bundles}}"
S3_REGION="${4:-${AWS_DEFAULT_REGION:-us-west-2}}"
PRESIGN_EXPIRY="${5:-86400}"

BUNDLE_FILENAME="nvidia-debug-bundle_${NODE}_${TIMESTAMP}.tar.gz"
S3_KEY="bundles/${NODE}/${TIMESTAMP}/${BUNDLE_FILENAME}"

echo "Checking s3://${S3_BUCKET}/${S3_KEY}..."
aws s3 ls "s3://${S3_BUCKET}/${S3_KEY}" --region "$S3_REGION" || {
    echo "ERROR: Bundle not found in S3"
    exit 1
}

PRESIGNED_URL=$(aws s3 presign "s3://${S3_BUCKET}/${S3_KEY}" \
    --region "$S3_REGION" \
    --expires-in "$PRESIGN_EXPIRY")

echo ""
echo "═══ PRESIGNED DOWNLOAD URL ═══"
echo "Node:    $NODE"
echo "Bundle:  $BUNDLE_FILENAME"
echo "Expires: $(( PRESIGN_EXPIRY / 3600 )) hours"
echo ""
echo "$PRESIGNED_URL"
echo "══════════════════════════════"
