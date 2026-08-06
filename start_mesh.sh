#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Start Script
# =============================================================================
# This script starts the mesh network. Run at boot or manually.
# Requires root privileges.
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.sh"
SETUP_SCRIPT="${SCRIPT_DIR}/setup_mesh.sh"
STATUS_SCRIPT="${SCRIPT_DIR}/mesh_status.sh"
LOG_FILE="/var/log/mesh.log"

log() {
    echo -e "${GREEN}[START]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true
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

# Load config
if [ ! -f "$CONFIG_FILE" ]; then
    error "Configuration file not found: $CONFIG_FILE"
fi

source "$CONFIG_FILE"

log "Starting Batman-Adv mesh network..."

# Load kernel modules
log "Loading kernel modules..."
modprobe batman_adv || error "Failed to load batman_adv module"
modprobe cfg80211 2>/dev/null || true
modprobe mac80211 2>/dev/null || true

# Wait for module to be ready
sleep 1

# Run setup script
if [ -f "$SETUP_SCRIPT" ]; then
    log "Running setup script..."
    "$SETUP_SCRIPT"
else
    error "Setup script not found: $SETUP_SCRIPT"
fi

# Wait for mesh to stabilize
log "Waiting for mesh to stabilize..."
sleep 5

# Show status
log "Mesh network started!"
echo ""
if [ -f "$STATUS_SCRIPT" ]; then
    "$STATUS_SCRIPT"
fi

log "Mesh is running. Use '$STATUS_SCRIPT' to check status."
