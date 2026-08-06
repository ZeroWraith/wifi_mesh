#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Package Installation Script
# =============================================================================
# Run this script once on each drone to install required packages and modules.
# Requires root privileges (run with sudo).
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INSTALL]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

# Detect OS
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    elif [ -f /etc/debian_version ]; then
        OS="debian"
    elif [ -f /etc/redhat-release ]; then
        OS="rhel"
    else
        OS="unknown"
    fi
    log "Detected OS: $OS $OS_VERSION"
}

# Update package lists
update_packages() {
    log "Updating package lists..."
    case $OS in
        ubuntu|debian|raspbian)
            apt-get update -qq
            ;;
        fedora|rhel|centos)
            dnf check-update || true  # dnf returns 100 if updates available
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm
            ;;
        *)
            warn "Unknown OS. Trying apt-get..."
            apt-get update -qq || true
            ;;
    esac
}

# Install required packages
install_packages() {
    log "Installing required packages..."
    
    case $OS in
        ubuntu|debian|raspbian)
            apt-get install -y \
                batctl \
                alfred \
                iw \
                wireless-tools \
                wpasupplicant \
                hostapd \
                bridge-utils \
                net-tools \
                iproute2 \
                ifupdown \
                dhcpcd5 \
                firmware-linux-free \
                firmware-linux-nonfree \
                python3 \
                python3-pip \
                python3-gi \
                gstreamer1.0-tools \
                gstreamer1.0-plugins-base \
                gstreamer1.0-plugins-good \
                gstreamer1.0-plugins-bad \
                gstreamer1.0-plugins-ugly \
                libgstreamer1.0-dev \
                v4l-utils \
                gpsd \
                gpsd-clients \
                python3-gps
            ;;
        fedora|rhel|centos)
            dnf install -y \
                batctl \
                alfred \
                iw \
                wpa_supplicant \
                hostapd \
                bridge-utils \
                net-tools \
                iproute \
                python3 \
                python3-pip \
                gstreamer1-plugins-good \
                gstreamer1-plugins-bad-free \
                gstreamer1-plugins-ugly-free \
                v4l-utils \
                gpsd \
                gpsd-clients
            ;;
        arch|manjaro)
            pacman -S --noconfirm \
                batctl \
                alfred \
                iw \
                wpa_supplicant \
                hostapd \
                bridge-utils \
                net-tools \
                iproute2 \
                python \
                python-pip \
                gst-plugins-good \
                gst-plugins-bad \
                gst-plugins-ugly \
                gst-libav \
                v4l-utils \
                gpsd
            ;;
        *)
            warn "Unsupported OS. Attempting to install with apt-get..."
            apt-get install -y batctl alfred iw wpasupplicant hostapd || true
            ;;
    esac
}

# Load kernel modules
load_modules() {
    log "Loading kernel modules..."
    
    # Load batman-adv module
    modprobe batman_adv || error "Failed to load batman_adv module"
    log "Loaded batman_adv module"
    
    # Load 802.11 mesh support modules
    modprobe cfg80211 || warn "Failed to load cfg80211"
    modprobe mac80211 || warn "Failed to load mac80211"
    
    # Load mesh-related modules
    modprobe 8021q || warn "Failed to load 8021q (VLAN)"
    
    log "Kernel modules loaded successfully"
}

# Enable modules at boot
enable_modules_boot() {
    log "Enabling modules at boot..."
    
    # Create modules-load config for batman-adv
    cat > /etc/modules-load.d/batman-adv.conf << EOF
batman_adv
cfg80211
mac80211
EOF
    
    log "Modules will load automatically at boot"
}

# Check for batman-adv in kernel
check_kernel_support() {
    log "Checking kernel support..."
    
    if lsmod | grep -q batman_adv; then
        log "batman_adv module is already loaded"
    elif modinfo batman_adv &>/dev/null; then
        log "batman_adv module available, will load"
    else
        error "batman_adv module not available. You may need to update your kernel or install linux-modules-extra."
    fi
    
    # Check for mesh support
    if iw list 2>/dev/null | grep -q "mesh point"; then
        log "Wireless mesh point mode supported"
    else
        warn "Cannot verify mesh point support. Check your WiFi adapter."
    fi
}

# Install pymavlink for MAVLink
install_pymavlink() {
    log "Installing pymavlink for MAVLink communication..."
    
    pip3 install pymavlink || warn "Failed to install pymavlink"
}

# Install alfred-gpsd for GPS distribution
install_alfred_gpsd() {
    log "Installing alfred-gpsd for GPS distribution..."
    
    # Check if alfred-gpsd is available
    if command -v alfred-gpsd &>/dev/null; then
        log "alfred-gpsd already installed"
    else
        # Try to build from source
        if [ -d /usr/src/alfred-gpsd ]; then
            cd /usr/src/alfred-gpsd
            make && make install || warn "Failed to install alfred-gpsd"
        else
            warn "alfred-gpsd not found. Manual installation may be required."
            warn "See: https://github.com/barney-ii/alfred-gpsd"
        fi
    fi
}

# Disable conflicting services
disable_conflicting() {
    log "Checking for conflicting services..."
    
    # Disable NetworkManager if managing mesh interface
    if systemctl is-active --quiet NetworkManager; then
        warn "NetworkManager is running. May interfere with mesh setup."
        warn "Consider: sudo systemctl stop NetworkManager"
    fi
    
    # Disable dhclient on mesh interface
    if pgrep -f "dhclient.*wlan0" >/dev/null; then
        warn "dhclient running on wlan0. May conflict with static IP."
    fi
}

# Create log directory
setup_logging() {
    log "Setting up logging..."
    mkdir -p /var/log
    touch /var/log/mesh.log
    chmod 644 /var/log/mesh.log
}

# Main installation
main() {
    echo "=========================================="
    echo " Batman-Adv Drone Mesh - Package Installer"
    echo "=========================================="
    echo ""
    
    detect_os
    update_packages
    install_packages
    check_kernel_support
    load_modules
    enable_modules_boot
    install_pymavlink
    install_alfred_gpsd
    disable_conflicting
    setup_logging
    
    echo ""
    echo "=========================================="
    log "Installation complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Edit config.sh with your settings"
    echo "  2. Run: sudo ./setup_mesh.sh"
    echo "=========================================="
}

main "$@"
