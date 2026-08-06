# Batman-Adv True Peer-to-Peer Drone Mesh Network

## Complete Implementation Guide

---

## Table of Contents

1. [Introduction & Overview](#1-introduction--overview)
2. [Protocol Deep Dive](#2-protocol-deep-dive)
3. [Hardware Requirements](#3-hardware-requirements)
4. [Software Stack](#4-software-stack)
5. [Step-by-Step Mesh Configuration](#5-step-by-step-mesh-configuration)
6. [Persistent Boot Configuration](#6-persistent-boot-configuration)
7. [MAVLink Integration](#7-mavlink-integration)
8. [Video Streaming Over Mesh](#8-video-streaming-over-mesh)
9. [GPS Distribution via Alfred-GPSD](#9-gps-distribution-via-alfred-gpsd)
10. [Network Visualization from Ground Station](#10-network-visualization-from-ground-station)
11. [Performance Tuning](#11-performance-tuning)
12. [Troubleshooting](#12-troubleshooting)
13. [Ad-Hoc (IBSS) Mode](#13-ad-hoc-ibss-mode)
14. [Uninstalling the Mesh Network](#14-uninstalling-the-mesh-network)
15. [References](#15-references)

---

## 1. Introduction & Overview

### 1.1 What is Batman-Adv

Batman-adv (Better Approach To Mobile Ad-hoc Networking - advanced) is a **Linux kernel module** implementing a Layer 2 mesh routing protocol. It creates a virtual `bat0` interface that acts as an Ethernet switch connecting all mesh nodes.

**Key characteristics:**
- Runs in kernel space (minimal overhead)
- Operates at Layer 2 (transparent to IPv4/IPv6/ARP/DHCP)
- Creates virtual switch across multiple wireless hops
- Self-healing: automatic reroute when nodes fail
- Proven technology: in mainline Linux since 2011

### 1.2 Why Batman-Adv for Drones

| Benefit | Description |
|---------|-------------|
| **Self-healing** | Automatic reroute within 3-5 seconds when nodes fail |
| **True peer-to-peer** | No hierarchy, every drone is identical |
| **Multi-hop** | Traffic routes through intermediate drones automatically |
| **Kernel space** | Minimal CPU/memory overhead |
| **Layer 2** | Transparent to all higher protocols |
| **Scalable** | Add/remove drones without reconfiguration |

### 1.3 True Mesh Concept

In a true batman-adv mesh, **every drone is an identical peer**:

```
Every drone:
  ✓ Runs identical configuration
  ✓ Broadcasts OGMs to announce itself
  ✓ Re-broadcasts OGMs from other drones
  ✓ Makes independent routing decisions
  ✓ Can forward traffic for any other drone
  ✓ Can be a gateway for internet access
```

### 1.4 Supported Hardware

| Device | CPU | RAM | WiFi Support | Role |
|--------|-----|-----|--------------|------|
| Raspberry Pi 4B | Quad A72 | 2-8GB | Built-in + USB | Companion computer |
| Raspberry Pi 5 | Quad A76 | 4-8GB | Built-in + USB | High-performance companion |
| Jetson Nano | Quad A57 + GPU | 4GB | USB adapter | Vision/AI companion |
| Jetson Orin Nano | 6-core Arm | 4-8GB | USB adapter | Advanced AI companion |
| Any x86 Linux PC | Various | Various | USB adapter | Ground station |

### 1.5 Network Architecture

```
TRUE PEER MESH (No Hierarchy):

    ┌─────────┐         ┌─────────┐
    │ Drone 1 │◄───────►│ Drone 2 │
    │10.0.0.1 │         │10.0.0.2 │
    └────┬────┘         └────┬────┘
         │                   │
         │    ┌─────────┐    │
         └───►│ Drone 3 │◄───┘
              │10.0.0.3 │
              └────┬────┘
                   │
              ┌────┴────┐
              │  Ground │
              │ Station │
              │10.0.0.100│
              └─────────┘

Every node can reach every other node via multi-hop.
No static routes. No manual configuration.
Batman-adv handles all routing automatically.
```

---

## 2. Protocol Deep Dive

### 2.1 OGM (Originator Message) Propagation

Every node broadcasts OGMs periodically (default: 1 second):

```
┌─────────────────────────────────────────────────────────────┐
│                    OGM v2 Packet Structure                  │
├─────────────────────────────────────────────────────────────┤
│ Version: 2                                                  │
│ TTL: 50 (decremented at each hop)                          │
│ Sequence: 12345 (prevents loops)                           │
│ Originator: aa:bb:cc:dd:ee:01 (sender's MAC)              │
│ Throughput: 1000 Mbps (measured link quality)              │
│ Previous Sender: aa:bb:cc:dd:ee:02 (who forwarded it)     │
└─────────────────────────────────────────────────────────────┘
```

**How routing decisions are made:**

1. Node A broadcasts OGM with throughput=1000
2. Node B receives, records: "A reachable via direct, metric=1000"
3. Node B re-broadcasts A's OGM (decremented TTL)
4. Node C receives B's re-broadcast
5. C compares: direct to A (if possible) vs via B
6. C selects best path based on throughput metric

### 2.2 BATMAN-V Algorithm

BATMAN-V uses throughput-based routing:

**Metric Calculation:**
```
metric = throughput × (1 - packet_loss) / hop_count
```

**ELP (Echo Location Protocol):**
- Neighbor discovery without OGM flooding
- Measures actual throughput between direct neighbors
- Reduces overhead compared to BATMAN-IV

### 2.3 Multi-Hop Routing Example

```
Drone 1 wants to send data to Drone 4:

    Drone 1 ──► Drone 2 ──► Drone 3 ──► Drone 4
       │            │            │            │
       └── 1 hop ───┴── 2 hops ─┴── 3 hops ──┘

Batman-adv automatically:
1. Discovers all paths via OGM flooding
2. Calculates best metric for each destination
3. Selects optimal path (fewest hops OR highest throughput)
4. Forwards packets at Layer 2 (transparent to IP)
5. Reroutes if any intermediate drone fails
```

### 2.4 Translation Tables

**Local Translation Table (batctl tl):**
- Maps MAC addresses of clients connected to this node
- Updated when clients associate/disassociate

**Global Translation Table (batctl tg):**
- Maps all client MACs across the entire mesh
- Shows which node each client is connected to
- Enables routing to clients on remote nodes

### 2.5 Gateway Election

Any node can be a gateway:
- Nodes advertise gateway bandwidth via OGMs
- Clients measure TQ (transmission quality) to each gateway
- Selection formula: `score = bandwidth × TQ`
- Automatic failover when gateway goes down

```
Gateway Selection Example:
  Gateway    Bandwidth    TQ     Score
  Node1      100/100      255    25500  ← Selected
  Node2      100/100      220    22000
  Node3      100/100      180    18000
```

---

## 3. Hardware Requirements

### 3.1 Per Drone

- **Companion Computer**: Raspberry Pi 4/5 OR Jetson Nano/Orin
- **WiFi Adapter**: Must support 802.11s mesh point mode
- **Flight Controller**: Pixhawk, CubePilot, or compatible
- **Camera**: Pi Camera, USB camera, or Jetson camera module
- **GPS Module**: Optional, for alfred-gpsd position distribution
- **Power Supply**: Appropriate for your companion computer

### 3.2 Ground Station

- **Computer**: Linux PC (Ubuntu recommended) or Windows with WSL2
- **WiFi Adapter**: Same type as drones
- **Software**: QGroundControl or Mission Planner

### 3.3 WiFi Adapter Requirements

**Must support 802.11s mesh point mode:**

```bash
# Check if your adapter supports mesh
iw phy | grep -A5 "mesh point"

# Expected output:
#     * mesh point
#     * #{ managed } <= 16, #{ AP, mesh point } <= 16
```

**Recommended adapters:**
- Alfa AWUS036ACH (RTL8812AU chipset)
- Alfa AWUS036ACM (MT7612U chipset)
- Panda PAU09 (MT7612U chipset)
- Built-in Raspberry Pi WiFi (Pi 4/5)

### 3.4 Hardware Connections

**Raspberry Pi:**
```
WiFi Adapter    → USB 3.0 port
Flight Controller → UART pins (GPIO 14/15) or USB
Camera         → CSI port (Pi camera) or USB (USB camera)
GPS            → UART pins (if available) or USB
```

**Jetson:**
```
WiFi Adapter    → USB 3.0 port
Flight Controller → UART or USB
Camera         → CSI port (Jetson camera module)
GPS            → UART or USB
```

---

## 4. Software Stack

### 4.1 Core Packages

| Package | Purpose |
|---------|---------|
| `kmod-batman-adv` | Batman-adv kernel module |
| `batctl` | Batman-adv control tool |
| `wpad-mesh-wolfssl` | 802.11s SAE authentication |
| `alfred` | Distributed data exchange |
| `gpsd` | GPS daemon |
| `gpsd-clients` | GPS utilities |

### 4.2 Video Streaming

| Package | Purpose |
|---------|---------|
| `gstreamer1.0-tools` | GStreamer command line tools |
| `gstreamer1.0-plugins-base` | Base GStreamer plugins |
| `gstreamer1.0-plugins-good` | Good GStreamer plugins |
| `gstreamer1.0-plugins-bad` | Bad GStreamer plugins |
| `gstreamer1.0-libav` | Libav GStreamer plugins |

### 4.3 MAVLink

| Package | Purpose |
|---------|---------|
| `python3-pip` | Python package manager |
| `pymavlink` | Python MAVLink library |

### 4.4 Installation Commands

**Raspberry Pi OS:**
```bash
sudo apt update
sudo apt install -y batctl kmod-batman-adv wpad-mesh-wolfssl \
    alfred gpsd gpsd-clients \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    libcamera-dev libcamera-apps-lite \
    python3-pip
pip3 install pymavlink
```

**Jetson (JetPack/Ubuntu):**
```bash
sudo apt update
sudo apt install -y batctl kmod-batman-adv wpad-mesh-wolfssl \
    alfred gpsd gpsd-clients \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    python3-pip
pip3 install pymavlink
```

---

## 5. Step-by-Step Mesh Configuration

### 5.1 Check WiFi Mesh Support

```bash
# Verify mesh point support
iw phy | grep -A10 "Supported interface modes"

# Look for:
#     * mesh point
```

### 5.2 Create Mesh Interface

```bash
# Bring down wlan0 temporarily
sudo ip link set wlan0 down

# Create mesh interface with SAE authentication
# mesh_id must be IDENTICAL on all drones
sudo iw dev wlan0 interface add mesh0 type mesh mesh_id drone-swarm-001

# Set channel (2.4 GHz channel 1)
sudo iw dev mesh0 set channel 1

# Set TX power (optional, depends on adapter)
sudo iw dev mesh0 set txpower fixed 2000  # 20 dBm

# Bring up mesh interface
sudo ip link set mesh0 up

# Verify interface exists
ip link show mesh0
```

### 5.3 Configure WPA Supplicant for SAE

```bash
# Create WPA supplicant config for mesh
sudo tee /etc/wpa_supplicant/wpa_supplicant_mesh.conf << 'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="drone-swarm-001"
    key_mgmt=SAE
    psk="your-secure-password-here"
    mode=5
    frequency=2412
    mesh_fwding=0
    mesh_ttl=1
}
EOF

# Start WPA supplicant for mesh
sudo wpa_supplicant -i mesh0 -c /etc/wpa_supplicant/wpa_supplicant_mesh.conf -D nl80211 &

# Wait for association
sleep 5

# Verify mesh peering
sudo iw dev mesh0 station dump
# Look for "mesh plink: ESTAB" for connected peers
```

### 5.4 Configure Batman-Adv

```bash
# Load batman-adv kernel module
sudo modprobe batman-adv

# Verify module loaded
lsmod | grep batman

# Add mesh interface to batman-adv
sudo batctl if add mesh0

# Verify interface added
sudo batctl if
# Should show: mesh0

# Bring up bat0 interface
sudo ip link set bat0 up

# Set routing algorithm (BATMAN_V for drones)
sudo batctl routing_algo BATMAN_V

# Configure for mobility (drones move fast)
sudo batctl orig_interval 1000    # OGM every 1 second
sudo batctl hop_penalty 15        # Moderate penalty per hop
sudo batctl fragmentation 1       # Enable fragmentation
sudo batctl ap_isolation 0        # Allow client-to-client

# Verify configuration
sudo batctl o    # Should show empty until peers are found
sudo batctl n    # Should show neighbors after OGM exchange
```

### 5.5 Assign IP Address

```bash
# Each drone gets a UNIQUE IP in the same subnet
# Format: 10.0.0.X where X is the drone number

# Drone 1:
sudo ip addr add 10.0.0.1/24 dev bat0

# Drone 2:
sudo ip addr add 10.0.0.2/24 dev bat0

# Drone 3:
sudo ip addr add 10.0.0.3/24 dev bat0

# Ground Station:
sudo ip addr add 10.0.0.100/24 dev bat0

# Verify IP assigned
ip addr show bat0
```

### 5.6 Test Connectivity

```bash
# From Drone 1, ping Drone 3 (may require multi-hop)
ping 10.0.0.3

# Check routing table
sudo batctl o
# Should show all drones and their quality

# Check neighbors
sudo batctl n
# Should show direct neighbors

# Trace route to verify multi-hop
sudo batctl traceroute 10.0.0.3
```

### 5.7 Identical Configuration on ALL Drones

**EVERY drone runs IDENTICAL configuration except IP address:**

| Setting | Value | Same on All? |
|---------|-------|--------------|
| mesh_id | drone-swarm-001 | YES |
| PSK | your-secure-password | YES |
| Channel | 1 (2.4 GHz) | YES |
| routing_algo | BATMAN_V | YES |
| orig_interval | 1000 | YES |
| hop_penalty | 15 | YES |
| fragmentation | 1 | YES |
| IP address | 10.0.0.X | UNIQUE per drone |

**No Hierarchy:**
- Any drone can route traffic for any other
- Any drone can be a gateway
- Any drone can fail without breaking the mesh
- No "master" or "slave" nodes
- No central controller needed

---

## 6. Persistent Boot Configuration

### 6.1 Systemd Service File

Create `/etc/systemd/system/drone-mesh.service`:

```ini
[Unit]
Description=Drone Batman-Adv Mesh Network
After=network.target
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/setup-drone-mesh.sh
ExecStop=/usr/local/bin/teardown-drone-mesh.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 6.2 Setup Script

Create `/usr/local/bin/setup-drone-mesh.sh`:

```bash
#!/bin/bash
# setup-drone-mesh.sh - Configure batman-adv mesh on boot

set -e

# Configuration (same on ALL drones)
MESH_ID="drone-swarm-001"
MESH_KEY="your-secure-password-here"
CHANNEL=1
ROUTING_ALGO="BATMAN_V"
ORIG_INTERVAL=1000
HOP_PENALTY=15

# Get drone ID from hostname or config file
DRONE_ID=$(hostname | grep -o '[0-9]*$')
if [ -z "$DRONE_ID" ]; then
    DRONE_ID=$(cat /etc/drone-id 2>/dev/null || echo "1")
fi

echo "Configuring mesh for drone ${DRONE_ID}..."

# Load batman-adv module
modprobe batman-adv

# Create mesh interface
iw dev wlan0 interface add mesh0 type mesh mesh_id ${MESH_ID}
iw dev mesh0 set channel ${CHANNEL}

# Configure WPA supplicant for SAE
cat > /tmp/wpa_supplicant_mesh.conf << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="${MESH_ID}"
    key_mgmt=SAE
    psk="${MESH_KEY}"
    mode=5
    frequency=$((2412 + (CHANNEL - 1) * 5))
    mesh_fwding=0
    mesh_ttl=1
}
EOF

# Start WPA supplicant
wpa_supplicant -i mesh0 -c /tmp/wpa_supplicant_mesh.conf -D nl80211 &
sleep 3

# Attach to batman-adv
batctl if add mesh0

# Bring up interfaces
ip link set mesh0 up
ip link set bat0 up

# Configure routing
batctl routing_algo ${ROUTING_ALGO}
batctl orig_interval ${ORIG_INTERVAL}
batctl hop_penalty ${HOP_PENALTY}
batctl fragmentation 1

# Assign IP address
ip addr add 10.0.0.${DRONE_ID}/24 dev bat0

# Start alfred for visualization
alfred -i bat0 -b bat0 &
batadv-vis -i bat0 -s &

echo "Mesh configured for drone ${DRONE_ID} (10.0.0.${DRONE_ID})"
```

### 6.3 Teardown Script

Create `/usr/local/bin/teardown-drone-mesh.sh`:

```bash
#!/bin/bash
# teardown-drone-mesh.sh - Remove batman-adv mesh

# Stop services
pkill alfred
pkill batadv-vis
pkill wpa_supplicant

# Remove interfaces
batctl if del mesh0
ip link set bat0 down
ip link set mesh0 down
iw dev mesh0 del

# Unload module
rmmod batman_adv

echo "Mesh torn down"
```

### 6.4 Enable Service

```bash
sudo chmod +x /usr/local/bin/setup-drone-mesh.sh
sudo chmod +x /usr/local/bin/teardown-drone-mesh.sh
sudo systemctl enable drone-mesh.service
sudo systemctl start drone-mesh.service
```

---

## 7. MAVLink Integration

### 7.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MAVLink Communication Flow               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Flight Controller    Companion Computer    Ground Station  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐  │
│  │   Pixhawk   │────►│ Raspberry Pi│────►│    GCS      │  │
│  │             │UART │  or Jetson  │mesh │ (QGC/MP)    │  │
│  └─────────────┘     └─────────────┘     └─────────────┘  │
│                                                             │
│  MAVLink messages flow:                                    │
│  FC → Companion: Telemetry (attitude, position, etc.)     │
│  Companion → FC: Commands (takeoff, land, waypoint)        │
│  Companion → GCS: Telemetry forwarded via mesh            │
│  GCS → Companion: Commands forwarded via mesh             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Flight Controller Connection

**Pixhawk via UART (Raspberry Pi):**
```bash
# Enable UART
sudo raspi-config
# Interface Options → Serial Port → Login shell over serial: No
# → Serial port hardware enabled: Yes

# Set Pixhawk parameters:
# SERIAL2_BAUD = 921 (921600 baud)
# SERIAL2_PROTOCOL = 2 (MAVLink2)
```

**Pixhawk via USB:**
```bash
# Just plug in USB - appears as /dev/ttyACM0
ls /dev/ttyACM*
```

**Jetson via UART:**
```bash
# Configure UART pins via jetson-io.py
sudo /opt/nvidia/jetson-io/jetson-io.py
# Configure header pins → UART
```

### 7.3 Python MAVLink Forwarder

Create `/usr/local/bin/mavlink-forwarder.py`:

```python
#!/usr/bin/env python3
"""MAVLink message forwarder via batman-adv mesh"""

import socket
import threading
from pymavlink import mavutil

# Configuration
FC_SERIAL = '/dev/ttyAMA0'  # or '/dev/ttyACM0' for USB
FC_BAUD = 921600
GCS_IP = '10.0.0.100'  # Ground station IP
GCS_PORT = 14550

class MAVLinkForwarder:
    def __init__(self):
        # Connect to flight controller
        self.fc = mavutil.mavlink_connection(FC_SERIAL, baud=FC_BAUD)
        self.fc.wait_heartbeat()
        print(f"Connected to FC: system {self.fc.target_system}")
        
        # UDP socket for GCS
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Request telemetry streams
        self.fc.mav.request_data_stream_send(
            self.fc.target_system,
            self.fc.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            10,  # 10 Hz
            1
        )
    
    def forward_to_gcs(self):
        """Forward FC telemetry to GCS via mesh"""
        while True:
            msg = self.fc.recv_msg()
            if msg:
                # Send raw bytes to GCS
                self.sock.sendto(msg.get_msgbuf(), (GCS_IP, GCS_PORT))
    
    def forward_to_fc(self):
        """Forward GCS commands to FC"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', 14551))
        
        while True:
            data, addr = sock.recvfrom(4096)
            # Forward to FC
            self.fc.write(data)

if __name__ == '__main__':
    forwarder = MAVLinkForwarder()
    
    # Start forwarding threads
    t1 = threading.Thread(target=forwarder.forward_to_gcs)
    t2 = threading.Thread(target=forwarder.forward_to_fc)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
```

### 7.4 MAVLink Forwarder systemd Service

Create `/etc/systemd/system/mavlink-forwarder.service`:

```ini
[Unit]
Description=MAVLink Forwarder via Mesh
After=drone-mesh.service
Requires=drone-mesh.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/mavlink-forwarder.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable mavlink-forwarder.service
sudo systemctl start mavlink-forwarder.service
```

### 7.5 Ground Station Connection

**QGroundControl (Linux/Windows):**
1. Open QGroundControl
2. Go to Application Settings → Comm Links
3. Add new connection:
   - Type: UDP
   - Port: 14550
   - No other settings needed
4. Connect - telemetry should flow via mesh

**Mission Planner (Windows):**
1. Open Mission Planner
2. Select UDP port 14550
3. Click Connect
4. Telemetry flows via batman-adv mesh

---

## 8. Video Streaming Over Mesh

### 8.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Video Streaming Flow                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Camera        Companion Computer      Ground Station      │
│  ┌─────────┐   ┌─────────────┐        ┌─────────────┐    │
│  │  Pi Cam │──►│ GStreamer   │──mesh──►│  Receiver   │    │
│  │  or USB │   │ H.264 enc   │  UDP   │  (QGC/VLC)  │    │
│  └─────────┘   └─────────────┘        └─────────────┘    │
│                                                             │
│  Bandwidth per stream:                                     │
│  - 640x480 @ 30fps: ~2-4 Mbps                            │
│  - 1280x720 @ 30fps: ~4-8 Mbps                           │
│  - 1920x1080 @ 30fps: ~8-15 Mbps                         │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Video Streaming Commands

**Raspberry Pi Camera (libcamerasrc):**

```bash
# Low quality (640x480, 30fps, ~2 Mbps)
gst-launch-1.0 -v libcamerasrc \
    ! video/x-raw,width=640,height=480,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000

# Medium quality (1280x720, 30fps, ~4 Mbps)
gst-launch-1.0 -v libcamerasrc \
    ! video/x-raw,width=1280,height=720,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=4000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000

# High quality (1920x1080, 30fps, ~8 Mbps)
gst-launch-1.0 -v libcamerasrc \
    ! video/x-raw,width=1920,height=1080,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=8000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

**Jetson Camera (nvarguscamerasrc):**

```bash
# Low quality (640x480, 30fps, ~2 Mbps)
gst-launch-1.0 -v nvarguscamerasrc \
    ! video/x-raw,width=640,height=480,framerate=30/1 \
    ! videoconvert \
    ! nvv4l2h264enc bitrate=2000 \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000

# Medium quality (1280x720, 30fps, ~4 Mbps)
gst-launch-1.0 -v nvarguscamerasrc \
    ! video/x-raw,width=1280,height=720,framerate=30/1 \
    ! videoconvert \
    ! nvv4l2h264enc bitrate=4000 \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000

# High quality (1920x1080, 30fps, ~8 Mbps)
gst-launch-1.0 -v nvarguscamerasrc \
    ! video/x-raw,width=1920,height=1080,framerate=30/1 \
    ! videoconvert \
    ! nvv4l2h264enc bitrate=8000 \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

**USB Camera (v4l2src):**

```bash
# Low quality (640x480, 30fps, ~2 Mbps)
gst-launch-1.0 -v v4l2src device=/dev/video0 \
    ! video/x-raw,width=640,height=480,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

### 8.3 Ground Station Receiver

**GStreamer command line:**
```bash
gst-launch-1.0 udpsrc port=5000 \
    ! application/x-rtp,encoding-name=H264 \
    ! rtph264depay \
    ! avdec_h264 \
    ! autovideosink
```

**VLC Media Player:**
1. Open VLC
2. Media → Open Network Stream
3. Enter: `udp://@:5000`
4. Click Play

**QGroundControl:**
1. Application Settings → General → Video Settings
2. Source: UDP h.264 Video Stream
3. UDP Port: 5000

### 8.4 Video Streaming systemd Service

Create `/etc/systemd/system/video-stream.service`:

```ini
[Unit]
Description=Drone Video Stream via Mesh
After=drone-mesh.service
Requires=drone-mesh.service

[Service]
Type=simple
ExecStart=/usr/local/bin/start-video-stream.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create `/usr/local/bin/start-video-stream.sh`:

```bash
#!/bin/bash
# start-video-stream.sh - Start video streaming

GCS_IP="10.0.0.100"
PORT=5000
QUALITY="low"  # low, medium, high

# Detect camera type
if [ -e /dev/video0 ]; then
    # USB camera
    case $QUALITY in
        low)
            gst-launch-1.0 -v v4l2src device=/dev/video0 \
                ! video/x-raw,width=640,height=480,framerate=30/1 \
                ! videoconvert \
                ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast \
                ! rtph264pay config-interval=1 \
                ! udpsink host=${GCS_IP} port=${PORT}
            ;;
        medium)
            gst-launch-1.0 -v v4l2src device=/dev/video0 \
                ! video/x-raw,width=1280,height=720,framerate=30/1 \
                ! videoconvert \
                ! x264enc tune=zerolatency bitrate=4000 speed-preset=superfast \
                ! rtph264pay config-interval=1 \
                ! udpsink host=${GCS_IP} port=${PORT}
            ;;
        high)
            gst-launch-1.0 -v v4l2src device=/dev/video0 \
                ! video/x-raw,width=1920,height=1080,framerate=30/1 \
                ! videoconvert \
                ! x264enc tune=zerolatency bitrate=8000 speed-preset=superfast \
                ! rtph264pay config-interval=1 \
                ! udpsink host=${GCS_IP} port=${PORT}
            ;;
    esac
elif command -v nvarguscamerasrc &> /dev/null; then
    # Jetson camera
    case $QUALITY in
        low)
            gst-launch-1.0 -v nvarguscamerasrc \
                ! video/x-raw,width=640,height=480,framerate=30/1 \
                ! videoconvert \
                ! nvv4l2h264enc bitrate=2000 \
                ! rtph264pay config-interval=1 \
                ! udpsink host=${GCS_IP} port=${PORT}
            ;;
        medium)
            gst-launch-1.0 -v nvarguscamerasrc \
                ! video/x-raw,width=1280,height=720,framerate=30/1 \
                ! videoconvert \
                ! nvv4l2h264enc bitrate=4000 \
                ! rtph264pay config-interval=1 \
                ! udpsink host=${GCS_IP} port=${PORT}
            ;;
        high)
            gst-launch-1.0 -v nvarguscamerasrc \
                ! video/x-raw,width=1920,height=1080,framerate=30/1 \
                ! videoconvert \
                ! nvv4l2h264enc bitrate=8000 \
                ! rtph264pay config-interval=1 \
                ! udpsink host=${GCS_IP} port=${PORT}
            ;;
    esac
else
    echo "No camera found"
    exit 1
fi
```

Enable:
```bash
sudo chmod +x /usr/local/bin/start-video-stream.sh
sudo systemctl enable video-stream.service
sudo systemctl start video-stream.service
```

---

## 9. GPS Distribution via Alfred-GPSD

### 9.1 What is Alfred-GPSD

alfred-gpsd distributes GPS location information across the batman-adv mesh. Every node can query the GPS position of every other node.

### 9.2 Install and Configure gpsd

```bash
# Install gpsd
sudo apt install gpsd gpsd-clients

# Configure gpsd
sudo tee /etc/default/gpsd << 'EOF'
START_DAEMON="true"
GPSD_OPTIONS="-n"
DEVICES="/dev/ttyUSB0"  # Change to your GPS device
USBAUTO="true"
GPSD_SOCKET="/var/run/gpsd.sock"
EOF

# Enable and start gpsd
sudo systemctl enable gpsd
sudo systemctl start gpsd
```

### 9.3 Start Alfred GPS Distribution

**On drones with GPS:**
```bash
# Start alfred daemon
sudo alfred -i bat0 -b bat0 &

# Start alfred-gpsd (reads from gpsd)
sudo alfred-gpsd -s
```

**On ground station (fixed location):**
```bash
# Start alfred daemon
sudo alfred -i bat0 -b bat0 &

# Start alfred-gpsd with fixed location
sudo alfred-gpsd -s -l 48.858222,2.2945,358
```

### 9.4 Query GPS from Any Node

```bash
# Get all drone positions (JSON format)
alfred-gpsd

# Example output:
[
  { "source" : "aa:bb:cc:dd:ee:01", "tpv" : {
      "class":"TPV", "mode":3,
      "lat":52.575485000, "lon":-1.339716667, "alt":122.500
  }},
  { "source" : "aa:bb:cc:dd:ee:02", "tpv" : {
      "class":"TPV", "mode":3,
      "lat":52.575500000, "lon":-1.339700000, "alt":125.000
  }}
]
```

### 9.5 GPS Distribution systemd Service

Create `/etc/systemd/system/alfred-gpsd.service`:

```ini
[Unit]
Description=Alfred GPS Distribution via Mesh
After=drone-mesh.service
Requires=drone-mesh.service

[Service]
Type=simple
ExecStartPre=/usr/local/bin/start-alfred.sh
ExecStart=/usr/local/bin/start-alfred-gpsd.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create `/usr/local/bin/start-alfred.sh`:

```bash
#!/bin/bash
# Start alfred daemon
alfred -i bat0 -b bat0
```

Create `/usr/local/bin/start-alfred-gpsd.sh`:

```bash
#!/bin/bash
# Start alfred-gpsd

# Check if GPS device exists
if [ -e /dev/ttyUSB0 ] || [ -e /dev/ttyAMA0 ]; then
    # Use GPS
    alfred-gpsd -s
else
    # Use fixed location (ground station)
    alfred-gpsd -s -l 48.858222,2.2945,358
fi
```

Enable:
```bash
sudo chmod +x /usr/local/bin/start-alfred.sh
sudo chmod +x /usr/local/bin/start-alfred-gpsd.sh
sudo systemctl enable alfred-gpsd.service
sudo systemctl start alfred-gpsd.service
```

---

## 10. Network Visualization from Ground Station

### 10.1 batctl Commands

```bash
# View all originators (every drone in the mesh)
sudo batctl o

# View direct neighbors
sudo batctl n

# View available gateways
sudo batctl gwl

# View translation table (all clients)
sudo batctl tg

# JSON output for automation
sudo batctl oj    # Originators JSON
sudo batctl nj    # Neighbors JSON
sudo batctl gwj   # Gateways JSON
sudo batctl tgj   # Translation table JSON
```

### 10.2 Alfred + Batadv-vis

```bash
# Start alfred (distributes data across mesh)
sudo alfred -i bat0 -b bat0 &

# Start batadv-vis server (collects topology)
sudo batadv-vis -i bat0 -s &

# Get topology in JSON format
batadv-vis -f json

# Get topology in Graphviz format
batadv-vis -f dot
```

### 10.3 Custom Python API

Create `/usr/local/bin/mesh-api.py`:

```python
#!/usr/bin/env python3
"""Mesh network visualization API"""

from flask import Flask, jsonify
import subprocess
import json

app = Flask(__name__)

@app.route('/api/mesh/topology')
def get_topology():
    """Get mesh topology in JSON format"""
    result = subprocess.run(['batadv-vis', '-f', 'json'],
                          capture_output=True, text=True)
    try:
        return jsonify(json.loads(result.stdout))
    except:
        return jsonify({"error": "Failed to get topology"}), 500

@app.route('/api/mesh/originators')
def get_originators():
    """Get all mesh nodes"""
    result = subprocess.run(['batctl', 'oj'],
                          capture_output=True, text=True)
    try:
        return jsonify(json.loads(result.stdout))
    except:
        return jsonify({"error": "Failed to get originators"}), 500

@app.route('/api/mesh/neighbors')
def get_neighbors():
    """Get direct neighbors"""
    result = subprocess.run(['batctl', 'nj'],
                          capture_output=True, text=True)
    try:
        return jsonify(json.loads(result.stdout))
    except:
        return jsonify({"error": "Failed to get neighbors"}), 500

@app.route('/api/mesh/gateways')
def get_gateways():
    """Get available gateways"""
    result = subprocess.run(['batctl', 'gwj'],
                          capture_output=True, text=True)
    try:
        return jsonify(json.loads(result.stdout))
    except:
        return jsonify({"error": "Failed to get gateways"}), 500

@app.route('/api/mesh/clients')
def get_clients():
    """Get all clients connected to mesh"""
    result = subprocess.run(['batctl', 'tgj'],
                          capture_output=True, text=True)
    try:
        return jsonify(json.loads(result.stdout))
    except:
        return jsonify({"error": "Failed to get clients"}), 500

@app.route('/api/mesh/gps')
def get_gps():
    """Get GPS positions of all nodes"""
    result = subprocess.run(['alfred-gpsd'],
                          capture_output=True, text=True)
    try:
        return jsonify(json.loads(result.stdout))
    except:
        return jsonify({"error": "Failed to get GPS"}), 500

@app.route('/api/mesh/status')
def get_status():
    """Get overall mesh status"""
    # Get originators
    orig_result = subprocess.run(['batctl', 'oj'],
                                capture_output=True, text=True)
    try:
        originators = json.loads(orig_result.stdout)
        node_count = len(originators.get('originators', []))
    except:
        node_count = 0
    
    # Get gateways
    gw_result = subprocess.run(['batctl', 'gwj'],
                              capture_output=True, text=True)
    try:
        gateways = json.loads(gw_result.stdout)
        gateway_count = len(gateways.get('gateways', []))
    except:
        gateway_count = 0
    
    return jsonify({
        "node_count": node_count,
        "gateway_count": gateway_count,
        "status": "healthy" if node_count > 0 else "no_nodes"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### 10.4 Web Dashboard

Create `/var/www/html/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Drone Mesh Network Monitor</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { display: flex; gap: 20px; }
        #network-graph { width: 600%; height: 500px; border: 1px solid #ccc; flex: 1; }
        #map { width: 600px; height: 500px; border: 1px solid #ccc; }
        #stats { margin-top: 20px; padding: 10px; background: #f5f5f5; }
        .node { fill: #4CAF50; stroke: #333; stroke-width: 2px; }
        .node.ground-station { fill: #2196F3; }
        .link { stroke: #999; stroke-width: 2px; }
        .link.strong { stroke: #4CAF50; stroke-width: 3px; }
        .link.weak { stroke: #f44336; stroke-width: 1px; }
    </style>
</head>
<body>
    <h1>Drone Mesh Network Monitor</h1>
    <div class="container">
        <div id="network-graph"></div>
        <div id="map"></div>
    </div>
    <div id="stats"></div>

    <script>
        const width = 600;
        const height = 500;

        // Initialize map
        const map = L.map('map').setView([0, 0], 2);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        // Initialize SVG
        const svg = d3.select("#network-graph")
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        // Fetch and render network topology
        async function updateTopology() {
            try {
                const response = await fetch('/api/mesh/topology');
                const data = await response.json();

                // Process nodes and links
                const nodes = [];
                const links = [];
                const nodeMap = {};

                data.forEach(primary => {
                    if (!nodeMap[primary.primary]) {
                        nodeMap[primary.primary] = {
                            id: primary.primary,
                            type: primary.type || "drone"
                        };
                        nodes.push(nodeMap[primary.primary]);
                    }

                    primary.neighbors.forEach(neighbor => {
                        links.push({
                            source: primary.primary,
                            target: neighbor.neighbor,
                            metric: parseFloat(neighbor.metric)
                        });
                    });
                });

                // Clear and redraw
                svg.selectAll("*").remove();

                // Create force simulation
                const simulation = d3.forceSimulation(nodes)
                    .force("link", d3.forceLink(links).id(d => d.id).distance(100))
                    .force("charge", d3.forceManyBody().strength(-200))
                    .force("center", d3.forceCenter(width / 2, height / 2));

                // Draw links
                const link = svg.selectAll(".link")
                    .data(links)
                    .enter()
                    .append("line")
                    .attr("class", d => `link ${d.metric > 0.9 ? 'strong' : 'weak'}`);

                // Draw nodes
                const node = svg.selectAll(".node")
                    .data(nodes)
                    .enter()
                    .append("circle")
                    .attr("class", d => `node ${d.type}`)
                    .attr("r", 10)
                    .call(d3.drag()
                        .on("start", dragstarted)
                        .on("drag", dragged)
                        .on("end", dragended));

                // Update positions
                simulation.on("tick", () => {
                    link
                        .attr("x1", d => d.source.x)
                        .attr("y1", d => d.source.y)
                        .attr("x2", d => d.target.x)
                        .attr("y2", d => d.target.y);

                    node
                        .attr("cx", d => d.x)
                        .attr("cy", d => d.y);
                });

                // Drag functions
                function dragstarted(event) {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    event.subject.fx = event.subject.x;
                    event.subject.fy = event.subject.y;
                }

                function dragged(event) {
                    event.subject.fx = event.x;
                    event.subject.fy = event.y;
                }

                function dragended(event) {
                    if (!event.active) simulation.alphaTarget(0);
                    event.subject.fx = null;
                    event.subject.fy = null;
                }

                // Update stats
                document.getElementById('stats').innerHTML = `
                    <strong>Network Statistics:</strong><br>
                    Nodes: ${nodes.length} | Links: ${links.length}
                `;
            } catch (error) {
                console.error('Error fetching topology:', error);
            }
        }

        // Fetch and render GPS positions
        async function updateGPS() {
            try {
                const response = await fetch('/api/mesh/gps');
                const data = await response.json();

                // Clear existing markers
                map.eachLayer(layer => {
                    if (layer instanceof L.Marker) {
                        map.removeLayer(layer);
                    }
                });

                // Add markers
                data.forEach(loc => {
                    const tpv = loc.tpv || {};
                    if (tpv.lat && tpv.lon) {
                        L.marker([tpv.lat, tpv.lon])
                            .addTo(map)
                            .bindPopup(`Node: ${loc.source}<br>Alt: ${tpv.alt || 'N/A'}m`);
                    }
                });

                // Fit bounds if we have locations
                if (data.length > 0) {
                    const bounds = data
                        .filter(loc => loc.tpv && loc.tpv.lat && loc.tpv.lon)
                        .map(loc => [loc.tpv.lat, loc.tpv.lon]);
                    
                    if (bounds.length > 0) {
                        map.fitBounds(bounds, { padding: [20, 20] });
                    }
                }
            } catch (error) {
                console.error('Error fetching GPS:', error);
            }
        }

        // Update every 2 seconds
        updateTopology();
        updateGPS();
        setInterval(updateTopology, 2000);
        setInterval(updateGPS, 5000);
    </script>
</body>
</html>
```

### 10.5 Visualization systemd Service

Create `/etc/systemd/system/mesh-visualization.service`:

```ini
[Unit]
Description=Mesh Network Visualization API
After=drone-mesh.service
Requires=drone-mesh.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/mesh-api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable mesh-visualization.service
sudo systemctl start mesh-visualization.service
```

---

## 11. Performance Tuning

### 11.1 Configuration Profiles

| Scenario | orig_interval | hop_penalty | fragmentation | Notes |
|----------|--------------|-------------|---------------|-------|
| **Low-latency (control)** | 500ms | 10 | 1 | Fast topology updates, more overhead |
| **Balanced (default)** | 1000ms | 15 | 1 | Good for most drone operations |
| **High-throughput (video)** | 1000ms | 15 | 1 | Optimize for bandwidth |
| **Long-range (stability)** | 2000ms | 30 | 0 | Less overhead, slower updates |
| **Highly mobile** | 500ms | 10 | 1 | For fast-moving drones |

### 11.2 Apply Configuration

```bash
# Low-latency profile
sudo batctl orig_interval 500
sudo batctl hop_penalty 10
sudo batctl fragmentation 1

# Balanced profile (default)
sudo batctl orig_interval 1000
sudo batctl hop_penalty 15
sudo batctl fragmentation 1

# Long-range profile
sudo batctl orig_interval 2000
sudo batctl hop_penalty 30
sudo batctl fragmentation 0
```

### 11.3 Multiple Interfaces

For higher throughput, use multiple WiFi adapters:

```bash
# Add multiple interfaces to batman-adv
sudo batctl if add mesh0
sudo batctl if add mesh1

# Verify
sudo batctl if
# Should show: mesh0, mesh1
```

### 11.4 Network Coding

Enable network coding to combine packets (requires 3+ nodes):

```bash
# Enable network coding
sudo batctl nc 1

# Verify
sudo batctl nc
```

---

## 12. Troubleshooting

### 12.1 Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No neighbors visible | Mesh interface not up | Check `batctl if`, ensure mesh0 is added |
| High latency | Slow OGM interval | Decrease `orig_interval` |
| Flapping routes | Unstable links | Increase `hop_penalty`, check signal |
| Gateway not selected | No gateway configured | Set `gw_mode server` on gateway node |
| Packet loss | Interference | Change channel, check signal strength |
| Video stuttering | Bandwidth limited | Reduce resolution, check mesh throughput |
| MAVLink timeout | FC not connected | Check UART/USB connection, baud rate |

### 12.2 Debugging Commands

```bash
# Check batman-adv status
sudo batctl o    # Originators
sudo batctl n    # Neighbors
sudo batctl if   # Interfaces
sudo batctl gwl  # Gateways

# Check interface status
ip link show bat0
ip addr show bat0

# Check kernel messages
dmesg | grep batman-adv

# Monitor batman-adv events
sudo batctl event

# Check signal strength
sudo iw dev mesh0 station dump

# Test throughput
sudo batctl tp <MAC_ADDRESS>
```

### 12.3 Log Analysis

```bash
# Check batman-adv kernel messages
dmesg | grep batman-adv

# Check system logs
journalctl -u drone-mesh -f

# Check alfred logs
journalctl -u alfred-gpsd -f

# Check MAVLink forwarder logs
journalctl -u mavlink-forwarder -f
```

### 12.4 Reset Mesh

```bash
# Stop all services
sudo systemctl stop drone-mesh
sudo systemctl stop alfred-gpsd
sudo systemctl stop mavlink-forwarder

# Tear down mesh
sudo /usr/local/bin/teardown-drone-mesh.sh

# Reconfigure
sudo /usr/local/bin/setup-drone-mesh.sh

# Restart services
sudo systemctl start drone-mesh
sudo systemctl start alfred-gpsd
sudo systemctl start mavlink-forwarder
```

---

## 13. Ad-Hoc (IBSS) Mode

### 13.1 When to Use Ad-Hoc Mode

Ad-hoc (IBSS) mode is an alternative to 802.11s mesh point mode for creating the wireless link between drones. Use ad-hoc mode when:

- Your WiFi adapter does **not** support 802.11s mesh point mode
- You need quick setup for testing/development
- Your hardware driver only supports IBSS

**Check if your adapter supports mesh point mode:**
```bash
iw phy | grep -A8 "interface modes"
```

If you see `mesh point` in the output, use the standard 802.11s setup (Section 5). If you only see `IBSS`, use this ad-hoc section.

### 13.2 Mesh Point vs Ad-Hoc Comparison

| Feature | Mesh Point (802.11s) | Ad-Hoc (IBSS) |
|---------|---------------------|---------------|
| **Batman-adv support** | Yes | Yes |
| **Auto-detection** | Yes (check `iw phy`) | Yes (fallback) |
| **Performance** | Better throughput | Slightly lower |
| **Reliability** | More robust | Adequate for testing |
| **SAE authentication** | Supported | Not available |
| **Multi-hop native** | Yes (built into 802.11s) | No (batman-adv handles) |
| **Setup complexity** | Higher (wpa_supplicant) | Lower (iwconfig) |

### 13.3 Auto-Detection with setup_adhoc.sh

The `setup_adhoc.sh` script automatically detects whether your adapter supports mesh point mode and falls back to ad-hoc if needed:

```bash
# The script checks:
iw phy | grep "mesh point"

# If found → uses 802.11s mesh point mode
# If NOT found → uses ad-hoc (IBSS) mode
```

**Usage:**
```bash
sudo ./setup_adhoc.sh
```

The script will:
1. Detect your WiFi interface automatically
2. Check for mesh point support
3. Configure the appropriate mode
4. Create bat0 and assign IP address

### 13.4 Step-by-Step Ad-Hoc Configuration

If you prefer manual configuration instead of using the script:

#### Check for IBSS Support

```bash
iw phy | grep -A8 "interface modes"
```

Look for `IBSS` in the output.

#### Set Up Ad-Hoc Interface

```bash
# Take interface down
sudo ip link set wlan0 down

# Set to ad-hoc mode
sudo iwconfig wlan0 mode ad-hoc

# Set network name (must be SAME on all drones)
sudo iwconfig wlan0 essid "drone-mesh"

# Set channel (must be SAME on all drones)
sudo iwconfig wlan0 channel 6

# Bring interface up
sudo ip link set wlan0 up
```

#### Verify Ad-Hoc Mode

```bash
iwconfig wlan0
```

Should show `Mode:Ad-Hoc` and the ESSID.

#### Configure Batman-Adv

```bash
# Load batman-adv module
sudo modprobe batman_adv

# Create bat0 interface
sudo batctl if add wlan0

# Bring up bat0
sudo ip link set bat0 up

# Set routing algorithm
sudo batctl routing_algo BATMAN_V

# Assign IP address (unique per drone)
sudo ip addr add 10.0.0.2/24 dev bat0
```

#### Test Connectivity

After setting up another drone with a different IP (e.g., 10.0.0.1):

```bash
# Check batman-adv neighbors
sudo batctl o

# Test connectivity
ping 10.0.0.1
```

### 13.5 Building Batman-Adv from Source (Jetson Tegra)

The Jetson's Tegra kernel does not include batman-adv by default. You must build it from source.

#### Prerequisites

```bash
sudo apt-get install -y build-essential git
```

#### Clone and Build

```bash
# Clone batman-adv source
cd /tmp
git clone https://git.open-mesh.org/batman-adv.git
cd batman-adv

# Generate compatibility header
bash gen-compat-autoconf.sh

# Build against running kernel
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules
```

#### Known Issue: timer_shutdown_sync

If you see this error:
```
error: static declaration of 'timer_shutdown_sync' follows non-static declaration
```

Fix by editing `compat-include/linux/timer.h` — change the version check:
```c
#if LINUX_VERSION_IS_LESS(5, 15, 148)
```

Then rebuild.

#### Install and Load

```bash
# Install module
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules_install

# Update module dependencies
sudo depmod -a

# Load module
sudo modprobe batman_adv

# Verify
lsmod | grep batman
```

#### Make Persistent Across Reboots

```bash
echo 'batman_adv' | sudo tee /etc/modules-load.d/batman-adv.conf
```

### 13.6 Ad-Hoc Troubleshooting

| Issue | Solution |
|-------|----------|
| `iwconfig: command not found` | Install wireless-tools: `sudo apt install wireless-tools` |
| `Mode:Auto` after setting ad-hoc | Interface may need to be down before changing mode |
| No neighbors in `batctl o` | Wait 10-30 seconds for OGM propagation |
| `batman_adv: Unknown symbol` | Module not built for your kernel, rebuild from source |
| ESSID mismatch | All drones must use the EXACT same ESSID |
| Channel mismatch | All drones must be on the SAME channel |

---

## 14. Uninstalling the Mesh Network

### 14.1 Using the Uninstall Script

The `uninstall.sh` script completely removes the mesh configuration and restores the system to its original state:

```bash
sudo ./uninstall.sh
```

**What it removes:**
- systemd service (`batman-mesh.service`)
- `/opt/mesh/` installation directory and all scripts
- Kernel module loading configuration (`/etc/modules-load.d/batman-adv.conf`)
- IP forwarding settings from `/etc/sysctl.conf`
- Firewall rules (iptables, UFW, firewalld)
- Mesh log file (`/var/log/mesh.log`)

**What it does NOT remove:**
- Installed packages (batctl, alfred, etc.) - these remain available
- WiFi adapter drivers - these remain functional

### 14.2 Manual Cleanup

If you need to remove specific components manually without using the full uninstall script:

```bash
# Stop and disable the mesh service
sudo systemctl stop batman-mesh
sudo systemctl disable batman-mesh

# Remove bat0 interface
sudo batctl if del bat0

# Take down physical interface
sudo ip link set wlan0 down

# Unload kernel modules
sudo rmmod batman_adv

# Remove boot module configuration
sudo rm /etc/modules-load.d/batman-adv.conf

# Remove installed files
sudo rm -rf /opt/mesh
```

### 14.3 After Uninstalling

Reboot to ensure all changes take effect:
```bash
sudo reboot
```

---

## 15. References

### Official Documentation
- [Batman-Adv Kernel Documentation](https://docs.kernel.org/networking/batman-adv.html)
- [OpenWrt Batman-Adv Guide](https://openwrt.org/docs/guide-user/network/wifi/mesh/batman)
- [Open-Mesh Wiki](https://www.open-mesh.org/projects/batman-adv/wiki)
- [Alfred Documentation](https://www.open-mesh.org/doc/alfred/)
- [Batadv-vis Documentation](https://www.open-mesh.org/doc/alfred/Batadv-vis.html)

### Tools
- [batadv-vis](https://www.open-mesh.org/doc/alfred/Batadv-vis.html) - Network visualization
- [Alfred](https://github.com/open-mesh-mirror/alfred) - Distributed data exchange
- [GStreamer](https://gstreamer.freedesktop.org/) - Video streaming
- [pymavlink](https://mavlink.io/en/) - MAVLink Python library

### Research Papers
- "Visually extracting the network topology of drone swarms" (Robotics and Autonomous Systems, 2026)
- Fraunhofer IIS: "Innovation From Above: How Mesh Networks Help Control Drone Swarms" (2026)

### Community
- IRC: `#batadv` on ircs://irc.hackint.org/
- Mailing list: b.a.t.m.a.n@lists.open-mesh.org

---

## Appendix A: Quick Reference Card

### Essential Commands

```bash
# Installation
sudo apt install batctl kmod-batman-adv wpad-mesh-wolfssl alfred gpsd gpsd-clients

# Configuration
sudo batctl if add mesh0
sudo batctl routing_algo BATMAN_V
sudo batctl orig_interval 1000
sudo batctl fragmentation 1

# Monitoring
sudo batctl o          # Originators
sudo batctl n          # Neighbors
sudo batctl gwl        # Gateways
sudo batctl tg         # Translation table

# Visualization
sudo alfred -i bat0 -b bat0
sudo batadv-vis -i bat0 -s
batadv-vis -f json     # JSON output
batadv-vis -f dot      # Graphviz output

# GPS
alfred-gpsd            # Get all GPS positions
alfred-gpsd -s         # Start GPS server

# Uninstall
sudo ./uninstall.sh    # Complete removal
# Or manual cleanup:
sudo batctl if del bat0
sudo rmmod batman_adv
sudo systemctl disable batman-mesh

# Ad-Hoc / IBSS Mode (when mesh point not supported)
iw phy | grep -A8 "interface modes"  # Check for IBSS support
sudo ip link set wlan0 down
sudo iwconfig wlan0 mode ad-hoc
sudo iwconfig wlan0 essid "drone-mesh"
sudo iwconfig wlan0 channel 6
sudo ip link set wlan0 up
sudo batctl if add wlan0
sudo ip link set bat0 up
sudo ip addr add 10.0.0.X/24 dev bat0

# Build batman-adv from source (Jetson Tegra)
cd /tmp && git clone https://git.open-mesh.org/batman-adv.git
cd batman-adv && bash gen-compat-autoconf.sh
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules_install
sudo depmod -a && sudo modprobe batman_adv
```

### Default Settings

| Parameter | Default | Recommended for Drones |
|-----------|---------|----------------------|
| `orig_interval` | 1000ms | 500-1000ms |
| `hop_penalty` | 15 | 10-30 |
| `fragmentation` | 0 | 1 |
| `routing_algo` | BATMAN_IV | BATMAN_V |

---

*Document Version: 1.0*
*Last Updated: August 2026*
*Mesh Frequency: 2.4 GHz*
*Hardware: Raspberry Pi 4/5, Jetson Nano/Orin*
