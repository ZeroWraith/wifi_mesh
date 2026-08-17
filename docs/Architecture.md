# Architecture

How batman-adv creates and manages the drone mesh network — and how the `meshd` control-plane daemon operates it.

> [Home](Home.md) > Architecture

## What is Batman-Adv

Batman-adv (Better Approach To Mobile Ad-hoc Networking - advanced) is a **Linux kernel module** implementing a Layer 2 mesh routing protocol. It creates a virtual `bat0` interface that acts as an Ethernet switch connecting all mesh nodes.

**Key characteristics:**
- Runs in kernel space (minimal CPU/memory overhead)
- Operates at Layer 2 (transparent to IPv4/IPv6/ARP/DHCP)
- Self-healing: automatic reroute within 3-5 seconds when nodes fail
- In mainline Linux since 2011

## Two Planes

Every node runs `meshd`, which owns two planes:

```
                    meshd (on every node)
   ┌──────────────────────────┬──────────────────────────┐
   │  DATA PLANE              │  CONTROL PLANE            │
   │  radios   (+802.11s/IBSS)│  lifecycle (steps)        │
   │  bat0 + batman-adv        │  local UNIX socket        │
   │  QoS (tc)                │  JSON-RPC over the mesh   │
   │  alfred / batadv-vis      │  services (supervision)  │
   │  telemetry/video/GPU      │  fleet registry (alfred) │
   └──────────────────────────┴──────────────────────────┘
```

## Network Model

```
+-----------+         +-----------+
|  Drone 1  |<------->|  Drone 2  |
| 10.0.0.1  |         | 10.0.0.2  |
+-----+-----+         +-----+-----+
      |                     |
      |    +-----------+    |
      +--->|  Drone 3  |<---+
           | 10.0.0.3  |
           +-----+-----+
                 |
            +----+----+
            | Ground  |
            | Station |
            |10.0.0.100|
            +---------+

Every node runs identical configuration (except IP address). There is no hierarchy — any drone can route traffic for any other drone.
```

## meshd Data Plane

On startup, `meshd` runs its **data-plane steps** in order:

1. **Prepare radios** — find interfaces, set channel/band/txpower
2. **Join 802.11** — mesh point (`iw mesh join`) or IBSS (`iw ad-hoc join`)
3. **Bring up batman-adv** — load module, add interfaces to `bat0`, apply routing settings (BATMAN_V, originator interval, fragmentation…)
4. **Configure IP** — assign `node.ip/netmask` to `bat0`
5. **QoS** — apply strict-priority `tc` classes (optional)
6. **Services** — start alfred, telemetry, video, dashboard (optional)

Each step is a **lifecycle step**: retried on failure, supervised while the
node runs, and rolled back in reverse order on shutdown so the adapter is
restored cleanly.

```
configuration.yml
   │
   v
meshd ── apply radios ── join wifi ── bat0 up ── ip assign ── services
   │         │              │          │           │            │
   └─────────┴──────────────┴──────────┴───────────┴────────────┘
                rollback order on stop (reverse of apply)
```

## meshd Control Plane

- **Lifecycle** — every node transitions `down → configuring → up` (or
  `degraded → failed`); state is exposed over the control socket.
- **Local control socket** — UNIX socket in the run dir; `meshctl
  status/ping/stop/restart` talks here.
- **Management plane (mesh)** — each node listens for JSON-RPC over UDP on
  `management.udp_port` and publishes its identity (`node_id`, `role`, `ip`)
  into the alfred registry (type 129). `meshctl -d <ip> status` reaches any
  node through the mesh; `meshctl nodes` lists the fleet.
- **Supervised services** — helpers (alfred, video pipeline, gpsd/alfred-gpsd)
  are restarted if they exit unexpectedly, and marked failed after too many
  restarts.

## How Routing Works

### OGM (Originator Message) Propagation

Every node broadcasts OGMs periodically (default: every 1 second):

