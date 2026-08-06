#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Mesh Setup Script
# =============================================================================
# This script configures the batman-adv mesh network on this drone.
# Run this once after install_packages.sh, or whenever you change settings.
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

log() {
    echo -e "${GREEN}[MESH]${NC} $1"
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
    
    # Validate required settings
    if [ -z "$DRONE_IP" ]; then
        error "DRONE_IP not set in config.sh"
    fi
    
    if [ -z "$MESH_IFACE" ]; then
        error "MESH_IFACE not set in config.sh"
    fi
    
    if [ -z "$MESH_ID" ]; then
        error "MESH_ID not set in config.sh"
    fi
    
    info "Drone IP: $DRONE_IP"
    info "Mesh Interface: $MESH_IFACE"
    info "Mesh ID: $MESH_ID"
    info "Channel: $MESH_CHANNEL"
}

# Detect physical interface
detect_interface() {
    if [ -n "$PHYS_IFACE" ]; then
        log "Using configured interface: $PHYS_IFACE"
        return
    fi
    
    log "Auto-detecting WiFi interface..."
    
    # Try common interface names
    for iface in wlan0 wlan1 wlp2s0 wlp3s0; do
        if ip link show "$iface" &>/dev/null; then
            PHYS_IFACE="$iface"
            log "Detected WiFi interface: $PHYS_IFACE"
            return
        fi
    done
    
    # Try to find any wireless interface
    PHYS_IFACE=$(iw dev 2>/dev/null | grep "Interface" | awk '{print $2}' | head -n1)
    
    if [ -n "$PHYS_IFACE" ]; then
        log "Detected WiFi interface: $PHYS_IFACE"
    else
        error "No WiFi interface found. Set PHYS_IFACE in config.sh."
    fi
}

# Stop existing services
stop_existing() {
    log "Stopping existing mesh services..."
    
    # Stop NetworkManager from managing the interface
    if command -v nmcli &>/dev/null; then
        nmcli device set "$PHYS_IFACE" managed no 2>/dev/null || true
    fi
    
    # Kill any existing hostapd
    pkill -f hostapd 2>/dev/null || true
    
    # Kill any existing wpa_supplicant
    pkill -f wpa_supplicant 2>/dev/null || true
    
    # Remove existing batman interface if any
    batctl if del bat0 2>/dev/null || true
    
    # Set interface down
    ip link set "$PHYS_IFACE" down 2>/dev/null || true
    
    sleep 1
}

# Configure WiFi adapter
configure_wifi() {
    log "Configuring WiFi adapter for mesh..."
    
    # Set interface up
    ip link set "$PHYS_IFACE" up
    
    # Set WiFi driver options if specified
    if [ -n "$WIFI_DRIVER_OPTIONS" ]; then
        log "Applying WiFi driver options: $WIFI_DRIVER_OPTIONS"
        # This varies by driver, common methods:
        # - modprobe options: echo "options $DRIVER $OPTIONS" > /etc/modprobe.d/mesh.conf
        # - iw dev set parameters
    fi
    
    # Set WiFi channel
    log "Setting WiFi channel to $MESH_CHANNEL..."
    iw dev "$PHYS_IFACE" set channel "$MESH_CHANNEL" "$MESH_BAND" 2>/dev/null || \
        iwconfig "$PHYS_IFACE" channel "$MESH_CHANNEL" 2>/dev/null || \
        warn "Could not set channel via iw/iwconfig"
}

