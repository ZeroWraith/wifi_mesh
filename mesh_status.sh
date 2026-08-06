#!/bin/bash
# =============================================================================
# Batman-Adv Drone Mesh - Status & Monitoring Script
# =============================================================================
# This script displays the current state of the mesh network.
# Run it anytime to check connectivity, neighbors, and gateway status.
# =============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.sh"

# Load config if exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Header
print_header() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN} Batman-Adv Mesh Network Status${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""
}

# Check if batman_adv is loaded
check_module() {
    echo -e "${BLUE}[Module]${NC}"
    if lsmod | grep -q batman_adv; then
        echo -e "  batman_adv: ${GREEN}Loaded${NC}"
    else
        echo -e "  batman_adv: ${RED}Not loaded${NC}"
    fi
    echo ""
}

# Show interface status
show_interfaces() {
    echo -e "${BLUE}[Interfaces]${NC}"
    
    # Physical interface
    if [ -n "$MESH_IFACE" ] && ip link show "$MESH_IFACE" &>/dev/null; then
        STATE=$(cat /sys/class/net/"$MESH_IFACE"/operstate 2>/dev/null || echo "unknown")
        MAC=$(cat /sys/class/net/"$MESH_IFACE"/address 2>/dev/null || echo "N/A")
        echo -e "  $MESH_IFACE: $GREEN$STATE${NC} (MAC: $MAC)"
    else
        echo -e "  ${MESH_IFACE:-wlan0}: ${RED}Not found${NC}"
    fi
    
    # bat0 interface
    if ip link show bat0 &>/dev/null; then
        STATE=$(cat /sys/class/net/bat0/operstate 2>/dev/null || echo "unknown")
        IP=$(ip addr show bat0 | grep -oP '(?<=inet\s)\d+\.\d+\.\d+\.\d+' || echo "N/A")
        echo -e "  bat0: ${GREEN}$STATE${NC} (IP: $IP)"
    else
        echo -e "  bat0: ${RED}Not created${NC}"
    fi
    echo ""
}

# Show batman-adv neighbors
show_neighbors() {
    echo -e "${BLUE}[Mesh Neighbors]${NC}"
    
    if ! command -v batctl &>/dev/null; then
        echo -e "  ${RED}batctl not found${NC}"
        return
    fi
    
    NEIGHBORS=$(batctl n 2>/dev/null)
    
    if [ -z "$NEIGHBORS" ] || echo "$NEIGHBORS" | grep -q "No batman"; then
        echo -e "  ${YELLOW}No neighbors discovered yet${NC}"
        echo -e "  ${YELLOW}(This may take 10-30 seconds after startup)${NC}"
    else
        echo "$NEIGHBORS" | tail -n +2 | while read -r line; do
            if [ -n "$line" ]; then
                echo -e "  $line"
            fi
        done
    fi
    echo ""
}

# Show batman-adv originators (routing table)
show_originators() {
    echo -e "${BLUE}[Routing Table]${NC}"
    
    ORIGS=$(batctl o 2>/dev/null)
    
    if [ -z "$ORIGS" ] || echo "$ORIGS" | grep -q "No batman"; then
        echo -e "  ${YELLOW}No routes discovered yet${NC}"
    else
        echo "$ORIGS" | tail -n +2 | while read -r line; do
            if [ -n "$line" ]; then
                echo -e "  $line"
            fi
        done
    fi
    echo ""
}

# Show gateway status
show_gateway() {
    echo -e "${BLUE}[Gateway Status]${NC}"
    
    GW_INFO=$(batctl gw 2>/dev/null)
    
    if echo "$GW_INFO" | grep -q "No gateways"; then
        echo -e "  ${YELLOW}No gateways available${NC}"
    else
        echo "$GW_INFO" | tail -n +2 | while read -r line; do
            if [ -n "$line" ]; then
                echo -e "  $line"
            fi
        done
    fi
    echo ""
}

# Show translation tables (client MACs)
show_translations() {
    echo -e "${BLUE}[Translation Tables]${NC}"
    
    # Local table
    LOCAL_TL=$(batctl tl 2>/dev/null)
    if [ -n "$LOCAL_TL" ] && ! echo "$LOCAL_TL" | grep -q "No"; then
        echo -e "  Local clients:"
        echo "$LOCAL_TL" | tail -n +2 | while read -r line; do
            if [ -n "$line" ]; then
                echo -e "    $line"
            fi
        done
    fi
    
    # Global table
    GLOBAL_TG=$(batctl tg 2>/dev/null)
    if [ -n "$GLOBAL_TG" ] && ! echo "$GLOBAL_TG" | grep -q "No"; then
        echo -e "  Global clients:"
        echo "$GLOBAL_TG" | tail -n +2 | while read -r line; do
            if [ -n "$line" ]; then
                echo -e "    $line"
            fi
        done
    fi
    echo ""
}

