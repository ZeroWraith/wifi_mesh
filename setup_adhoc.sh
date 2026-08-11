#!/bin/bash
# =============================================================================
# Batman-Adv Ad-Hoc Mode Setup Script
# =============================================================================
# This script configures batman-adv mesh network using Ad-hoc (IBSS) mode.
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

log()  { echo -e "${GREEN}[MESH]${NC} $1"; echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

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

    [ -z "$DRONE_IP" ]   && error "DRONE_IP not set in config.sh"
    [ -z "$MESH_ID" ]    && error "MESH_ID not set in config.sh"
    [ -z "$MESH_BSSID" ] && error "MESH_BSSID not set in config.sh"

    info "Drone IP: $DRONE_IP"
    info "Mesh ID: $MESH_ID"
    info "BSSID: $MESH_BSSID"
    info "Channel: ${MESH_CHANNEL:-6}"
}

# Detect physical WiFi interface
detect_interface() {
    if [ -n "$PHYS_IFACE" ] && ip link show "$PHYS_IFACE" &>/dev/null; then
        log "Using configured interface: $PHYS_IFACE"
        return
    fi
    log "Auto-detecting WiFi interface..."
    PHYS_IFACE=$(iw dev 2>/dev/null | grep "Interface" | awk '{print $2}' | head -n1)
    if [ -n "$PHYS_IFACE" ] && ip link show "$PHYS_IFACE" &>/dev/null; then
        log "Detected WiFi interface: $PHYS_IFACE"
        return
    fi
    for iface in wlan0 wlP1p1s0 wlp2s0 wlp3s0 wlan1; do
        if ip link show "$iface" &>/dev/null; then
            PHYS_IFACE="$iface"
            log "Detected WiFi interface: $PHYS_IFACE"
            return
        fi
    done
    error "No WiFi interface found. Set PHYS_IFACE in config.sh or connect a WiFi adapter."
}

# Stop existing services
stop_existing() {
    log "Stopping existing network services..."

    # Kill any hotspot/AP that NetworkManager may auto-restart
    pkill -f hostapd 2>/dev/null || true
    pkill -f wpa_supplicant 2>/dev/null || true
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop wpa_supplicant 2>/dev/null || true

    # Disable NetworkManager from managing this interface
    if command -v nmcli &>/dev/null; then
        nmcli device set "$PHYS_IFACE" managed no 2>/dev/null || true
        # Also disconnect to prevent auto-reconnect/hotspot
        nmcli device disconnect "$PHYS_IFACE" 2>/dev/null || true
    fi

    # Clean up any existing mesh state
    batctl if del bat0 2>/dev/null || true
    ip addr flush dev bat0 2>/dev/null || true
    ip link set bat0 down 2>/dev/null || true

    # Leave any existing IBSS/mesh network and flush IPs
    ip addr flush dev "$PHYS_IFACE" 2>/dev/null || true
    iw dev "$PHYS_IFACE" ibss leave 2>/dev/null || true
    ip link set "$PHYS_IFACE" down 2>/dev/null || true
    sleep 1
}

# Check WiFi adapter health (no driver reload - that leaks phy devices)
check_adapter_health() {
    log "Checking WiFi adapter health..."

    local txpower
    txpower=$(iw dev "$PHYS_IFACE" info 2>/dev/null | grep "txpower" | awk '{print $2}')

    if [ -z "$txpower" ]; then
        warn "Could not read txpower, skipping check"
        return
    fi

    log "Current txpower: ${txpower} dBm"

    if [ "$txpower" = "-100.00" ] || [ "$txpower" = "-100" ]; then
        warn "txpower is ${txpower} dBm - known Realtek quirk in managed mode, not a real problem"
        warn "If tx_dropped increases rapidly after IBSS join, the adapter may need a power-cycle"
    fi

    log "Adapter check complete: txpower=${txpower} dBm"
}

# Setup Ad-hoc mode (IBSS) with fixed BSSID
setup_ibss() {
    log "Setting up Ad-hoc mode (IBSS)..."

    local freq=$((2412 + (${MESH_CHANNEL:-6} - 1) * 5))

    # Ensure rfkill is unblocked
    rfkill unblock wifi 2>/dev/null || true

    # Stop NetworkManager from interfering
    if command -v nmcli &>/dev/null; then
        nmcli device set "$PHYS_IFACE" managed no 2>/dev/null || true
        nmcli device disconnect "$PHYS_IFACE" 2>/dev/null || true
    fi

    # Step 1: Interface must be DOWN to change type
    ip link set "$PHYS_IFACE" down 2>/dev/null || true
    sleep 1

    # Step 2: Set interface type to IBSS
    log "Setting interface type to IBSS..."
    iw dev "$PHYS_IFACE" set type ibss || error "Failed to set IBSS mode"

    # Step 3: Bring interface UP
    ip link set "$PHYS_IFACE" up
    sleep 1

    # Step 4: Join with FIXED BSSID so both nodes are in the same IBSS
    log "Joining IBSS: $MESH_ID on channel ${MESH_CHANNEL:-6} (${freq} MHz) BSSID $MESH_BSSID..."

    # Try iw first with fixed-freq, then fall back to iwconfig for drivers that ignore it
    local joined_bssid=""
    iw dev "$PHYS_IFACE" ibss join "$MESH_ID" "$freq" fixed-freq "$MESH_BSSID" 2>/dev/null || true
    sleep 2

    # Check if the BSSID matches
    joined_bssid=$(iw dev "$PHYS_IFACE" link 2>/dev/null | grep -i "IBSS\|Joined" | awk '{print $NF}' | tr '[:lower:]' '[:upper:]')
    local target_bssid=$(echo "$MESH_BSSID" | tr '[:lower:]' '[:upper:]')

    if [ "$joined_bssid" = "$target_bssid" ]; then
        log "IBSS joined with correct BSSID: $MESH_BSSID"
    else
        warn "iw fixed-freq ignored by driver (got $joined_bssid, expected $target_bssid)"
        warn "Falling back to iwconfig to force BSSID..."

        ip link set "$PHYS_IFACE" down 2>/dev/null || true
        sleep 1
        iwconfig "$PHYS_IFACE" mode ad-hoc 2>/dev/null || true
        ip link set "$PHYS_IFACE" up 2>/dev/null || true
        sleep 1
        iwconfig "$PHYS_IFACE" essid "$MESH_ID" channel "${MESH_CHANNEL:-6}" ap "$MESH_BSSID" 2>/dev/null \
            || error "Failed to join IBSS with iwconfig"
        sleep 2

        joined_bssid=$(iw dev "$PHYS_IFACE" link 2>/dev/null | grep -i "IBSS\|Joined" | awk '{print $NF}' | tr '[:lower:]' '[:upper:]')
        if [ "$joined_bssid" = "$target_bssid" ]; then
            log "IBSS joined via iwconfig with correct BSSID: $MESH_BSSID"
        else
            warn "BSSID still mismatched ($joined_bssid vs $target_bssid), continuing anyway..."
        fi
    fi

    # Verify
    if iw dev "$PHYS_IFACE" link 2>/dev/null | grep -qi "IBSS\|Joined"; then
        log "IBSS network joined successfully"
    else
        warn "Could not verify IBSS join, but continuing..."
    fi

    info "Mode: IBSS (Ad-hoc)"
}

