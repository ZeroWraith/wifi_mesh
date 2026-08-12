# Architecture

How batman-adv creates and manages the drone mesh network.

> [Home](Home.md) > Architecture

## What is Batman-Adv

Batman-adv (Better Approach To Mobile Ad-hoc Networking - advanced) is a **Linux kernel module** implementing a Layer 2 mesh routing protocol. It creates a virtual `bat0` interface that acts as an Ethernet switch connecting all mesh nodes.

**Key characteristics:**
- Runs in kernel space (minimal CPU/memory overhead)
- Operates at Layer 2 (transparent to IPv4/IPv6/ARP/DHCP)
- Self-healing: automatic reroute within 3-5 seconds when nodes fail
- In mainline Linux since 2011

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
```

Every node runs identical configuration (except IP address). There is no hierarchy — any drone can route traffic for any other drone.

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
2. Node B receives, records: "A reachable via direct link, metric=1000"
3. Node B re-broadcasts A's OGM (decremented TTL)
4. Node C receives B's re-broadcast
5. C compares: direct to A (if possible) vs. via B
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

Batman-adv automatically:
1. Discovers all paths via OGM flooding
2. Calculates best metric for each destination
3. Selects optimal path
4. Forwards packets at Layer 2 (transparent to IP)
5. Reroutes if any intermediate drone fails
```

## Translation Tables

**Local Translation Table (`batctl tl`):**
- Maps MAC addresses of clients connected to this node

**Global Translation Table (`batctl tg`):**
- Maps all client MACs across the entire mesh
- Shows which node each client is connected to

## Gateway Election

Any node can be a gateway:
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

Batman-adv sits on top of two possible wireless link types:

### 802.11s Mesh Point Mode
- Native WiFi mesh standard
- Requires `wpad-mesh` for SAE authentication
- Better performance and reliability
- Setup via `setup_mesh.sh`

### Ad-Hoc (IBSS) Mode
- Legacy WiFi ad-hoc networking
- Works with most WiFi adapters
- Simpler setup, no authentication
- Setup via `setup_adhoc.sh`

Both modes are transparent to batman-adv — it treats the wireless interface as a Layer 2 transport.

## Data Flow

```
Application (e.g., MAVLink)
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
