#!/bin/bash
# =============================================================================
# Build Batman-Adv Module for Jetson Tegra Kernel
# =============================================================================
# This script builds the batman_adv kernel module from source.
# Requires kernel headers and build tools.
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[BUILD]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo $0"
fi

KERNEL_VERSION=$(uname -r)
KERNEL_SRC="/usr/src/linux-headers-5.15.148-tegra-ubuntu22.04_aarch64/3rdparty/canonical/linux-jammy/kernel-source"

log "Building batman_adv for kernel: $KERNEL_VERSION"
log "Using kernel source: $KERNEL_SRC"

# Verify kernel source exists
if [ ! -d "$KERNEL_SRC" ]; then
    error "Kernel source not found at: $KERNEL_SRC"
fi

# Check for build tools
log "Checking build dependencies..."
which make || error "make not found. Install build-essential"
which gcc || error "gcc not found. Install gcc"

# Check for kernel headers
if [ ! -f "$KERNEL_SRC/Makefile" ]; then
    error "Kernel Makefile not found"
fi

# Enable batman_adv in kernel config
log "Enabling batman_adv in kernel config..."
cd "$KERNEL_SRC"

# Backup original config
cp .config .config.backup

# Enable batman_adv
sed -i 's/# CONFIG_BATMAN_ADV is not set/CONFIG_BATMAN_ADV=m/' .config

# Also enable required dependencies
sed -i 's/# CONFIG_NET is not set/CONFIG_NET=y/' .config
sed -i 's/# CONFIG_INET is not set/CONFIG_INET=y/' .config
sed -i 's/# CONFIG_PACKET is not set/CONFIG_PACKET=y/' .config
sed -i 's/# CONFIG_NET_SCHED is not set/CONFIG_NET_SCHED=y/' .config

# Ensure cfg80211 is enabled
grep -q "CONFIG_CFG80211=" .config || echo "CONFIG_CFG80211=m" >> .config
grep -q "CONFIG_MAC80211=" .config || echo "CONFIG_MAC80211=m" >> .config

log "Config updated. Building module..."

# Prepare kernel build
log "Preparing kernel build..."
make olddefconfig 2>&1 | tail -5

# Build just the batman_adv module
log "Building batman_adv module..."
make M=net/batman-adv modules 2>&1 | tail -20

# Check if build succeeded
if [ ! -f net/batman-adv/batman-adv.ko ]; then
    error "Build failed - batman-adv.ko not found"
fi

log "Build successful! batman-adv.ko created."

# Install the module
log "Installing module..."
INSTALL_MOD_PATH=/ make M=net/batman-adv modules_install 2>&1 | tail -5

# Update module dependencies
log "Updating module dependencies..."
depmod -a

# Test if module can be loaded
log "Testing module load..."
rmmod batman_adv 2>/dev/null || true
if modprobe batman_adv; then
    log "Module loaded successfully!"
    modinfo batman_adv | head -10
else
    warn "Module load test failed, but module is installed."
    warn "You may need to reboot to use it."
fi

log "=========================================="
log "Batman-adv module built and installed!"
log ""
log "To load the module:"
log "  sudo modprobe batman_adv"
log ""
log "To make it load at boot:"
log "  echo 'batman_adv' | sudo tee /etc/modules-load.d/batman-adv.conf"
log "=========================================="