```
OGM v2 Packet:
  Version:     2
  TTL:         50 (decremented at each hop)
  Sequence:    12345 (prevents loops)
  Originator:  aa:bb:cc:dd:ee:01 (sender MAC)
  Throughput:  1000 Mbps (measured link quality)
```

**Routing decision process:**
1. Node A broadcasts OGM with throughput=1000
2. Node B receives, records: "A reachable via direct, metric=1000"
3. Node B re-broadcasts A's OGM (decremented TTL)
4. Node C receives B's re-broadcast
5. C compares: direct to A (if possible) vs via B
6. C selects best path based on throughput metric

### BATMAN-V Algorithm

BATMAN-V uses throughput-based routing:

```
metric = throughput x (1 - packet_loss) / hop_count
```

**ELP (Echo Location Protocol):**
- Neighbor discovery without OGM flooding
- Measures actual throughput between direct neighbors
- Reduces overhead compared to BATMAN-IV

### Multi-Hop Routing

```
Drone 1 -> Drone 2 -> Drone 3 -> Drone 4
   |           |           |           |
   +-- 1 hop --+-- 2 hops -+-- 3 hops -+
```

Batman-adv automatically:
1. Discovers all paths via OGM flooding
2. Calculates best metric for each destination
3. Selects optimal path
4. Forwards packets at Layer 2 (transparent to IP)
5. Reroutes if any intermediate drone fails

## Translation Tables

**Local Translation Table (`batctl tl`):**
- Maps MAC addresses of clients connected to this node

**Global Translation Table (`batctl tg`):**
- Maps all client MACs across the entire mesh
- Shows which node each client is connected to

## Gateway Election

Any node can be a gateway (`mesh.gateway: server`):
- Nodes advertise gateway bandwidth via OGMs
- Clients measure TQ (transmission quality) to each gateway
- Score formula: `score = bandwidth x TQ`
- Automatic failover when gateway goes down

```
Gateway Selection:
  Gateway    Bandwidth    TQ     Score
  Node1      100/100      255    25500  <-- Selected
  Node2      100/100      220    22000
  Node3      100/100      180    18000
```

## Wireless Link Layer

Batman-adv sits on top of two possible wireless link types. meshd chooses
per-radio via `radios[].mode: auto` (prefers 802.11s, falls back to IBSS).

### 802.11s Mesh Point Mode
- Native WiFi mesh standard
- Better performance and reliability
- Mode `mesh` (or `auto` with a supporting adapter)

### Ad-Hoc (IBSS) Mode
- Legacy WiFi ad-hoc networking
- Works with most WiFi adapters
- Simpler setup, no authentication
- Mode `ibss`

Both modes are transparent to batman-adv — it treats the wireless interface as a Layer 2 transport.

## Data Flow

```
Application (e.g., MAVLink / video RTP)
    |
    v
IP Stack (10.0.0.X)
    |
    v
bat0 (batman-adv virtual interface)
    |
    v
Batman-adv routing (selects best next-hop)
    |
    v
Physical WiFi interface (wlan0/wlp0s20f3)
    |
    v
802.11 frame (mesh point or ad-hoc)
    |
    v
Air -> Neighbor drone
```

## Service Data Flows

### GPS distribution

```
GPS receiver -> gpsd -> alfred-gpsd --(alfred type 128)--> all nodes
Flight controller -> pymavlink forwarder --(alfred type 128)--> all nodes
Ground station fixed_location --(alfred type 128)--> all nodes
```

### MAVLink forwarding

```
Flight controller ──serial──▶ meshd (mavlink thread)
                                   │  UDP (gcs_ip:14550)
                                   ▼
                              Ground station (QGC / Mission Planner)
```

### Video

```
Camera/AI encode ──▶ meshd video sender (H.264 RTP over UDP)
                              │  mesh
                              ▼
              meshd video receiver ──▶ display / GCS video sink
```

### Fleet management

```
Each node ──alfred registry (type 129)──▶ all nodes
meshctl nodes  ->  local alfred registry
meshctl -d <ip> ->  UDP JSON-RPC to management.udp_port
```