# Setup batman-adv with correct routing algo
setup_batman() {
    log "Setting up batman-adv..."

    # Ensure rfkill is still unblocked
    rfkill unblock wifi 2>/dev/null || true

    # Unload module if already loaded (to apply routing_algo at load time)
    rmmod batman_adv 2>/dev/null || true
    sleep 1

    # Load module with routing algo parameter
    local algo="${BATMAN_ROUTING:-BATMAN_V}"
    log "Loading batman_adv with routing_algo=$algo..."
    modprobe batman_adv || error "Failed to load batman_adv module"

    # Verify algo was applied
    local current_algo
    current_algo=$(cat /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || echo "unknown")
    if [ "$current_algo" != "$algo" ]; then
        warn "Routing algo is $current_algo, expected $algo. Trying sysfs write..."
        echo "$algo" > /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || true
        current_algo=$(cat /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || echo "unknown")
        if [ "$current_algo" != "$algo" ]; then
            warn "Could not set $algo, using $current_algo"
        fi
    fi
    log "Routing algorithm: $current_algo"

    sleep 2

    # Create bat0 interface
    log "Creating bat0 interface..."
    batctl if add "$PHYS_IFACE" || error "Failed to create bat0 interface"
    sleep 2

    if ! ip link show bat0 &>/dev/null; then
        error "bat0 interface not created"
    fi
    log "bat0 interface created successfully"
}

# Configure IP address
configure_ip() {
    log "Configuring IP address..."
    ip addr flush dev bat0 2>/dev/null || true
    ip addr add "${DRONE_IP}/24" dev bat0 || error "Failed to set IP address"
    ip link set bat0 up || error "Failed to bring up bat0"
    log "IP address set: $DRONE_IP"
}

# Enable IP forwarding and firewall
enable_forwarding() {
    log "Enabling IP forwarding..."
    echo 1 > /proc/sys/net/ipv4/ip_forward
    if ! grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
    fi

    # Open firewall for batman-adv traffic
    log "Configuring firewall for batman-adv..."
    if command -v iptables &>/dev/null; then
        iptables -I INPUT -i bat0 -j ACCEPT 2>/dev/null || true
        iptables -I FORWARD -i bat0 -j ACCEPT 2>/dev/null || true
        iptables -I FORWARD -o bat0 -j ACCEPT 2>/dev/null || true
    fi
    if command -v ufw &>/dev/null; then
        ufw allow in on bat0 2>/dev/null || true
        ufw allow out on bat0 2>/dev/null || true
    fi
}

# Verify setup
verify_setup() {
    log "Verifying mesh setup..."
    if ! ip link show bat0 &>/dev/null; then error "bat0 interface not found"; fi
    if ! ip addr show bat0 | grep -q "$DRONE_IP"; then error "IP not configured on bat0"; fi
    if ! batctl if | grep -q "$PHYS_IFACE"; then error "Interface not added to batman-adv"; fi

    log "Mesh setup verified successfully!"
    echo ""
    info "========================================"
    info "Mesh Network Status:"
    info "========================================"
    info "Interface: $PHYS_IFACE"
    info "Mode: IBSS (Ad-hoc)"
    info "BSSID: $MESH_BSSID"
    info "bat0 IP: $DRONE_IP"
    info "Mesh ID: $MESH_ID"
    info "Channel: ${MESH_CHANNEL:-6}"
    info "Routing: $(cat /sys/module/batman_adv/parameters/routing_algo 2>/dev/null)"
    echo ""
    info "Batman-adv interfaces:"
    batctl if
    echo ""
    info "Batman-adv originators (will populate as neighbors join):"
    batctl o 2>/dev/null || echo "  (waiting for neighbors...)"
    echo ""
}

# Main
main() {
    echo "=========================================="
    echo " Batman-Adv Mesh Setup"
    echo " Mode: Ad-hoc (IBSS) + Batman-Adv"
    echo "=========================================="
    echo ""

    load_config
    detect_interface
    stop_existing
    check_adapter_health
    setup_ibss
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
