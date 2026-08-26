#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Complete Uninstall Script
# =============================================================================
# This script completely removes the mesh network configuration and restores
# the system to its original state. It handles both the meshd daemon and the
# legacy batman-mesh setup.
# Requires root privileges.
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/mesh"
LOG_FILE="/var/log/mesh.log"
CONFIG_FILE="/opt/mesh/config/mesh.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { echo -e "${GREEN}[UNINSTALL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# -----------------------------------------------------------------------------
# Root check
# -----------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

# -----------------------------------------------------------------------------
# Confirmation prompt (can be skipped with --force)
# -----------------------------------------------------------------------------
FORCE=false
for arg in "$@"; do
    case $arg in
        --force|-f) FORCE=true ;;
        -h|--help)
            echo "Usage: $0 [--force|-f] [--help|-h]"
            echo "  --force    Skip confirmation prompt"
            echo "  --help     Show this help"
            exit 0
            ;;
    esac
done

if [[ "$FORCE" != "true" ]]; then
    echo -e "${RED}WARNING: This will completely remove the mesh network configuration.${NC}"
    echo ""
    echo "The following will be removed:"
    echo "  - systemd services (meshd.service, batman-mesh.service)"
    echo "  - batman-adv kernel module and interfaces (bat0, bat1, etc.)"
    echo "  - WiFi mesh/IBSS configuration on all wireless interfaces"
    echo "  - iptables / nftables / ufw / firewalld rules for mesh"
    echo "  - IP forwarding sysctl settings"
    echo "  - /opt/mesh installation directory"
    echo "  - /etc/modules-load.d/batman-adv.conf"
    echo "  - /etc/mesh/token.env (if exists)"
    echo "  - NetworkManager device unmanaged settings"
    echo "  - alfred, batadv-vis, gpsd processes"
    echo "  - Log files in /var/log/mesh.log"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi
fi

log "Starting complete mesh network uninstallation..."

# -----------------------------------------------------------------------------
# Stop and disable systemd services
# -----------------------------------------------------------------------------
log "Stopping and disabling systemd services..."

# meshd (new Python daemon)
systemctl stop meshd.service 2>/dev/null || true
systemctl disable meshd.service 2>/dev/null || true
rm -f /etc/systemd/system/meshd.service

# batman-mesh (legacy shell script service)
systemctl stop batman-mesh.service 2>/dev/null || true
systemctl disable batman-mesh.service 2>/dev/null || true
rm -f /etc/systemd/system/batman-mesh.service

# alfred/batadv-vis if installed as services
systemctl stop alfred.service 2>/dev/null || true
systemctl disable alfred.service 2>/dev/null || true
rm -f /etc/systemd/system/alfred.service

systemctl daemon-reload

# -----------------------------------------------------------------------------
# Kill mesh-related processes
# -----------------------------------------------------------------------------
log "Stopping mesh-related processes..."

# Supervised processes from meshd
pkill -f "gst-launch" 2>/dev/null || true
pkill -f "alfred-gpsd" 2>/dev/null || true
pkill -f "python.*meshd" 2>/dev/null || true

# Legacy processes
pkill -f alfred 2>/dev/null || true
pkill -f batadv-vis 2>/dev/null || true
pkill -f hostapd 2>/dev/null || true
pkill -f wpa_supplicant 2>/dev/null || true
pkill -f gpsd 2>/dev/null || true

# Give processes time to terminate
sleep 1

# -----------------------------------------------------------------------------
# Remove batman-adv interfaces
# -----------------------------------------------------------------------------
log "Removing batman-adv interfaces..."

# Delete all batman interfaces
for bat_iface in bat0 bat1 bat2 bat3 bat4; do
    if ip link show "$bat_iface" &>/dev/null; then
        log "Removing $bat_iface..."
        batctl if del "$bat_iface" 2>/dev/null || true
        ip link set "$bat_iface" down 2>/dev/null || true
        ip addr flush dev "$bat_iface" 2>/dev/null || true
    fi
done

# -----------------------------------------------------------------------------
# Clean up physical wireless interfaces
# -----------------------------------------------------------------------------
log "Cleaning up wireless interfaces..."

# Get all wireless interfaces
for iface in $(iw dev 2>/dev/null | awk '/Interface/ {print $2}'); do
    if [[ -n "$iface" ]]; then
        log "Cleaning $iface..."
        # Leave any mesh/IBSS network
        iw dev "$iface" mesh leave 2>/dev/null || true
        iw dev "$iface" ibss leave 2>/dev/null || true
        # Bring down
        ip link set "$iface" down 2>/dev/null || true
        # Reset to managed mode if possible
        iw dev "$iface" set type managed 2>/dev/null || true
        # Bring back up
        ip link set "$iface" up 2>/dev/null || true
    fi
done

# Common interface names (fallback)
for iface in wlan0 wlan1 wlp2s0 wlp3s0 wlx*; do
    if ip link show "$iface" &>/dev/null; then
        iw dev "$iface" mesh leave 2>/dev/null || true
        iw dev "$iface" ibss leave 2>/dev/null || true
        ip link set "$iface" down 2>/dev/null || true
        iw dev "$iface" set type managed 2>/dev/null || true
        ip link set "$iface" up 2>/dev/null || true
    fi
done

# -----------------------------------------------------------------------------
# Unload kernel modules
# -----------------------------------------------------------------------------
log "Unloading kernel modules..."

# Try to unload batman-adv (may fail if in use)
for module in batman_adv cfg80211 mac80211 8021q; do
    if lsmod | grep -q "^${module}"; then
        log "Unloading $module..."
        rmmod "$module" 2>/dev/null || warn "Could not unload $module (may be in use)"
    fi
