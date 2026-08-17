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
10. [Network Visualization & Dashboard](#10-network-visualization--dashboard)
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

`meshd` is the **control-plane daemon** that owns this data plane on each node.
It reads one declarative `mesh.yaml` and brings up radios, bat0, QoS,
management plane, and optional services (telemetry, video, dashboard) — so
every node converges on the same state from the same config.

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
meshd brings up the data plane; batman-adv handles all routing.
```

**Two planes:**

| Plane | Responsibility | Implemented by |
|-------|----------------|----------------|
| **Data plane** | Radios, bat0, forwarding, QoS `tc` shaping | Kernel + `batctl`/`tc`, orchestrated by meshd |
| **Control plane** | Lifecycle, services, management RPC, fleet discovery | `meshd` daemon, `meshctl` CLI, JSON-RPC over the mesh |

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

Set `mesh.orig_interval_ms` in `mesh.yaml` to change the interval.

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

Set `mesh.routing_algo: BATMAN_V` in `mesh.yaml`.

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

Enable a gateway node with `mesh.gateway: server` and optional
`mesh.external_iface` in `mesh.yaml`.

---

## 3. Hardware Requirements

### 3.1 Per Drone

- **Companion Computer**: Raspberry Pi 4/5 OR Jetson Nano/Orin
- **WiFi Adapter**: Must support 802.11s mesh point mode (or IBSS)
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
| `batctl` | Batman-adv control tool |
| `batman-adv` (kernel) | Layer 2 mesh routing module |
| `wpad-mesh-wolfssl` | 802.11s SAE authentication |
| `alfred` | Distributed data exchange |
| `alfred-gpsd` | GPS position distribution |
| `batadv-vis` | Topology visualization |
| `gpsd` | GPS daemon |
| `python3-venv` | meshd virtualenv |

### 4.2 meshd Dependencies

`meshd` is a Python package with optional extras:

| Extra | Package | Purpose |
|-------|---------|---------|
| (core) | — | Data plane, lifecycle, QoS, management |
| `telemetry` | `pymavlink` | MAVLink forwarding (flight controller) |
| `dashboard` | `flask` | Web dashboard |

GStreamer is used out-of-band for the video service (installed as a system
package).

### 4.3 Video Streaming

| Package | Purpose |
|---------|---------|
| `gstreamer1.0-tools` | GStreamer command line tools |
| `gstreamer1.0-plugins-base` | Base GStreamer plugins |
| `gstreamer1.0-plugins-good` | Good GStreamer plugins |
| `gstreamer1.0-plugins-bad` | Bad GStreamer plugins |
| `gstreamer1.0-libav` | Libav GStreamer plugins |

### 4.4 Installation

**One command (Debian/Ubuntu, Fedora/RHEL, Arch):**

```bash
git clone <your-repo> && cd <your-repo>
sudo ./install_packages.sh   # OS packages + kernel modules
sudo ./install.sh            # pip-install meshd into /opt/mesh/.venv, enable systemd
```

Or install `meshd` extras selectively:

```bash
sudo ./install.sh --with-telemetry   # + pymavlink
sudo ./install.sh --with-dashboard   # + flask
sudo ./install.sh --with-all         # everything
```

---

## 5. Step-by-Step Mesh Configuration

### 5.1 Generate the Config

```bash
meshd --init -c /opt/mesh/config/mesh.yaml
# or the install script already wrote a default file
```

Every node runs **identical configuration except `node.id` and `node.ip`**:

| Setting | Value | Same on All? |
|---------|-------|--------------|
| `mesh.id` / `mesh.essid` | `drone-mesh` | YES |
| `mesh.ibss_bssid` | `02:12:34:56:78:9a` | YES |
| `radios[].channel` / band | e.g. channel 6, 2.4g | YES |
| `mesh.routing_algo` | BATMAN_V | YES |
| `mesh.orig_interval_ms` | 1000 | YES |
| `mesh.hop_penalty` | 15 | YES |
| `mesh.fragmentation` | true | YES |
| `management.token` | (shared secret) | YES |
| `node.ip` | `10.0.0.X` | UNIQUE per node |
| `node.id` | `drone-XX` | UNIQUE per node |

### 5.2 Verify WiFi Mesh Support

```bash
# Verify mesh point support
iw phy | grep -A10 "Supported interface modes"

# Look for:
#     * mesh point
```

### 5.3 Create the Mesh Interface

`meshd` handles this automatically from `radios[]` — with 802.11s SAE
authentication, channel and TX power set from config:

```yaml
radios:
  - name: radioA
    iface: auto          # auto-detects the first free wireless interface
    mode: auto           # auto | mesh (802.11s) | ibss
    band: 2.4g
    channel: 6
    txpower_dbm: 20
```

Equivalent manual commands (for reference):

```bash
sudo ip link set wlan0 down
sudo iw dev wlan0 interface add mesh0 type mesh mesh_id drone-mesh
sudo iw dev mesh0 set channel 1
sudo iw dev mesh0 set txpower fixed 2000
sudo ip link set mesh0 up
```

### 5.4 Configure Batman-Adv

`meshd` loads the module, adds the interface, and applies the routing profile:

```yaml
mesh:
  routing_algo: BATMAN_V
  orig_interval_ms: 1000
  hop_penalty: 15
  fragmentation: true
  interface_routing: true
```

Equivalent manual commands (for reference):

```bash
sudo modprobe batman-adv
sudo batctl if add mesh0
sudo ip link set bat0 up
sudo batctl routing_algo BATMAN_V
sudo batctl orig_interval 1000
sudo batctl hop_penalty 15
sudo batctl fragmentation 1
sudo batctl ap_isolation 0
```

### 5.5 Assign IP Address

`meshd` assigns `node.ip` (e.g. `10.0.0.3/24`) to `bat0` automatically.

```yaml
node:
  id: drone-03
  ip: 10.0.0.3
```

```
Drone 1:    10.0.0.1
Drone 2:    10.0.0.2
Drone 3:    10.0.0.3
Ground:     10.0.0.100
```

### 5.6 Start and Test Connectivity

```bash
sudo systemctl start meshd
systemctl status meshd
meshctl status
```

Then verify on any node:

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

### 5.7 Remote Fleet Management

Because the management plane runs over the mesh, any node can inspect any
other node:

```bash
meshctl nodes                          # list the whole fleet (alfred type 129)
meshctl -d 10.0.0.3 status             # status of a specific drone
meshctl -d 10.0.0.3 restart            # restart a remote drone's mesh
```

All management calls are token-authenticated (`management.token`).

**No Hierarchy:**
- Any drone can route traffic for any other
- Any drone can be a gateway
- Any drone can fail without breaking the mesh
- No "master" or "slave" nodes
- No central controller needed

---

## 6. Persistent Boot Configuration

### 6.1 The meshd Systemd Unit

`install.sh` installs `deploy/units/meshd.service`:

```ini
[Unit]
Description=meshd — batman-adv drone mesh daemon
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=/opt/mesh/.venv/bin/meshd -c /opt/mesh/config/mesh.yaml
EnvironmentFile=/etc/mesh/token.env   # optional MESH_MGMT_TOKEN override
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 6.2 Enable at Boot

```bash
sudo systemctl enable meshd
sudo systemctl start meshd
```

### 6.3 Lifecycle

`meshd` performs the full bring-up in order (see [Architecture](docs/Architecture.md)):

1. Load kernel modules (`batman_adv`, `cfg80211`, `mac80211`)
2. Bring up each radio in `radios[]` (mesh point or IBSS)
3. Create `bat0`, apply routing profile, assign `node.ip`
4. Apply QoS `tc` classes
5. Start supervised services (gpsd, alfred-gpsd, MAVLink forwarder, video, dashboard, management plane)

Tear-down reverses the same steps; `systemctl stop meshd` restores radios to
managed mode.

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

### 7.3 MAVLink Forwarding via meshd

No custom scripts or systemd units needed — `meshd` runs a threaded MAVLink
forwarder supervised by the daemon:

```yaml
telemetry:
  gps:
    enabled: true
    device: null            # auto-detect (/dev/ttyUSB0, /dev/ttyAMA0, ...)
  mavlink:
    enabled: true
    fc_serial: /dev/ttyACM0
    fc_baud: 921600
    gcs_ip: 10.0.0.100      # ground station
    gcs_port: 14550         # QGC / Mission Planner UDP
    local_port: 14551       # return path (GCS → FC)
    stream_rate_hz: 10
```

The forwarder:
- Reads MAVLink from the flight controller serial port
- Forwards telemetry to the GCS over the mesh (UDP)
- Receives GCS commands and writes them back to the FC
- Publishes GPS from the FC into the mesh (alfred type 128)
- Restarts automatically if the FC serial reconnects

QoS gives `udp/tcp:14550-14555` a strict priority class so control traffic
wins over video on congested links.

### 7.4 Ground Station Connection

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

### 8.2 Sender Configuration

Enable the sender on the drone in `mesh.yaml`:

```yaml
video:
  mode: sender
  source_device: /dev/video0    # auto-detect, or libcamera / nvidia / test / file
  caps: "video/x-raw,width=1280,height=720,framerate=30/1"
  bitrate_kbps: 4000
  transport: unicast            # unicast | multicast
  fec: true                     # RTP ULP FEC
  dest_ip: 10.0.0.100
  dest_port: 5000
```

`meshd` builds and supervises the `gst-launch-1.0` pipeline, choosing the
source automatically (v4l2 USB camera, `libcamerasrc` on Pi, NVENC on Jetson,
a test pattern, or a file replay) and inserting ULP FEC
(`rtpulpfecenc`/`rtpulpfecdec`) when `fec: true`.

### 8.3 Receiver Configuration

On the ground station:

```yaml
video:
  mode: receiver
  dest_port: 5000
```

The receiver pipeline performs `rtph264depay → avdec_h264 → autovideosink`
with FEC de-interleaving.

### 8.4 Manual Equivalents (for reference)

**Raspberry Pi Camera (libcamerasrc):**

```bash
# Medium quality (1280x720, 30fps, ~4 Mbps)
gst-launch-1.0 -v libcamerasrc \
    ! video/x-raw,width=1280,height=720,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=4000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

**Jetson Camera (nvarguscamerasrc):**

```bash
gst-launch-1.0 -v nvarguscamerasrc \
    ! video/x-raw,width=1280,height=720,framerate=30/1 \
    ! videoconvert \
    ! nvv4l2h264enc bitrate=4000 \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

**Ground station receiver:**

```bash
gst-launch-1.0 udpsrc port=5000 \
    ! application/x-rtp,encoding-name=H264 \
    ! rtph264depay \
    ! avdec_h264 \
    ! autovideosink
```

**VLC:** Media → Open Network Stream → `udp://@:5000`
**QGroundControl:** Application Settings → General → Video Settings → Source:
UDP h.264 Video Stream, UDP Port 5000.

### 8.5 Adaptive Bitrate

`video.adaptive: true` reserves a video QoS class (20mbit/40mbit) and enables
RTCP-driven adaptation (future work). For now, adapt `bitrate_kbps` per link
quality.

---

## 9. GPS Distribution via Alfred-GPSD

### 9.1 What is Alfred-GPSD

alfred-gpsd distributes GPS location information across the batman-adv mesh.
Every node can query the GPS position of every other node. `meshd` publishes
positions to **alfred type 128** (GPS) and fleet registry data to **type 129**.

### 9.2 Configure GPS Distribution

Enable in `mesh.yaml`:

```yaml
telemetry:
  gps:
    enabled: true
    device: null              # auto-detect /dev/ttyUSB0, /dev/ttyAMA0, ...
    fixed_location: null      # "lat,lon,alt" for fixed ground stations
```

**On drones with GPS:** `meshd` starts `gpsd` on the auto-detected device and
runs `alfred-gpsd -s` to publish live position.

**On ground station (fixed location):**

```yaml
telemetry:
  gps:
    enabled: true
    fixed_location: "48.858222,2.2945,358"
```

**On drones with a flight controller:** MAVLink GPS (from the FC) is also
published into the mesh automatically when `telemetry.mavlink.enabled` is on.

### 9.3 Manual Equivalents (for reference)

```bash
# gpsd
sudo apt install gpsd gpsd-clients
# Start alfred daemon + alfred-gpsd
sudo alfred -i bat0 -b bat0 &
sudo alfred-gpsd -s
# Fixed location (ground station)
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

The dashboard exposes the same data as `GET /api/mesh/gps`.

---

## 10. Network Visualization & Dashboard

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

`meshd` supervises `alfred` and `batadv-vis` automatically. For manual use:

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

### 10.3 Web Dashboard

The dashboard is a Flask app **served in-process by `meshd`** — no separate
`mesh-api.py`, Flask service, or static files to install.

Enable it on the ground station:

```yaml
node:
  id: ground-station
  role: ground-station
  ip: 10.0.0.100
dashboard:
  enabled: true
  host: 0.0.0.0
  port: 8080
```

Access at **http://10.0.0.100:8080**.

**Features:**
- Force-directed D3.js topology graph
- Link quality indicators (strong/medium/weak)
- Node list with TQ metrics
- Neighbor list
- GPS positions from alfred type 128 (Leaflet map)
- Fleet nodes from alfred type 129

**JSON API served by meshd:**

| Endpoint | Description |
|----------|-------------|
| `/api/mesh/status` | Aggregated health: node/gateway counts |
| `/api/mesh/topology` | batadv-vis JSON topology |
| `/api/mesh/originators` | `batctl oj` |
| `/api/mesh/neighbors` | `batctl nj` |
| `/api/mesh/interfaces` | `batctl if` |
| `/api/mesh/gateways` | `batctl gwj` |
| `/api/mesh/gps` | GPS positions (alfred type 128) |
| `/api/mesh/nodes` | Fleet registry (alfred type 129) |
| `/api/health` | meshd process health |

### 10.4 Management Plane

The dashboard is read-only. For control, use the JSON-RPC management plane
served by `meshd` (UDP, token-authenticated):

```bash
meshctl nodes                    # fleet from alfred type 129
meshctl -d 10.0.0.3 status       # remote status
meshctl -d 10.0.0.3 ping
meshctl -d 10.0.0.3 restart
```

---

## 11. Performance Tuning

### 11.1 Configuration Profiles

All of these are set declaratively in `mesh.yaml`:

| Scenario | orig_interval_ms | hop_penalty | fragmentation | Notes |
|----------|------------------|-------------|---------------|-------|
| **Low-latency (control)** | 500 | 10 | true | Fast topology updates, more overhead |
| **Balanced (default)** | 1000 | 15 | true | Good for most drone operations |
| **High-throughput (video)** | 1000 | 15 | true | Optimize for bandwidth |
| **Long-range (stability)** | 2000 | 30 | false | Less overhead, slower updates |
| **Highly mobile** | 500 | 10 | true | For fast-moving drones |

```yaml
mesh:
  routing_algo: BATMAN_V
  orig_interval_ms: 500
  hop_penalty: 10
  fragmentation: true
```

### 11.2 QoS Traffic Shaping

`meshd` applies strict-priority `tc` classes on `bat0` so control traffic is
never starved by video:

```yaml
qos:
  enabled: true
  classes:
    - name: command_and_control
      dscp: [CS6, EF]
      matches:
        - protocol: udp
          dport: 14550:14555
      rate: 2mbit
      ceil: 8mbit
      prio: 0
    - name: video
      dscp: [AF41, AF42, AF43]
      matches:
        - protocol: udp
          dport: 5000:5999
      rate: 20mbit
      ceil: 40mbit
      prio: 1
    - name: best_effort
      is_default: true
      prio: 2
```

### 11.3 Multiple Interfaces

Add one entry per radio:

```yaml
radios:
  - name: radioA
    iface: auto
    mode: auto
    band: 2.4g
    channel: 6
  - name: radioB
    iface: auto
    mode: auto
    band: 5g
    channel: 36
```

Requires `mesh.interface_routing: true`.

### 11.4 Network Coding

```yaml
mesh:
  network_coding: true
```

---

## 12. Troubleshooting

### 12.1 Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No neighbors visible | Mesh interface not up | `meshctl status`, check radios |
| High latency | Slow OGM interval | Decrease `orig_interval_ms` |
| Flapping routes | Unstable links | Increase `hop_penalty`, check signal |
| Gateway not selected | No gateway configured | `mesh.gateway: server` on gateway node |
| Packet loss | Interference | Change channel, check signal strength |
| Video stuttering | Bandwidth limited | Reduce resolution / bitrate, check QoS |
| MAVLink timeout | FC not connected | Check UART/USB connection, baud rate |
| Remote status fails | Token mismatch | Ensure `management.token` matches (or `MESH_MGMT_TOKEN`) |

### 12.2 Debugging Commands

```bash
# meshd control plane
meshctl status                 # full local status (radios, lifecycle, health)
meshctl nodes                  # fleet
journalctl -u meshd -f         # daemon logs

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
# meshd daemon (all supervised services report here)
journalctl -u meshd -f

# GPS / telemetry
journalctl -u meshd -f | grep -i gps

# MAVLink forwarder
journalctl -u meshd -f | grep -i mavlink

# Video pipeline
journalctl -u meshd -f | grep -i gst
```

### 12.4 Reset Mesh

```bash
# Restart the whole data plane
sudo systemctl restart meshd

# Stop the mesh entirely (radios return to managed mode)
sudo systemctl stop meshd

# Inspect why a step failed
journalctl -u meshd -f
meshctl status
```

---

## 13. Ad-Hoc (IBSS) Mode

### 13.1 When to Use Ad-Hoc Mode

Ad-hoc (IBSS) mode is an alternative to 802.11s mesh point mode for creating
the wireless link between drones. Use ad-hoc mode when:

- Your WiFi adapter does **not** support 802.11s mesh point mode
- You need quick setup for testing/development
- Your hardware driver only supports IBSS

**Check if your adapter supports mesh point mode:**
```bash
iw phy | grep -A8 "interface modes"
```

If you see `mesh point`, keep `radios[].mode: auto` (uses 802.11s). If you
only see `IBSS`, set `mode: ibss`.

### 13.2 Mesh Point vs Ad-Hoc Comparison

| Feature | Mesh Point (802.11s) | Ad-Hoc (IBSS) |
|---------|---------------------|---------------|
| **Batman-adv support** | Yes | Yes |
| **Auto-detection** | Yes (check `iw phy`) | Yes (`mode: auto` fallback) |
| **Performance** | Better throughput | Slightly lower |
| **Reliability** | More robust | Adequate for testing |
| **SAE authentication** | Supported | Not available |
| **Multi-hop native** | Yes (built into 802.11s) | No (batman-adv handles) |
| **Setup complexity** | Higher (wpa_supplicant) | Lower (`mode: ibss`) |

### 13.3 Using IBSS with meshd

Set `mode: ibss` (or leave `auto` — meshd falls back to IBSS when mesh point
is unavailable):

```yaml
node:
  id: drone-01
  ip: 10.0.0.3
mesh:
  id: drone-mesh
  essid: drone-mesh
  ibss_bssid: "02:12:34:56:78:9a"   # must match on all nodes
radios:
  - name: radioA
    iface: auto
    mode: ibss
    band: 2.4g
    channel: 6
```

`meshd` brings up IBSS with the fixed BSSID, attaches it to `bat0`, and
assigns the IP. The fixed BSSID is what makes independent nodes join the same
cell — without it each node could create its own random-BSSID IBSS network.

### 13.4 Manual Ad-Hoc Configuration (for reference)

#### Set Up Ad-Hoc Interface

```bash
sudo ip link set wlan0 down
sudo iwconfig wlan0 mode ad-hoc
sudo iwconfig wlan0 essid "drone-mesh"
sudo iwconfig wlan0 channel 6
sudo ip link set wlan0 up
```

#### Configure Batman-Adv

```bash
sudo modprobe batman_adv
sudo batctl if add wlan0
sudo ip link set bat0 up
sudo batctl routing_algo BATMAN_V
sudo ip addr add 10.0.0.2/24 dev bat0
```

#### Test Connectivity

```bash
sudo batctl o
ping 10.0.0.1
```

### 13.5 Building Batman-Adv from Source (Jetson Tegra)

The Jetson's Tegra kernel does not include batman-adv by default. You must
build it from source. See [Jetson Build](docs/Jetson-Build.md).

#### Prerequisites

```bash
sudo apt-get install -y build-essential git
```

#### Clone and Build

```bash
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
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules_install
sudo depmod -a
sudo modprobe batman_adv
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
| BSSID mismatch | All drones must use the same `mesh.ibss_bssid` |

---

## 14. Uninstalling the Mesh Network

### 14.1 Using the Uninstall Script

The `uninstall.sh` script completely removes the mesh configuration and
restores the system to its original state:

```bash
sudo ./uninstall.sh
```

**What it removes:**
- systemd service (`meshd.service`)
- `/opt/mesh/` installation directory, virtualenv, and config
- Kernel module loading configuration (`/etc/modules-load.d/batman-adv.conf`)
- IP forwarding settings from `/etc/sysctl.conf`
- Firewall rules (iptables, UFW, firewalld)
- Mesh log file (`/var/log/mesh.log`)

**What it does NOT remove:**
- Installed packages (batctl, alfred, etc.) - these remain available
- WiFi adapter drivers - these remain functional

### 14.2 Manual Cleanup

If you need to remove specific components manually without using the full
uninstall script:

```bash
# Stop and disable the mesh service
sudo systemctl stop meshd
sudo systemctl disable meshd

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

### Project Documentation
- [Wiki Home](docs/Home.md) — documentation index
- [Getting Started](docs/Getting-Started.md) — first-time setup
- [Configuration](docs/Configuration.md) — `mesh.yaml` reference
- [Monitoring](docs/Monitoring.md) — `meshctl`, dashboard, batctl commands
- [Video Streaming](docs/Video-Streaming.md) — pipeline configuration
- [Ground Station](docs/Ground-Station.md) — GCS + dashboard setup
- [Architecture](docs/Architecture.md) — meshd control plane + data plane
- [Troubleshooting](docs/Troubleshooting.md) — common issues

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
sudo ./install_packages.sh          # OS packages + kernel modules
sudo ./install.sh --with-all        # meshd into /opt/mesh/.venv + systemd

# Configuration (mesh.yaml — same on all nodes except node.id/ip)
sudo nano /opt/mesh/config/mesh.yaml
meshctl -c /opt/mesh/config/mesh.yaml validate   # dry-run validate

# Service
sudo systemctl start meshd
sudo systemctl status meshd

# Local control
meshctl status
meshctl ping
meshctl restart

# Fleet / remote management
meshctl nodes                        # alfred type 129 registry
meshctl -d 10.0.0.3 status           # remote node over mesh JSON-RPC
meshctl token                        # generate a management token

# Monitoring (data plane)
sudo batctl o          # Originators
sudo batctl n          # Neighbors
sudo batctl gwl        # Gateways
sudo batctl tg         # Translation table

# Visualization
batadv-vis -f json     # Topology JSON
# Dashboard: enable dashboard.enabled in mesh.yaml, open http://<node>:8080

# GPS
alfred-gpsd            # Get all GPS positions

# Uninstall
sudo ./uninstall.sh    # Complete removal
# Or manual cleanup:
sudo systemctl stop meshd && sudo systemctl disable meshd
sudo batctl if del bat0
sudo rmmod batman_adv

# Ad-Hoc / IBSS Mode (when mesh point not supported)
# radios[].mode: ibss  +  mesh.ibss_bssid (same on all nodes)

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
| `mesh.routing_algo` | BATMAN_V | BATMAN_V |
| `mesh.orig_interval_ms` | 1000 | 500-1000 |
| `mesh.hop_penalty` | 15 | 10-30 |
| `mesh.fragmentation` | true | true |
| `radios[].mode` | auto | auto (802.11s, fallback IBSS) |
| `radios[].band` / channel | 2.4g / 6 | per deployment |
| `management.token` | change-me | generated (`meshctl token`) |

---

*Document Version: 2.0 (meshd rewrite)*
*Last Updated: August 2026*
*Mesh Frequency: 2.4 GHz*
*Hardware: Raspberry Pi 4/5, Jetson Nano/Orin*
