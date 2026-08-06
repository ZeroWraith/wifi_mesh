#!/bin/bash
# =============================================================================
# Batman-Adv Ad-Hoc Mode Setup Script
# =============================================================================
# This script configures batman-adv mesh network using Ad-hoc (IBSS) mode.
# It automatically detects if mesh point mode is available and uses it if so.
# Requires root privileges (run with sudo).
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.sh"
LOG_FILE="/var/log/mesh.log"

log() {
    echo -e "${GREEN}[MESH]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

# Load configuration
load_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        error "Configuration file not found: $CONFIG_FILE"
    fi
    
    source "$CONFIG_FILE"
    log "Loaded configuration from $CONFIG_FILE"
    
    if [ -z "$DRONE_IP" ]; then
        error "DRONE_IP not set in config.sh"
    fi
    
    if [ -z "$MESH_ID" ]; then
        error "MESH_ID not set in config.sh"
    fi
    
    info "Drone IP: $DRONE_IP"
    info "Mesh ID: $MESH_ID"
    info "Channel: ${MESH_CHANNEL:-6}"
}

# Detect physical WiFi interface
detect_interface() {
    if [ -n "$PHYS_IFACE" ] && ip link show "$PHYS_IFACE" &>/dev/null; then
        log "Using configured interface: $PHYS_IFACE"
        return
    fi
    
    log "Auto-detecting WiFi interface..."
    
    # Try to get interface from iw
    PHYS_IFACE=$(iw dev 2>/dev/null | grep "Interface" | awk '{print $2}' | head -n1)
    
    if [ -n "$PHYS_IFACE" ] && ip link show "$PHYS_IFACE" &>/dev/null; then
        log "Detected WiFi interface: $PHYS_IFACE"
        return
    fi
    
    # Try common interface names
    for iface in wlan0 wlP1p1s0 wlp2s0 wlp3s0 wlan1; do
        if ip link show "$iface" &>/dev/null; then
            PHYS_IFACE="$iface"
            log "Detected WiFi interface: $PHYS_IFACE"
            return
        fi
    done
    
    error "No WiFi interface found. Set PHYS_IFACE in config.sh or connect a WiFi adapter."
}

# Check if mesh point mode is supported
check_mesh_point_support() {
    log "Checking for mesh point mode support..."
    
    if iw phy 2>/dev/null | grep -q "mesh point"; then
        MESH_MODE="mesh_point"
        log "Mesh point mode SUPPORTED - will use 802.11s"
    else
        MESH_MODE="adhoc"
        log "Mesh point mode NOT supported - will use Ad-hoc (IBSS)"
    fi
    
    info "Mode: $MESH_MODE"
}

# Stop existing services
stop_existing() {
    log "Stopping existing network services..."
    
    # Stop NetworkManager from managing the interface
    if command -v nmcli &>/dev/null; then
        nmcli device set "$PHYS_IFACE" managed no 2>/dev/null || true
    fi
    
    # Kill any existing hostapd/wpa_supplicant
    pkill -f hostapd 2>/dev/null || true
    pkill -f wpa_supplicant 2>/dev/null || true
    
    # Remove existing batman interface if any
    batctl if del bat0 2>/dev/null || true
    
    # Set interface down
    ip link set "$PHYS_IFACE" down 2>/dev/null || true
    
    sleep 1
}

# Configure WiFi adapter
configure_wifi() {
    log "Configuring WiFi adapter..."
    
    ip link set "$PHYS_IFACE" up
}

# Setup mesh point mode (802.11s)
setup_mesh_point() {
    log "Setting up mesh point mode (802.11s)..."
    
    # Leave any existing network
    iw dev "$PHYS_IFACE" leave 2>/dev/null || true
    
    # Set channel first
    iw dev "$PHYS_IFACE" set channel "${MESH_CHANNEL:-6}" 2>/dev/null || true
    
    # Join mesh network
    iw dev "$PHYS_IFACE" mesh join "$MESH_ID" || error "Failed to join mesh network"
    
    log "Joined mesh network: $MESH_ID"
}

