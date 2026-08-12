# Monitoring

Checking mesh network health and status.

> [Home](Home.md) > Monitoring

## mesh_status.sh

The primary monitoring tool. Run from any mesh node:

```bash
sudo ./mesh_status.sh
```

### Output Sections

**[Module]**
Shows whether the batman_adv kernel module is loaded.

**[Interfaces]**
Status of the physical WiFi interface and virtual bat0 interface, including IP address.

**[Mesh Neighbors]**
Direct neighbors discovered by batman-adv (from `batctl n`). Shows MAC address, link quality (TQ), and which interface the neighbor is on.

**[Routing Table]**
All originators in the mesh (from `batctl o`). Shows which nodes are reachable, the best next-hop, TQ value, and outgoing interface.

**[Gateway Status]**
Available gateways and their bandwidth (from `batctl gw`).

**[Translation Tables]**
Local and global MAC address tables (from `batctl tl` and `batctl tg`). Shows which client MACs are connected to which nodes.

**[Statistics]**
RX/TX byte counts on bat0 and a connectivity test (ping common IPs).

### JSON Output

For programmatic access:

```bash
sudo ./mesh_status.sh --json
```

Returns a JSON object with:

```json
{
  "drone_ip": "10.0.0.3",
  "mesh_id": "drone-mesh",
  "neighbors": ["aa:bb:cc:dd:ee:01  ..."],
  "timestamp": "2026-08-12T10:30:00+00:00"
}
```

## batctl Commands

The `batctl` tool provides direct access to batman-adv internals.

### Core Commands

| Command | Description |
|---------|-------------|
| `batctl o` | Show originators (all mesh nodes) |
| `batctl n` | Show direct neighbors |
| `batctl if` | Show interfaces added to batman-adv |
| `batctl gwl` | Show available gateways |
| `batctl tg` | Show global translation table |
| `batctl tl` | Show local translation table |

### JSON Output

Append `j` to any command for JSON output:

| Command | Description |
|---------|-------------|
| `batctl oj` | Originators in JSON |
| `batctl nj` | Neighbors in JSON |
| `batctl gwj` | Gateways in JSON |
| `batctl tgj` | Translation table in JSON |

### Diagnostic Commands

| Command | Description |
|---------|-------------|
| `batctl tp <MAC>` | Test throughput to a specific node |
| `batctl traceroute <IP>` | Trace route through the mesh |
| `batctl event` | Monitor batman-adv events in real-time |

### Reading TQ Values

TQ (Transmission Quality) ranges from 0-255:

| TQ Range | Quality | Meaning |
|----------|---------|---------|
| 200-255 | Excellent | Strong signal, direct neighbor |
| 128-199 | Good | Reliable connection |
| 64-127 | Fair | Multi-hop or weak signal |
| 0-63 | Poor | Unstable, may drop |

**Percentage:** `TQ / 255 * 100`

## System Logs

### Batman-Adv Kernel Messages

```bash
dmesg | grep batman-adv
```

### Mesh Service Logs

```bash
journalctl -u batman-mesh -f          # Live follow
journalctl -u batman-mesh --since today  # Today's logs
```

### Dashboard Logs

```bash
journalctl -u mesh-dashboard -f
```

### Mesh Log File

```bash
cat /var/log/mesh.log
tail -f /var/log/mesh.log    # Follow
grep ERROR /var/log/mesh.log # Filter errors
```

## Dashboard Monitoring

The web dashboard at `http://localhost:8080` provides real-time visual monitoring.

See [Ground Station](Ground-Station.md) for dashboard details.

## Script Output Example

```
============================================
 Batman-Adv Mesh Network Status
============================================

[Module]
  batman_adv: Loaded

[Interfaces]
  wlp0s20f3: up (MAC: aa:bb:cc:dd:ee:03)
  bat0: up (IP: 10.0.0.3)

[Mesh Neighbors]
  aa:bb:cc:dd:ee:01   255   wlp0s20f3
  aa:bb:cc:dd:ee:02   243   wlp0s20f3

[Routing Table]
  aa:bb:cc:dd:ee:01   255   aa:bb:cc:dd:ee:01   (wlp0s20f3)
  aa:bb:cc:dd:ee:02   243   aa:bb:cc:dd:ee:01   (wlp0s20f3)

[Gateway Status]
  No gateways available

[Statistics]
  RX: 12.45 MB
  TX: 8.32 MB

============================================
  Last updated: Wed Aug 12 10:30:00 UTC 2026
============================================
```
