#!/bin/bash
# =============================================================================
# Batman-Adv Ad-Hoc Mode Stop Script
# =============================================================================
# Tears down the batman-adv mesh, IBSS network, and restores WiFi to managed
# mode so NetworkManager or wpa_supplicant can use it again.
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

# Ensure /usr/sbin is in PATH (iw, iwconfig may be there)
export PATH="$PATH:/usr/sbin"

# Load config
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

IFACE="${PHYS_IFACE:-wlan0}"

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

# Restore WiFi adapter to managed mode
if ip link show "$IFACE" &>/dev/null; then
    log "Restoring $IFACE to managed mode..."

    # Step 1: Bring interface DOWN (required before mode change)
    ip link set "$IFACE" down 2>/dev/null || true
    sleep 1

    # Step 2: Leave IBSS network
    iw dev "$IFACE" ibss leave 2>/dev/null || true

    # Step 3: Flush any stale IPs
    ip addr flush dev "$IFACE" 2>/dev/null || true

    # Step 4: Reset to managed mode (try iw first, fall back to iwconfig)
    if iw dev "$IFACE" set type managed 2>/dev/null; then
        log "Set $IFACE to managed mode via iw"
    elif iwconfig "$IFACE" mode managed 2>/dev/null; then
        log "Set $IFACE to managed mode via iwconfig"
    else
        warn "Could not set managed mode — driver may handle it automatically on up"
    fi

    sleep 1

    # Step 5: Bring interface back UP
    ip link set "$IFACE" up 2>/dev/null || true
    sleep 1

    # Step 6: Unblock rfkill in case it got blocked
    rfkill unblock wifi 2>/dev/null || true

    # Step 7: Re-enable NetworkManager so it can manage the interface again
    if command -v nmcli &>/dev/null; then
        nmcli device set "$IFACE" managed yes 2>/dev/null || true
        nmcli device connect "$IFACE" 2>/dev/null || true
        log "Re-enabled NetworkManager on $IFACE"
    fi

    # Verify
    mode=$(iw dev "$IFACE" info 2>/dev/null | grep "type" | awk '{print $2}')
    if [ "$mode" = "managed" ]; then
        log "$IFACE restored to managed mode successfully"
    else
        warn "Interface mode is '$mode', expected 'managed' — check manually"
    fi
fi

# Disable IP forwarding
if grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
    sed -i '/net.ipv4.ip_forward = 1/d' /etc/sysctl.conf
fi
echo 0 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true

# Remove iptables rules added by mesh
if command -v iptables &>/dev/null; then
    iptables -D INPUT -i bat0 -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i bat0 -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -o bat0 -j ACCEPT 2>/dev/null || true
fi

# Remove bat0 module if nothing else uses it
modprobe -r batman_adv 2>/dev/null || true

log "Mesh network stopped."
echo ""
info "========================================"
info "Batman-Adv mesh has been shut down."
info ""
info "  Interface $IFACE restored to managed mode"
info "  NetworkManager re-enabled"
info "  Stale IPs flushed"
info "  Processes killed: alfred, batadv-vis"
info "  batman_adv module unloaded"
info ""
info "  To restart: sudo ./setup_adhoc.sh"
info "========================================"