done

# -----------------------------------------------------------------------------
# Remove module-load configuration
# -----------------------------------------------------------------------------
log "Removing module-load configuration..."
rm -f /etc/modules-load.d/batman-adv.conf
rm -f /etc/modules-load.d/mesh.conf

# -----------------------------------------------------------------------------
# Restore IP forwarding
# -----------------------------------------------------------------------------
log "Restoring IP forwarding..."
if grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
    sed -i '/net.ipv4.ip_forward = 1/d' /etc/sysctl.conf
    sysctl -p 2>/dev/null || true
fi
# Also ensure it's off immediately
echo 0 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true

# -----------------------------------------------------------------------------
# Remove iptables / nftables rules
# -----------------------------------------------------------------------------
log "Removing firewall rules..."

# iptables cleanup - try to remove all rules we might have added
if command -v iptables &>/dev/null; then
    # NAT rules
    for ext_iface in eth0 eth1 ens33 ens34 enp0s3 enp0s8; do
        iptables -t nat -D POSTROUTING -o "$ext_iface" -j MASQUERADE 2>/dev/null || true
    done
    iptables -t nat -D POSTROUTING -j MASQUERADE 2>/dev/null || true

    # FORWARD rules
    for bat_iface in bat0 bat1 bat2 bat3 bat4; do
        iptables -D FORWARD -i "$bat_iface" -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -o "$bat_iface" -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i "$bat_iface" -o "$bat_iface" -j ACCEPT 2>/dev/null || true
    done
    iptables -D FORWARD -i bat0 -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -o bat0 -j ACCEPT 2>/dev/null || true

    # Related/established rules
    iptables -D FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
fi

# nftables cleanup
if command -v nft &>/dev/null; then
    nft flush ruleset 2>/dev/null || true
    # Note: This flushes ALL nftables rules. If you have other rules, 
    # you may want to be more selective.
fi

# UFW cleanup
if command -v ufw &>/dev/null; then
    for bat_iface in bat0 bat1 bat2 bat3 bat4; do
        ufw delete allow in on "$bat_iface" 2>/dev/null || true
        ufw delete allow out on "$bat_iface" 2>/dev/null || true
    done
    ufw delete allow in on bat0 2>/dev/null || true
    ufw delete allow out on bat0 2>/dev/null || true
fi

# firewalld cleanup
if command -v firewall-cmd &>/dev/null; then
    for bat_iface in bat0 bat1 bat2 bat3 bat4; do
        firewall-cmd --zone=trusted --remove-interface="$bat_iface" --permanent 2>/dev/null || true
    done
    firewall-cmd --zone=trusted --remove-interface=bat0 --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Restore NetworkManager
# -----------------------------------------------------------------------------
log "Restoring NetworkManager management..."
if command -v nmcli &>/dev/null; then
    for iface in $(iw dev 2>/dev/null | awk '/Interface/ {print $2}'); do
        if [[ -n "$iface" ]]; then
            nmcli device set "$iface" managed yes 2>/dev/null || true
        fi
    done
    # Common interface names
    for iface in wlan0 wlan1 wlp2s0 wlp3s0; do
        nmcli device set "$iface" managed yes 2>/dev/null || true
    done
fi

# -----------------------------------------------------------------------------
# Remove installed files
# -----------------------------------------------------------------------------
log "Removing installed files..."

# /opt/mesh directory
rm -rf "$INSTALL_DIR"

# Config files that may have been created elsewhere
rm -f /etc/mesh/token.env
rm -f /etc/mesh/management.token

# -----------------------------------------------------------------------------
# Remove log files
# -----------------------------------------------------------------------------
log "Removing log files..."
rm -f "$LOG_FILE"
rm -f /var/log/mesh-*.log

# -----------------------------------------------------------------------------
# Remove cron jobs if any
# -----------------------------------------------------------------------------
log "Removing cron entries..."
crontab -l 2>/dev/null | grep -v "mesh" | crontab - 2>/dev/null || true

# -----------------------------------------------------------------------------
# Remove modprobe.d entries
# -----------------------------------------------------------------------------
log "Removing modprobe.d entries..."
rm -f /etc/modprobe.d/mesh.conf
rm -f /etc/modprobe.d/mesh-radio.conf
rm -f /etc/modprobe.d/batman-adv.conf

# -----------------------------------------------------------------------------
# Remove alfred socket
# -----------------------------------------------------------------------------
log "Removing alfred socket..."
rm -f /var/run/alfred.sock

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
log "Uninstallation complete!"

echo ""
echo "=========================================="
echo "  Mesh network has been completely removed"
echo "=========================================="
echo ""
echo "The following have been cleaned up:"
echo "  ✓ systemd services (meshd, batman-mesh, alfred)"
echo "  ✓ batman-adv interfaces (bat0, bat1, ...)"
echo "  ✓ Wireless mesh/IBSS configuration"
echo "  ✓ iptables/nftables/ufw/firewalld rules"
echo "  ✓ IP forwarding (sysctl)"
echo "  ✓ Kernel module autoload (/etc/modules-load.d/)"
echo "  ✓ /opt/mesh installation directory"
echo "  ✓ Configuration and token files"
echo "  ✓ NetworkManager device settings"
echo "  ✓ Log files"
echo "  ✓ Cron entries"
echo "  ✓ modprobe.d entries"
echo ""
echo "You may need to reboot to ensure all kernel modules are fully reset:"
echo "  sudo reboot"
echo ""
echo "=========================================="