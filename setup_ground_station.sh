#!/bin/bash
# =============================================================================
# Batman-Adv Ground Station Setup Script
# =============================================================================
# Sets up batman-adv in ad-hoc mode on an Ubuntu ground station PC.
# Installs all dependencies, configures mesh, and starts the web dashboard.
# Requires root privileges (run with sudo).
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="${SCRIPT_DIR}/mesh_dashboard"
LOG_FILE="/var/log/mesh.log"

# Ground station configuration
GCS_IP="10.0.0.100"
MESH_ID="drone-mesh"
MESH_BSSID="02:12:34:56:78:9a"
MESH_CHANNEL=6
MESH_ESSID="drone-mesh"

log()  { echo -e "${GREEN}[GCS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

# ---- Detect WiFi adapter ----
detect_wifi() {
    log "Detecting WiFi adapter..."
    PHYS_IFACE=$(iw dev 2>/dev/null | grep "Interface" | awk '{print $2}' | head -n1)
    if [ -z "$PHYS_IFACE" ]; then
        for iface in wlp0s20f3 wlp2s0 wlp3s0 wlan0 wlan1; do
            if ip link show "$iface" &>/dev/null 2>&1; then
                PHYS_IFACE="$iface"
                break
            fi
        done
    fi
    if [ -z "$PHYS_IFACE" ]; then
        error "No WiFi adapter found. Plug in a USB WiFi adapter or check your interface name."
    fi
    info "Using WiFi adapter: $PHYS_IFACE"
}

# ---- Install packages ----
install_packages() {
    log "Updating package lists..."
    apt-get update -qq

    log "Installing required packages..."
    apt-get install -y \
        batctl \
        alfred \
        iw \
        wpasupplicant \
        hostapd \
        bridge-utils \
        net-tools \
        iproute2 \
        python3 \
        python3-pip \
        python3-venv \
        gpsd \
        gpsd-clients \
        build-essential \
        git || true

    # Check if batman_adv module is available
    if ! modinfo batman_adv &>/dev/null 2>&1; then
        warn "batman_adv module not found in kernel. Installing linux-modules-extra..."
        apt-get install -y linux-modules-extra-$(uname -r) 2>/dev/null || \
            warn "Could not install linux-modules-extra. You may need to build batman-adv from source."
    fi

    # Install Flask
    log "Installing Python dependencies..."
    pip3 install flask 2>/dev/null || pip3 install --break-system-packages flask 2>/dev/null || true
}

# ---- Stop conflicting services ----
stop_conflicts() {
    log "Stopping conflicting services..."
    if command -v nmcli &>/dev/null; then
        nmcli device set "$PHYS_IFACE" managed no 2>/dev/null || true
    fi
    pkill -f hostapd 2>/dev/null || true
    pkill -f wpa_supplicant 2>/dev/null || true
    systemctl stop wpa_supplicant 2>/dev/null || true
    systemctl stop hostapd 2>/dev/null || true
}

# ---- Load kernel modules ----
load_modules() {
    log "Loading kernel modules..."
    modprobe batman_adv || error "Failed to load batman_adv module"
    modprobe cfg80211 2>/dev/null || true
    modprobe mac80211 2>/dev/null || true
    log "Kernel modules loaded"
}

# ---- Setup wireless link ----
setup_wifi_link() {
    log "Setting up Ad-hoc mode (IBSS)..."

    local freq=$((2412 + ($MESH_CHANNEL - 1) * 5))

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
    log "Joining IBSS: $MESH_ESSID on channel $MESH_CHANNEL (${freq} MHz) BSSID $MESH_BSSID..."
    iw dev "$PHYS_IFACE" ibss join "$MESH_ESSID" "$freq" fixed-freq "$MESH_BSSID" \
        || error "Failed to join IBSS network"

    sleep 2

    # Verify
    if iw dev "$PHYS_IFACE" link 2>/dev/null | grep -qi "IBSS\|Joined"; then
        log "IBSS network joined successfully"
    else
        warn "Could not verify IBSS join, but continuing..."
    fi

    info "Mode: IBSS (Ad-hoc)"
}

# ---- Setup batman-adv ----
setup_batman() {
    log "Configuring batman-adv..."

    # Unload module if already loaded (to apply routing_algo at load time)
    rmmod batman_adv 2>/dev/null || true
    sleep 1

    # Load module (default BATMAN_V, can be overridden)
    log "Loading batman_adv module..."
    modprobe batman_adv || error "Failed to load batman_adv module"

    # Verify algo
    local algo
    algo=$(cat /sys/module/batman_adv/parameters/routing_algo 2>/dev/null || echo "unknown")
    log "Routing algorithm: $algo"

    # Add interface to batman
    sleep 2
    batctl if add "$PHYS_IFACE" || error "Failed to add $PHYS_IFACE to batman-adv"
    sleep 2

    # Bring up bat0
    ip addr add "${GCS_IP}/24" dev bat0 2>/dev/null || true
    ip link set bat0 up || error "Failed to bring up bat0"

    # Enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
    if ! grep -q "net.ipv4.ip_forward = 1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
    fi

    # Open firewall for batman-adv
    log "Configuring firewall..."
    if command -v iptables &>/dev/null; then
        iptables -I INPUT -i bat0 -j ACCEPT 2>/dev/null || true
        iptables -I FORWARD -i bat0 -j ACCEPT 2>/dev/null || true
        iptables -I FORWARD -o bat0 -j ACCEPT 2>/dev/null || true
    fi
    if command -v ufw &>/dev/null; then
        ufw allow in on bat0 2>/dev/null || true
        ufw allow out on bat0 2>/dev/null || true
    fi

    # Start alfred
    if command -v alfred &>/dev/null; then
        pkill -f "alfred -i bat0" 2>/dev/null || true
        sleep 1
        alfred -i bat0 -b bat0 &
        log "alfred started"
    fi

    # Start batadv-vis
    if command -v batadv-vis &>/dev/null; then
        pkill -f "batadv-vis -i bat0" 2>/dev/null || true
        sleep 1
        batadv-vis -i bat0 -s &
        log "batadv-vis started"
    fi

    log "batman-adv configured"
}

# ---- Verify setup ----
verify() {
    log "Verifying setup..."

    if ! ip link show bat0 &>/dev/null; then
        error "bat0 interface not found"
    fi

    if ! ip addr show bat0 | grep -q "$GCS_IP"; then
        error "IP address not configured on bat0"
    fi

    if ! batctl if | grep -q "$PHYS_IFACE"; then
        error "Physical interface not added to batman-adv"
    fi

    echo ""
    info "========================================"
    info "Ground Station Mesh Status"
    info "========================================"
    info "WiFi Adapter: $PHYS_IFACE"
    info "Mode: Ad-hoc (IBSS)"
    info "bat0 IP: $GCS_IP"
    info "Mesh ESSID: $MESH_ESSID"
    info "Channel: $MESH_CHANNEL"
    echo ""
    info "Batman-adv interfaces:"
    batctl if
    echo ""
}

# ---- Create systemd service for dashboard ----
setup_dashboard_service() {
    log "Setting up dashboard service..."

    cat > /etc/systemd/system/mesh-dashboard.service << 'DASHEOF'
[Unit]
Description=Batman-Adv Mesh Dashboard
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/mesh/mesh_dashboard/app.py
WorkingDirectory=/opt/mesh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
DASHEOF

    # Copy dashboard files to /opt/mesh
    mkdir -p /opt/mesh/mesh_dashboard/templates
    cp "${SCRIPT_DIR}/mesh_dashboard/app.py" /opt/mesh/mesh_dashboard/
    cp "${SCRIPT_DIR}/mesh_dashboard/templates/index.html" /opt/mesh/mesh_dashboard/templates/

    systemctl daemon-reload
    systemctl enable mesh-dashboard.service 2>/dev/null || true
    systemctl start mesh-dashboard.service 2>/dev/null || true

    log "Dashboard service installed and started"
}

# ---- Create systemd service for mesh ----
setup_mesh_service() {
    log "Setting up mesh service..."

    mkdir -p /opt/mesh

    cat > /etc/systemd/system/batman-gcs.service << 'MESHFEOF'
[Unit]
Description=Batman-Adv Ground Station Mesh
After=network.target
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/mesh/start_gcs_mesh.sh
ExecStop=/opt/mesh/stop_gcs_mesh.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
MESHFEOF

    # Create start script
    cat > /opt/mesh/start_gcs_mesh.sh << 'STARTEOF'
#!/bin/bash
set -e

PHYS_IFACE="__PHYS_IFACE__"
GCS_IP="10.0.0.100"
MESH_ESSID="drone-mesh"
MESH_BSSID="02:12:34:56:78:9a"
MESH_CHANNEL=6

modprobe batman_adv 2>/dev/null || true

if command -v nmcli &>/dev/null; then
    nmcli device set "$PHYS_IFACE" managed no 2>/dev/null || true
fi
pkill -f hostapd 2>/dev/null || true
pkill -f wpa_supplicant 2>/dev/null || true

ip link set "$PHYS_IFACE" down 2>/dev/null || true
sleep 1

# Set interface to IBSS mode
iw dev "$PHYS_IFACE" set type ibss 2>/dev/null || true

# Bring interface up
ip link set "$PHYS_IFACE" up
sleep 1

# Join ad-hoc network with fixed BSSID
FREQ=$((2412 + ($MESH_CHANNEL - 1) * 5))
iw dev "$PHYS_IFACE" ibss join "$MESH_ESSID" "$FREQ" fixed-freq "$MESH_BSSID" 2>/dev/null || true
sleep 2

# Reload batman-adv with correct routing algo
rmmod batman_adv 2>/dev/null || true
sleep 1
modprobe batman_adv 2>/dev/null || true
sleep 2

batctl if add "$PHYS_IFACE"
sleep 2
ip addr add "${GCS_IP}/24" dev bat0 2>/dev/null || true
ip link set bat0 up
echo 1 > /proc/sys/net/ipv4/ip_forward

# Open firewall
iptables -I INPUT -i bat0 -j ACCEPT 2>/dev/null || true
iptables -I FORWARD -i bat0 -j ACCEPT 2>/dev/null || true
iptables -I FORWARD -o bat0 -j ACCEPT 2>/dev/null || true

pkill -f "alfred -i bat0" 2>/dev/null || true
sleep 1
alfred -i bat0 -b bat0 &
pkill -f "batadv-vis -i bat0" 2>/dev/null || true
sleep 1
batadv-vis -i bat0 -s &
STARTEOF

    # Create stop script
    cat > /opt/mesh/stop_gcs_mesh.sh << 'STOPEOF'
#!/bin/bash
pkill -f alfred 2>/dev/null || true
pkill -f batadv-vis 2>/dev/null || true
batctl if del bat0 2>/dev/null || true
ip link set bat0 down 2>/dev/null || true
STOPEOF

    # Replace PHYS_IFACE placeholder
    sed -i "s|__PHYS_IFACE__|${PHYS_IFACE}|g" /opt/mesh/start_gcs_mesh.sh

    chmod +x /opt/mesh/start_gcs_mesh.sh
    chmod +x /opt/mesh/stop_gcs_mesh.sh

    systemctl daemon-reload
    systemctl enable batman-gcs.service 2>/dev/null || true
    systemctl start batman-gcs.service 2>/dev/null || true

    log "Mesh service installed and started"
}

# ---- Main ----
main() {
    echo "=========================================="
    echo " Batman-Adv Ground Station Setup"
    echo "=========================================="
    echo ""

    detect_wifi
    install_packages
    stop_conflicts
    load_modules
    setup_wifi_link
    setup_batman
    verify
    setup_mesh_service
    setup_dashboard_service

    echo ""
    echo "=========================================="
    log "Ground station setup complete!"
    echo ""
    echo "  Mesh IP:     $GCS_IP"
    echo "  ESSID:       $MESH_ESSID"
    echo "  Channel:     $MESH_CHANNEL"
    echo "  Dashboard:   http://localhost:8080"
    echo ""
    echo "  Service management:"
    echo "    sudo systemctl status batman-gcs"
    echo "    sudo systemctl status mesh-dashboard"
    echo ""
    echo "  Check mesh status:"
    echo "    sudo batctl o    # originators"
    echo "    sudo batctl n    # neighbors"
    echo ""
    echo "  Make sure the drone node is running:"
    echo "    sudo ./setup_adhoc.sh"
    echo "=========================================="
}

main "$@"