# Show network statistics
show_stats() {
    echo -e "${BLUE}[Statistics]${NC}"
    
    if [ -f /sys/class/net/bat0/statistics/rx_bytes ]; then
        RX_BYTES=$(cat /sys/class/net/bat0/statistics/rx_bytes 2>/dev/null || echo "0")
        TX_BYTES=$(cat /sys/class/net/bat0/statistics/tx_bytes 2>/dev/null || echo "0")
        
        # Convert to human readable
        RX_MB=$(echo "scale=2; $RX_BYTES / 1048576" | bc 2>/dev/null || echo "0")
        TX_MB=$(echo "scale=2; $TX_BYTES / 1048576" | bc 2>/dev/null || echo "0")
        
        echo -e "  RX: ${GREEN}${RX_MB} MB${NC}"
        echo -e "  TX: ${GREEN}${TX_MB} MB${NC}"
    fi
    
    # Packet loss (if ping is available)
    if [ -n "$DRONE_IP" ]; then
        echo -e "  Packet loss to self:"
        ping -c 3 -W 1 "$DRONE_IP" 2>/dev/null | tail -1
    fi
    echo ""
}

# Show gateway clients (if this node is a gateway server)
show_gw_clients() {
    if [ "$GATEWAY_MODE" = "server" ]; then
        echo -e "${BLUE}[Gateway Clients]${NC}"
        GW_CLIENTS=$(batctl gwl 2>/dev/null)
        if [ -n "$GW_CLIENTS" ]; then
            echo "$GW_CLIENTS" | tail -n +2 | while read -r line; do
                if [ -n "$line" ]; then
                    echo -e "  $line"
                fi
            done
        fi
        echo ""
    fi
}

# Show connectivity test
test_connectivity() {
    echo -e "${BLUE}[Connectivity Test]${NC}"
    
    # Test local interface
    if ping -c 1 -W 1 10.0.0.1 &>/dev/null; then
        echo -e "  10.0.0.1 (Drone 1): ${GREEN}Reachable${NC}"
    else
        echo -e "  10.0.0.1 (Drone 1): ${RED}Unreachable${NC}"
    fi
    
    # Test common IPs
    for ip in 10.0.0.2 10.0.0.3 10.0.0.100; do
        if ping -c 1 -W 1 "$ip" &>/dev/null; then
            echo -e "  $ip: ${GREEN}Reachable${NC}"
        else
            echo -e "  $ip: ${YELLOW}No response${NC}"
        fi
    done
    echo ""
}

# JSON output for visualization
json_output() {
    echo -e "${BLUE}[JSON Output]${NC}"
    echo "{"
    echo "  \"drone_ip\": \"${DRONE_IP:-unknown}\","
    echo "  \"mesh_id\": \"${MESH_ID:-unknown}\","
    echo "  \"neighbors\": ["
    
    NEIGHBORS=$(batctl n 2>/dev/null | tail -n +2)
    FIRST=true
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            if [ "$FIRST" = true ]; then
                FIRST=false
            else
                echo ","
            fi
            echo -n "    \"$line\""
        fi
    done <<< "$NEIGHBORS"
    
    echo ""
    echo "  ],"
    echo "  \"timestamp\": \"$(date -Iseconds)\""
    echo "}"
}

# Main function
main() {
    print_header
    
    check_module
    show_interfaces
    show_neighbors
    show_originators
    show_gateway
    show_translations
    show_gw_clients
    show_stats
    test_connectivity
    
    echo -e "${CYAN}============================================${NC}"
    echo -e "  Last updated: $(date)"
    echo -e "${CYAN}============================================${NC}"
    echo ""
}

# Handle command line arguments
case "${1:-}" in
    -j|--json)
        json_output
        ;;
    -h|--help)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  -j, --json    Output status in JSON format"
        echo "  -h, --help    Show this help message"
        echo ""
        echo "Without options, shows detailed human-readable status."
        ;;
    *)
        main
        ;;
esac
