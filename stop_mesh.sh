#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Stop Script
# =============================================================================
# This script stops the mesh network.
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
LOG_FILE="/var/log/mesh.log"

log() {
    echo -e "${GREEN}[STOP]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} This script must be run as root. Use: sudo $0"
    exit 1
fi

# Load config
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

log "Stopping Batman-Adv mesh network..."

# Stop alfred
if pgrep -f alfred >/dev/null; then
    log "Stopping alfred..."
    pkill -f alfred 2>/dev/null || true
fi

# Remove batman interface
if batctl if | grep -q "bat0"; then
    log "Removing bat0 interface..."
    batctl if del bat0 2>/dev/null || true
fi

# Take down physical interface
IFACE="${MESH_IFACE:-wlan0}"
if ip link show "$IFACE" &>/dev/null; then
    log "Taking down $IFACE..."
    ip link set "$IFACE" down 2>/dev/null || true
    
    # Leave mesh network
    iw dev "$IFACE" leave 2>/dev/null || true
fi

# Disable IP forwarding
if [ -f /proc/sys/net/ipv4/ip_forward ]; then
    echo 0 > /proc/sys/net/ipv4/ip_forward
    log "Disabled IP forwarding"
fi

# Remove iptables rules (if we added them)
if command -v iptables &>/dev/null; then
    iptables -t nat -D POSTROUTING -o "$EXTERNAL_IFACE" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i bat0 -o "$EXTERNAL_IFACE" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$EXTERNAL_IFACE" -o bat0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
fi

log "Mesh network stopped."
echo ""
log "To restart mesh: sudo $SCRIPT_DIR/start_mesh.sh"