# Create batman-adv interface
setup_batman() {
    log "Setting up batman-adv..."
    
    # Ensure batman_adv module is loaded
    modprobe batman_adv || error "Failed to load batman_adv module"
    
    # Set routing algorithm
    if [ "$BATMAN_ROUTING" = "BATMAN_V" ]; then
        log "Using BATMAN_V routing algorithm"
        echo "BATMAN_V" > /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || true
    else
        log "Using BATMAN_IV routing algorithm"
        echo "BATMAN_IV" > /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || true
    fi
    
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

# Configure mesh point mode
configure_mesh_point() {
    log "Configuring mesh point mode..."
    
    # Leave any existing network
    iw dev "$PHYS_IFACE" leave 2>/dev/null || true
    
    # Join mesh network
    iw dev "$PHYS_IFACE" mesh join "$MESH_ID" frequency "$MESH_CHANNEL" || \
        error "Failed to join mesh network"
    
    log "Joined mesh network: $MESH_ID"
}

# Configure IP address
configure_ip() {
    log "Configuring IP address..."
    
    # Remove any existing IP from bat0
    ip addr flush dev bat0 2>/dev/null || true
    
    # Set new IP address
    ip addr add "${DRONE_IP}/24" dev bat0 || error "Failed to set IP address"
    
    # Set broadcast address
    ip link set bat0 up || error "Failed to bring up bat0"
    
    log "IP address set: $DRONE_IP"
}

# Configure gateway (if enabled)
configure_gateway() {
    if [ "$GATEWAY_MODE" = "off" ] || [ -z "$GATEWAY_MODE" ]; then
        return
    fi
    
    log "Configuring gateway mode: $GATEWAY_MODE"
    
    if [ "$GATEWAY_MODE" = "server" ]; then
        # Server mode: share internet with mesh
        batctl gw server "${GW_DOWNLOAD}/${GW_UPLOAD}" || warn "Failed to set gateway server"
        
        # Enable IP forwarding
        echo 1 > /proc/sys/net/ipv4/ip_forward
        
        # Configure NAT if external interface exists
        if [ -n "$EXTERNAL_IFACE" ]; then
            iptables -t nat -A POSTROUTING -o "$EXTERNAL_IFACE" -j MASQUERADE
            iptables -A FORWARD -i bat0 -o "$EXTERNAL_IFACE" -j ACCEPT
            iptables -A FORWARD -i "$EXTERNAL_IFACE" -o bat0 -m state --state RELATED,ESTABLISHED -j ACCEPT
            log "NAT configured for internet sharing"
        fi
    elif [ "$GATEWAY_MODE" = "client" ]; then
        # Client mode: use gateway for internet
        batctl gw client || warn "Failed to set gateway client"
    fi
}

# Configure alfred (for GPS distribution)
configure_alfred() {
    log "Configuring alfred..."
    
    # Start alfred if available
    if command -v alfred &>/dev/null; then
        alfred -i bat0 -m "/var/run/alfred.sock" &
        log "alfred started"
    else
        warn "alfred not installed, skipping GPS distribution setup"
    fi
}

# Enable IP forwarding for mesh routing
enable_forwarding() {
    log "Enabling IP forwarding..."
    
    # Enable IPv4 forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
    
    # Make persistent
    if ! grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
    fi
}

# Configure firewall (allow mesh traffic)
configure_firewall() {
    log "Configuring firewall..."
    
    # Check if ufw is available
    if command -v ufw &>/dev/null; then
        # Allow all traffic on bat0
        ufw allow in on bat0 2>/dev/null || true
        ufw allow out on bat0 2>/dev/null || true
        log "UFW rules added for bat0"
    fi
    
    # Check if firewalld is available
    if command -v firewall-cmd &>/dev/null; then
        firewall-cmd --zone=trusted --add-interface=bat0 --permanent 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
        log "Firewalld rules added for bat0"
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
    
    # Check mesh status
    if batctl o | grep -q "Batman"; then
        log "Mesh setup verified successfully!"
    else
        warn "Mesh may take a few seconds to discover neighbors"
    fi
    
    # Show current status
    echo ""
    info "Current mesh status:"
    batctl if
    echo ""
    batctl o
    echo ""
    ip addr show bat0
}

# Create startup script
create_startup_script() {
    log "Creating startup script..."
    
    cat > "${SCRIPT_DIR}/start_mesh.sh" << 'STARTUP_EOF'
#!/bin/bash
# Start Batman-Adv Mesh Network
# Run this script at boot or manually to start the mesh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Load modules
modprobe batman_adv

# Start mesh
"${SCRIPT_DIR}/setup_mesh.sh"

echo "Mesh network started!"
STARTUP_EOF
    
    chmod +x "${SCRIPT_DIR}/start_mesh.sh"
    log "Created start_mesh.sh"
}

# Main setup
main() {
    echo "=========================================="
    echo " Batman-Adv Drone Mesh - Setup Script"
    echo "=========================================="
    echo ""
    
    load_config
    detect_interface
    stop_existing
    configure_wifi
    setup_batman
    configure_mesh_point
    configure_ip
    configure_gateway
    enable_forwarding
    configure_firewall
    configure_alfred
    verify_setup
    create_startup_script
    
    echo ""
    echo "=========================================="
    log "Mesh setup complete!"
    echo ""
    echo "This drone is now part of the mesh network."
    echo "IP Address: $DRONE_IP"
    echo "Mesh Interface: bat0"
    echo ""
    echo "To verify connectivity, ping another drone:"
    echo "  ping 10.0.0.2"
    echo ""
    echo "To see mesh neighbors:"
    echo "  batctl o"
    echo ""
    echo "To check gateway status:"
    echo "  batctl gw"
    echo "=========================================="
}

main "$@"
