#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Uninstall Script
# =============================================================================
# This script completely removes the mesh configuration and restores defaults.
# Requires root privileges.
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

INSTALL_DIR="/opt/mesh"
LOG_FILE="/var/log/mesh.log"

log() {
    echo -e "${GREEN}[UNINSTALL]${NC} $1"
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

# Confirmation prompt
echo -e "${RED}WARNING: This will completely remove the mesh network configuration.${NC}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Uninstall cancelled."
    exit 0
fi

log "Starting mesh network uninstallation..."

# Stop mesh if running
log "Stopping mesh network..."
if [ -f "$INSTALL_DIR/stop_mesh.sh" ]; then
    "$INSTALL_DIR/stop_mesh.sh" 2>/dev/null || true
fi

# Stop and disable systemd service
log "Removing systemd service..."
systemctl stop batman-mesh.service 2>/dev/null || true
systemctl disable batman-mesh.service 2>/dev/null || true
rm -f /etc/systemd/system/batman-mesh.service
systemctl daemon-reload

# Kill any running mesh processes
log "Stopping mesh processes..."
pkill -f alfred 2>/dev/null || true
pkill -f hostapd 2>/dev/null || true
pkill -f wpa_supplicant 2>/dev/null || true

# Remove batman interfaces
log "Removing mesh interfaces..."
if command -v batctl &>/dev/null; then
    batctl if del bat0 2>/dev/null || true
fi

# Take down physical interface
for iface in wlan0 wlan1 wlp2s0 wlp3s0; do
    if ip link show "$iface" &>/dev/null; then
        ip link set "$iface" down 2>/dev/null || true
        iw dev "$iface" leave 2>/dev/null || true
    fi
done

# Unload kernel modules
log "Unloading kernel modules..."
rmmod batman_adv 2>/dev/null || true
rmmod cfg80211 2>/dev/null || true
rmmod mac80211 2>/dev/null || true

# Remove modules-load config
log "Removing boot module configuration..."
rm -f /etc/modules-load.d/batman-adv.conf

# Restore IP forwarding
log "Restoring network settings..."
if grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
    sed -i '/net.ipv4.ip_forward = 1/d' /etc/sysctl.conf
    sysctl -p 2>/dev/null || true
fi

# Remove iptables rules
log "Removing firewall rules..."
if command -v iptables &>/dev/null; then
    # Try to remove rules we may have added
    iptables -t nat -D POSTROUTING -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i bat0 -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -o bat0 -j ACCEPT 2>/dev/null || true
fi

# Remove UFW rules
if command -v ufw &>/dev/null; then
    ufw delete allow in on bat0 2>/dev/null || true
    ufw delete allow out on bat0 2>/dev/null || true
fi

# Remove firewalld rules
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --zone=trusted --remove-interface=bat0 --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi

# Remove installed files
log "Removing installed files..."
rm -rf "$INSTALL_DIR"

# Remove log file
rm -f "$LOG_FILE"

# Remove NetworkManager conflicts if we added them
if command -v nmcli &>/dev/null; then
    nmcli device set wlan0 managed 2>/dev/null || true
fi

log "Uninstallation complete!"
echo ""
echo "=========================================="
echo "  Mesh network has been completely removed"
echo "=========================================="
echo ""
echo "The system has been restored to its original state."
echo "All mesh configuration files, services, and network"
echo "settings have been removed."
echo ""
echo "You may need to reboot to ensure all changes take effect:"
echo "  sudo reboot"
echo "=========================================="
