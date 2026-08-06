#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Installation Script
# =============================================================================
# This script installs the mesh scripts to /opt/mesh and sets up systemd service.
# Run this once to set up the system.
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/mesh"

log() {
    echo -e "${GREEN}[INSTALL]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

# Create installation directory
log "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy scripts
log "Copying scripts to $INSTALL_DIR..."
cp "$SCRIPT_DIR"/config.sh "$INSTALL_DIR/"
cp "$SCRIPT_DIR"/install_packages.sh "$INSTALL_DIR/"
cp "$SCRIPT_DIR"/setup_mesh.sh "$INSTALL_DIR/"
cp "$SCRIPT_DIR"/mesh_status.sh "$INSTALL_DIR/"
cp "$SCRIPT_DIR"/start_mesh.sh "$INSTALL_DIR/"
cp "$SCRIPT_DIR"/stop_mesh.sh "$INSTALL_DIR/"

# Make scripts executable
chmod +x "$INSTALL_DIR"/*.sh

# Install systemd service
log "Installing systemd service..."
cp "$SCRIPT_DIR"/batman-mesh.service /etc/systemd/system/
systemctl daemon-reload

# Enable service at boot
systemctl enable batman-mesh.service

log "Installation complete!"
echo ""
echo "=========================================="
echo "  Installation Summary"
echo "=========================================="
echo ""
echo "Scripts installed to: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit configuration:"
echo "     sudo nano $INSTALL_DIR/config.sh"
echo ""
echo "  2. Install required packages:"
echo "     sudo $INSTALL_DIR/install_packages.sh"
echo ""
echo "  3. Setup mesh network:"
echo "     sudo $INSTALL_DIR/setup_mesh.sh"
echo ""
echo "  4. Check mesh status:"
echo "     sudo $INSTALL_DIR/mesh_status.sh"
echo ""
echo "  5. Enable auto-start at boot:"
echo "     sudo systemctl enable batman-mesh"
echo "     sudo systemctl start batman-mesh"
echo ""
echo "  Or start manually:"
echo "     sudo $INSTALL_DIR/start_mesh.sh"
echo "=========================================="
