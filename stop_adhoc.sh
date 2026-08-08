#!/bin/bash
# =============================================================================
# Batman-Adv Ad-Hoc Mode Stop Script
# =============================================================================
# Tears down the batman-adv mesh and IBSS network.
# Requires root privileges (run with sudo).
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.sh"
LOG_FILE="/var/log/mesh.log"

log()  { echo -e "${GREEN}[STOP]${NC} $1"; echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} This script must be run as root. Use: sudo $0"
    exit 1
fi

# Load config
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

IFACE="${PHYS_IFACE:-wlp0s20f3}"

echo "=========================================="
echo " Batman-Adv Mesh Shutdown"
echo "=========================================="
echo ""

# Stop dashboard
log "Stopping dashboard service..."
systemctl stop mesh-dashboard 2>/dev/null || true

# Stop alfred / batadv-vis
log "Stopping alfred and batadv-vis..."
pkill -f alfred 2>/dev/null || true
pkill -f batadv-vis 2>/dev/null || true

# Remove batman interface
if batctl if 2>/dev/null | grep -q "bat0"; then
    log "Removing bat0 interface..."
    batctl if del bat0 2>/dev/null || true
fi

# Flush and bring down bat0
if ip link show bat0 &>/dev/null; then
    log "Shutting down bat0..."
    ip addr flush dev bat0 2>/dev/null || true
    ip link set bat0 down 2>/dev/null || true
fi

# Leave IBSS network
if ip link show "$IFACE" &>/dev/null; then
    log "Leaving IBSS network on $IFACE..."
    ip link set "$IFACE" down 2>/dev/null || true
    iw dev "$IFACE" ibss leave 2>/dev/null || true
    ip link set "$IFACE" up 2>/dev/null || true
fi

# Disable IP forwarding
if grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
    sed -i '/net.ipv4.ip_forward = 1/d' /etc/sysctl.conf
fi
echo 0 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true

log "Mesh network stopped."
echo ""
info "========================================"
info "Batman-Adv mesh has been shut down."
info ""
info "  Interfaces down: bat0, $IFACE (IBSS left)"
info "  Processes killed: alfred, batadv-vis"
info ""
info "  To restart: sudo ./setup_adhoc.sh"
info "========================================"
