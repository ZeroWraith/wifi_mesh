#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Configuration File
# =============================================================================
# Edit this file to match your hardware and network setup.
# Each drone should have its own copy of this file with the unique settings.
# =============================================================================

# ----- DRONE IDENTITY (UNIQUE PER DRONE) -----

# IP address for this drone (must be unique in mesh)
DRONE_IP="10.0.0.3"

# Physical WiFi interface name (before batman-adv creates bat0)
# If empty, auto-detection will try to find your WiFi adapter
PHYS_IFACE="wlp0s20f3"

# Mesh interface name (after batman-adv creates bat0)
# Usually "bat0" - no need to change unless you know what you're doing
MESH_IFACE="bat0"

# Optional: Additional network interface for internet/GCS access
# Set to physical interface name (e.g., eth0, wlan1) or leave empty
EXTERNAL_IFACE=""

# ----- MESH NETWORK SETTINGS -----

# Mesh ID (must be SAME on all drones for them to join same mesh)
MESH_ID="drone-mesh"

# Fixed IBSS BSSID (must be SAME on all nodes)
# Both nodes must join with this exact BSSID to be in the same IBSS network
MESH_BSSID="02:12:34:56:78:9a"

# Channel for mesh operation (must be SAME on all drones)
# Use channels 1-11 for 2.4 GHz, 36-165 for 5 GHz
MESH_CHANNEL=6

# Mesh frequency band: "2g" for 2.4GHz, "5g" for 5GHz
MESH_BAND="2g"

# ----- BATMAN-ADV SETTINGS -----

# Routing algorithm: "BATMAN_V" (throughput-based, recommended)
# or "BATMAN_IV" (older, simpler)
BATMAN_ROUTING="BATMAN_V"

# Gateway mode: "off", "client", or "server"
# Set to "server" if this drone has internet access to share
GATEWAY_MODE="off"

# Gateway download/upload in Mbit (only if GATEWAY_MODE="server")
GW_DOWNLOAD=100
GW_UPLOAD=100

# ----- NETWORK SETTINGS -----

# Netmask for mesh network
NETMASK="255.255.255.0"

# Broadcast address
BROADCAST="10.0.0.255"

# Optional: DNS server (for internet access via gateway)
DNS_SERVER="8.8.8.8"

# ----- INTERFACE NAMES (AUTO-DETECTED OR MANUAL) -----

# ----- ADVANCED SETTINGS -----

# WiFi adapter driver options (for specific adapters)
# Examples:
#   Alfa AWUS036ACH: OPTIONS="rtwl8xxcu rtw_channel=6"
#   Intel AX200: OPTIONS=""
# Leave empty for most adapters
WIFI_DRIVER_OPTIONS=""

# Optional: Set MAC address for mesh interface (leave empty for auto)
# Format: XX:XX:XX:XX:XX:XX
MESH_MAC=""

# Optional: Additional batman-adv module parameters
# Example: "batman_adv.routing_algorithm=BATMAN_V batman_adv.gw_mode=off"
BATMAN_PARAMS=""

# ----- LOGGING -----

# Enable debug logging to /var/log/mesh.log
DEBUG_LOG=false

# Log level: "info", "debug", "warn", "error"
LOG_LEVEL="info"
