#!/bin/bash
# =============================================================================
# Batman-Adv GCS Mesh Stop Script
# =============================================================================
# Tears down the batman-adv mesh, restores WiFi to managed mode,
# and re-enables NetworkManager.
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

IFACE="wlp0s20f3"

log()  { echo -e "${GREEN}[STOP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} This script must be run as root. Use: sudo $0"
    exit 1
fi

export PATH="$PATH:/usr/sbin"

echo "=========================================="
echo " Batman-Adv GCS Mesh Shutdown"
echo "=========================================="
echo ""

# Stop processes
log "Stopping alfred and batadv-vis..."
pkill -f alfred 2>/dev/null || true
pkill -f batadv-vis 2>/dev/null || true

# Remove batman interface
if batctl if 2>/dev/null | grep -q "bat0"; then
    log "Removing bat0 interface..."
    batctl if del bat0 2>/dev/null || true
fi

if ip link show bat0 &>/dev/null; then
    ip addr flush dev bat0 2>/dev/null || true
    ip link set bat0 down 2>/dev/null || true
fi

# Restore WiFi adapter to managed mode
if [ -n "$IFACE" ] && [ "$IFACE" != "__PHYS_IFACE__" ] && ip link show "$IFACE" &>/dev/null; then
    log "Restoring $IFACE to managed mode..."

    ip link set "$IFACE" down 2>/dev/null || true
    sleep 1

    iw dev "$IFACE" ibss leave 2>/dev/null || true
    ip addr flush dev "$IFACE" 2>/dev/null || true

    if iw dev "$IFACE" set type managed 2>/dev/null; then
        log "Set $IFACE to managed mode via iw"
    elif iwconfig "$IFACE" mode managed 2>/dev/null; then
        log "Set $IFACE to managed mode via iwconfig"
    else
        warn "Could not set managed mode — driver may handle it on up"
    fi

    sleep 1

    ip link set "$IFACE" up 2>/dev/null || true
    sleep 1

    rfkill unblock wifi 2>/dev/null || true

    # Re-enable NetworkManager
    if command -v nmcli &>/dev/null; then
        nmcli device set "$IFACE" managed yes 2>/dev/null || true
        nmcli device connect "$IFACE" 2>/dev/null || true
        log "Re-enabled NetworkManager on $IFACE"
    fi

    mode=$(iw dev "$IFACE" info 2>/dev/null | grep "type" | awk '{print $2}')
    log "Interface $IFACE mode: $mode"
else
    warn "Interface $IFACE not found or not set"
fi

# Unload batman_adv
modprobe -r batman_adv 2>/dev/null || true

log "GCS mesh stopped. WiFi restored to managed mode."