# Setup Ad-hoc mode (IBSS)
setup_adhoc() {
    log "Setting up Ad-hoc mode (IBSS)..."
    
    # Take interface down first
    ip link set "$PHYS_IFACE" down
    
    # Set mode to ad-hoc
    iwconfig "$PHYS_IFACE" mode ad-hoc 2>/dev/null || \
        iw dev "$PHYS_IFACE" set type ibss 2>/dev/null || \
        error "Failed to set Ad-hoc mode"
    
    # Set ESSID
    iwconfig "$PHYS_IFACE" essid "$MESH_ID" 2>/dev/null || \
        iw dev "$PHYS_IFACE" set ssid "$MESH_ID" 2>/dev/null || \
        error "Failed to set ESSID"
    
    # Set channel
    iwconfig "$PHYS_IFACE" channel "${MESH_CHANNEL:-6}" 2>/dev/null || \
        error "Failed to set channel"
    
    # Bring interface up
    ip link set "$PHYS_IFACE" up
    
    # Wait for interface to initialize
    sleep 2
    
    # Verify Ad-hoc mode
    if iwconfig "$PHYS_IFACE" 2>/dev/null | grep -q "Mode:Ad-Hoc"; then
        log "Ad-hoc mode configured successfully"
    else
        warn "Could not verify Ad-hoc mode, but continuing..."
    fi
}

# Setup batman-adv
setup_batman() {
    log "Setting up batman-adv..."
    
    # Load batman_adv module
    modprobe batman_adv || error "Failed to load batman_adv module"
    
    # Set routing algorithm
    if [ "${BATMAN_ROUTING:-BATMAN_V}" = "BATMAN_V" ]; then
        log "Using BATMAN_V routing algorithm"
        echo "BATMAN_V" > /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || true
    else
        log "Using BATMAN_IV routing algorithm"
        echo "BATMAN_IV" > /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || true
    fi
    
    # Wait for interface to be ready
    sleep 2
    
    # Create bat0 interface
    log "Creating bat0 interface..."
    batctl if add "$PHYS_IFACE" || error "Failed to create bat0 interface"
    
    # Wait for interface to be created
    sleep 2
    
    # Verify bat0 exists
    if ! ip link show bat0 &>/dev/null; then
        error "bat0 interface not created"
    fi
    
    log "bat0 interface created successfully"
}

# Configure IP address
configure_ip() {
    log "Configuring IP address..."
    
    # Remove any existing IP from bat0
    ip addr flush dev bat0 2>/dev/null || true
    
    # Set new IP address
    ip addr add "${DRONE_IP}/24" dev bat0 || error "Failed to set IP address"
    
    # Bring up bat0
    ip link set bat0 up || error "Failed to bring up bat0"
    
    log "IP address set: $DRONE_IP"
}

# Enable IP forwarding
enable_forwarding() {
    log "Enabling IP forwarding..."
    echo 1 > /proc/sys/net/ipv4/ip_forward
    
    # Make persistent
    if ! grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
    fi
}

# Verify setup
verify_setup() {
    log "Verifying mesh setup..."
    
    # Check bat0 interface
    if ! ip link show bat0 &>/dev/null; then
        error "bat0 interface not found"
    fi
    
    # Check IP address
    if ! ip addr show bat0 | grep -q "$DRONE_IP"; then
        error "IP address not configured on bat0"
    fi
    
    # Check batman-adv
    if ! batctl if | grep -q "$PHYS_IFACE"; then
        error "Physical interface not added to batman-adv"
    fi
    
    log "Mesh setup verified successfully!"
    
    echo ""
    info "========================================"
    info "Mesh Network Status:"
    info "========================================"
    info "Interface: $PHYS_IFACE"
    info "Mode: $MESH_MODE"
    info "bat0 IP: $DRONE_IP"
    info "Mesh ID: $MESH_ID"
    info "Channel: ${MESH_CHANNEL:-6}"
    echo ""
    info "Batman-adv interfaces:"
    batctl if
    echo ""
    info "Batman-adv originators (will populate as neighbors join):"
    batctl o 2>/dev/null || echo "  (waiting for neighbors...)"
    echo ""
}

# Main setup
main() {
    echo "=========================================="
    echo " Batman-Adv Mesh Setup"
    echo " Mode: Auto-detect (Mesh Point / Ad-hoc)"
    echo "=========================================="
    echo ""
    
    load_config
    detect_interface
    check_mesh_point_support
    stop_existing
    configure_wifi
    
    # Use appropriate mode
    if [ "$MESH_MODE" = "mesh_point" ]; then
        setup_mesh_point
    else
        setup_adhoc
    fi
    
    setup_batman
    configure_ip
    enable_forwarding
    verify_setup
    
    echo ""
    echo "=========================================="
    log "Setup complete! Mesh is running."
    echo ""
    echo "Next steps:"
    echo "  1. Check status: sudo ./mesh_status.sh"
    echo "  2. Test with another node on the same mesh"
    echo "=========================================="
}

main "$@"
