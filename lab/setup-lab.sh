#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# BCM Lab — Setup Script
# ═══════════════════════════════════════════════════════════════════
# Run this ONCE to set up the lab environment:
#   1. Adds simulators to PATH
#   2. Resets BCM state to clean
#   3. Verifies everything works
#
# Usage:
#   source lab/setup-lab.sh
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SIM_DIR="$SCRIPT_DIR/simulators"

echo "═══════════════════════════════════════════════════════════"
echo "  BCM Lab Environment Setup"
echo "═══════════════════════════════════════════════════════════"

# 1. Add simulators to PATH
export PATH="$SIM_DIR:$PATH"
export CMSH_STATE_DIR="/tmp/bcm-lab-state"
echo "✅ Simulators added to PATH: $SIM_DIR"

# 2. Reset state
rm -rf "$CMSH_STATE_DIR"
mkdir -p "$CMSH_STATE_DIR"
echo "✅ State reset: $CMSH_STATE_DIR"

# 3. Initialize — run cmsh once to seed state
cmsh -c "device; list" > /dev/null 2>&1
scontrol show nodes > /dev/null 2>&1
echo "✅ BCM state initialized (3 nodes: cpu-n01, cpu-n02, gpu-n01)"

# 4. Verify
echo ""
echo "── Verify: cmsh device list ──"
cmsh -c "device; list"
echo ""
echo "── Verify: sinfo ──"
sinfo -l
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Lab ready! Run playbooks from: $REPO_ROOT"
echo ""
echo "  Example:"
echo "    cd $REPO_ROOT"
echo "    ansible-playbook -i tests/inventory/test-hosts.yml \\"
echo "        lab/ansible/playbooks/cluster_health.yml"
echo ""
echo "  BCM Concept Labs:"
echo "    ansible-playbook -i tests/inventory/test-hosts.yml \\"
echo "        lab/bcm-concepts/01-device-management.yml"
echo "═══════════════════════════════════════════════════════════"
