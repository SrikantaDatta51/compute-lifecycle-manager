#!/usr/bin/env bash
###############################################################################
# install.sh — Fleet Validation Framework Installer
###############################################################################
# Installs the Fleet Validator on a BCM headnode.
# Sets up directories, symlinks, systemd units, and validates dependencies.
###############################################################################
set -euo pipefail

INSTALL_DIR="/opt/fleet-validator"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="/var/lib/fleet-validator"

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'
YELLOW='\033[0;33m'; NC='\033[0m'

log_info() { echo -e "${BLUE}[INSTALL]${NC} $*"; }
log_ok()   { echo -e "${GREEN}[INSTALL]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[INSTALL]${NC} $*"; }
log_fail() { echo -e "${RED}[INSTALL]${NC} $*"; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Fleet Validation Framework — Installer                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Check root ──
if [[ $EUID -ne 0 ]]; then
    log_fail "Must run as root"
    exit 1
fi

# ── Validate dependencies ──
log_info "Checking dependencies..."
DEPS_OK=true

for cmd in cmsh python3 curl; do
    if command -v "$cmd" &>/dev/null; then
        log_ok "  ✅ ${cmd}: $(command -v "$cmd")"
    else
        log_warn "  ⚠️  ${cmd}: not found (some features may be limited)"
        [[ "$cmd" == "cmsh" ]] && DEPS_OK=false
    fi
done

# Check Python YAML
if python3 -c "import yaml" 2>/dev/null; then
    log_ok "  ✅ python3-yaml: installed"
else
    log_warn "  ⚠️  python3-yaml: not installed — installing..."
    pip3 install pyyaml 2>/dev/null || apt-get install -y python3-yaml 2>/dev/null || true
fi

if [[ "$DEPS_OK" == "false" ]]; then
    log_fail "Critical dependencies missing. Install cmsh (BCM) first."
    exit 1
fi

# ── Create directories ──
log_info "Creating directories..."
mkdir -p "${INSTALL_DIR}"/{bin,config,logs,dashboards}
mkdir -p "${INSTALL_DIR}/config"/{test-suites,sku-profiles}
mkdir -p "${STATE_DIR}"/{states,certifications}
mkdir -p /etc/fleet-validator

# ── Copy files ──
log_info "Installing files..."
cp -r "${SOURCE_DIR}/bin/"* "${INSTALL_DIR}/bin/"
cp -r "${SOURCE_DIR}/config/"* "${INSTALL_DIR}/config/"
cp -r "${SOURCE_DIR}/dashboards/"* "${INSTALL_DIR}/dashboards/" 2>/dev/null || true

# Make scripts executable
chmod +x "${INSTALL_DIR}/bin/"*.sh

# ── Create default protected-nodes file ──
if [[ ! -f /etc/fleet-validator/protected-nodes.txt ]]; then
    touch /etc/fleet-validator/protected-nodes.txt
    log_info "Created empty protected-nodes.txt (add customer nodes here)"
fi

# ── Install systemd units ──
log_info "Installing systemd units..."
cp "${SOURCE_DIR}/systemd/fleet-validator.service" /etc/systemd/system/
cp "${SOURCE_DIR}/systemd/fleet-validator.timer" /etc/systemd/system/

# Update ExecStart path in service
sed -i "s|/opt/fleet-validator|${INSTALL_DIR}|g" /etc/systemd/system/fleet-validator.service

systemctl daemon-reload
systemctl enable fleet-validator.timer
systemctl start fleet-validator.timer

log_ok "systemd timer enabled (daily at 02:00 UTC)"

# ── Show status ──
echo ""
log_ok "Installation complete!"
echo ""
echo "  Install dir:    ${INSTALL_DIR}"
echo "  State dir:      ${STATE_DIR}"
echo "  Config:         ${INSTALL_DIR}/config/"
echo "  Protected list: /etc/fleet-validator/protected-nodes.txt"
echo ""
echo "  Usage:"
echo "    # Manual run"
echo "    ${INSTALL_DIR}/bin/fleet-certify.sh --suite daily-quick"
echo ""
echo "    # Dry run (no state changes)"
echo "    ${INSTALL_DIR}/bin/fleet-certify.sh --suite daily-quick --dry-run"
echo ""
echo "    # Full certification"
echo "    ${INSTALL_DIR}/bin/fleet-certify.sh --suite full-certification --nodes dgx-b200-001"
echo ""
echo "    # Check timer status"
echo "    systemctl status fleet-validator.timer"
echo "    systemctl list-timers fleet-validator.timer"
echo ""
echo "    # View node states"
echo "    ${INSTALL_DIR}/bin/node-state-manager.sh summary"
echo ""
