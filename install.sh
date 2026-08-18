#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Installation Script
# =============================================================================
# Installs the meshd control-plane daemon (Python package + systemd unit).
# Run once per node with root:  sudo ./install.sh
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/mesh"
VENV="$INSTALL_DIR/.venv"
UNIT_SRC="$SCRIPT_DIR/deploy/units/meshd.service"
UNIT_DST="/etc/systemd/system/meshd.service"

EXTRAS=""

log()  { echo -e "${GREEN}[INSTALL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

# --- CLI ---------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-telemetry) EXTRAS="${EXTRAS:+$EXTRAS,}telemetry"; shift ;;
        --with-dashboard) EXTRAS="${EXTRAS:+$EXTRAS,}dashboard"; shift ;;
        --with-all)       EXTRAS="telemetry,dashboard"; shift ;;
        -h|--help)
            echo "Usage: $0 [--with-telemetry] [--with-dashboard] [--with-all]"
            exit 0 ;;
        *) error "unknown option: $1" ;;
    esac
done

# --- Package prerequisites --------------------------------------------
log "Running package installer (batctl, alfred, kernel modules)..."
"$SCRIPT_DIR/install_packages.sh"

# --- Layout ------------------------------------------------------------
log "Creating $INSTALL_DIR layout..."
mkdir -p "$INSTALL_DIR/config" "$INSTALL_DIR/run"

# --- Virtualenv + meshd ------------------------------------------------
if [[ ! -x "$VENV/bin/meshd" ]]; then
    log "Creating virtualenv at $VENV..."
    python3 -m venv "$VENV"
fi

log "Installing meshd + dependencies into $VENV..."
"$VENV/bin/pip" install --upgrade pip -q
if [[ -n "$EXTRAS" ]]; then
    "$VENV/bin/pip" install -q "${SCRIPT_DIR}[${EXTRAS}]"
else
    "$VENV/bin/pip" install -q "$SCRIPT_DIR"
fi

# --- Configuration -----------------------------------------------------
if [[ ! -f "$INSTALL_DIR/config/mesh.yaml" ]]; then
    log "Writing default configuration (edit before first start)..."
    "$VENV/bin/meshd" --init -c "$INSTALL_DIR/config/mesh.yaml"
else
    warn "Keeping existing $INSTALL_DIR/config/mesh.yaml"
fi

# --- systemd unit ------------------------------------------------------
log "Installing meshd.service..."
if [[ -f "$UNIT_SRC" ]]; then
    cp "$UNIT_SRC" "$UNIT_DST"
else
    error "missing unit file: $UNIT_SRC"
fi
systemctl daemon-reload
systemctl enable meshd.service

log "Installation complete!"
echo ""
echo "=========================================="
echo "  meshd installation summary"
echo "=========================================="
echo ""
echo "  Daemon:      $VENV/bin/meshd"
echo "  Config:      $INSTALL_DIR/config/mesh.yaml"
echo "  Unit:        meshd.service (enabled)"
echo "  CLI:         $VENV/bin/meshctl"
echo ""
echo "Next steps:"
echo "  1. Edit the config:"
echo "       sudo nano $INSTALL_DIR/config/mesh.yaml"
echo "     (set node.id, node.ip, and management.token;"
echo "      generate a token with:  $VENV/bin/meshctl token)"
echo ""
echo "  2. Validate the config:"
echo "       $VENV/bin/meshctl -c $INSTALL_DIR/config/mesh.yaml validate"
echo ""
echo "  3. Start the mesh:"
echo "       sudo systemctl start meshd"
echo "       $VENV/bin/meshctl status"
echo ""
echo "  4. Optional token override (avoids secrets in the yaml):"
echo "       echo 'MESH_MGMT_TOKEN=your-token' | sudo tee /etc/mesh/token.env"
echo "=========================================="