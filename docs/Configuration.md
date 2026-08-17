# Configuration

Full reference for the `mesh.yaml` parameters used by `meshd`.

> [Home](Home.md) > Configuration

## Overview

Each node has its own copy of `mesh.yaml` (installed to
`/opt/mesh/config/mesh.yaml`). A starter file is written by
`meshd --init -c <path>`, and a fully-commented example lives at
`config/mesh.yaml` in the repository.

**Node-unique settings:** `node.id`, `node.ip`, `node.role`.
**Settings that must match across all nodes:** `mesh.*`, `radios[]` channel/band,
and `management.token`.

Validate a config without starting anything:

```bash
meshctl -c /opt/mesh/config/mesh.yaml validate
```

## Top-level structure

```yaml
node:
mesh:
radios:
qos:
telemetry:
video:
dashboard:
management:
```

## `node` — Identity

| Field | Default | Description |
|-------|---------|-------------|
| `id` | `drone-01` | Unique per node `[a-zA-Z0-9_-]`, ≤64 chars |
| `role` | `drone` | `drone` \| `ground-station` \| `relay` |
| `ip` | `10.0.0.3` | IPv4 address on `bat0` — unique per node |
| `netmask` | `/24` | CIDR suffix, e.g. `/24` |
| `hostname` | `null` | Optional hostname to apply |

**IP addressing scheme:**

```yaml
node:
  id: drone-01
  role: drone
  ip: 10.0.0.3
```

```
Drone 1:    10.0.0.1
Drone 2:    10.0.0.2
Drone 3:    10.0.0.3
...
Ground:     10.0.0.100
```

## `mesh` — Network Settings

| Field | Default | Must match | Description |
|-------|---------|------------|-------------|
| `id` | `drone-mesh` | Yes | Mesh identifier |
| `essid` | `drone-mesh` | Yes | 802.11 SSID (ad-hoc) |
| `ibss_bssid` | `02:12:34:56:78:9a` | Yes | Fixed BSSID for IBSS cell |
| `routing_algo` | `BATMAN_V` | Yes | `BATMAN_V` (throughput) \| `BATMAN_IV` (TQ) |
| `orig_interval_ms` | `1000` | — | OGM beacon interval |
| `hop_penalty` | `15` | — | Penalty per hop (0-255) |
| `fragmentation` | `true` | — | Enable batman-adv frags |
| `interface_routing` | `true` | — | Required for multi-radio nodes |
| `network_coding` | `false` | — | BATMAN network coding |
| `gateway` | `off` | — | `off` \| `server` \| `client` |
| `gateway_download_mbit` | `100` | — | Advertised downlink (server mode) |
| `gateway_upload_mbit` | `100` | — | Advertised uplink (server mode) |
| `external_iface` | `null` | — | e.g. `eth0` — only when `gateway=server` |
| `dns_server` | `8.8.8.8` | — | DNS advertised by the gateway |

**Routing algorithm comparison:**

| Algorithm | Metric | Best for |
|-----------|--------|----------|
| `BATMAN_IV` | TQ (Transmission Quality) | Simple setups, older hardware |
| `BATMAN_V` | Throughput | Drone swarms, video streaming |

**Channel selection:**
- 2.4 GHz: channels 1-11 (use 1, 6, or 11 to avoid overlap)
- 5 GHz: channels 34-177
- 6 GHz: channels (Wi-Fi 6E), experimental

## `radios` — Radio Farm

A list; add one entry per radio on multi-radio nodes.

| Field | Default | Description |
|-------|---------|-------------|
| `name` | `radioA` | Label (used in status) |
| `iface` | `auto` | Interface name, or `auto` (first free wireless iface) |
| `mode` | `auto` | `auto` \| `mesh` (802.11s) \| `ibss` (ad-hoc) |
| `band` | `2.4g` | `2.4g` \| `5g` \| `6g` |
| `channel` | `6` | Radio channel (2.4g: 1-14, 5g: 34-177) |
| `txpower_dbm` | `null` | Explicit TX power (1-30 dBm) when set |
| `mac` | `null` | Custom MAC for the mesh interface |
| `driver_options` | `""` | Driver options, e.g. `rtw88 rtw_channel=6` |

## `qos` — Traffic Shaping

Strict-priority classes applied via `tc`. First class listed is strictest.

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Apply QoS on startup |
| `classes[]` | — | Ordered list of classes |

Per class:

| Field | Description |
|-------|-------------|
| `name` | Class name |
| `dscp` | DSCP values marked on these flows, e.g. `[CS6, EF]` |
| `matches[]` | Flow selectors: `protocol`, `dport`, `sport`, `dscp` |
| `rate` | Guaranteed bandwidth, e.g. `2mbit` |
| `ceil` | Ceiling bandwidth, e.g. `8mbit` |
| `prio` | Strict priority (0 = strictest) |
| `is_default` | Matches all remaining traffic |

## `telemetry` — GPS + MAVLink

### `telemetry.gps`

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Publish GPS over the mesh |
| `device` | `null` | Serial device, or `null` = auto-detect `/dev/ttyUSB0`… |
| `fixed_location` | `null` | `"lat,lon,alt"` for ground stations without GPS |

### `telemetry.mavlink`

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `false` | Forward FC telemetry to the GCS |
| `fc_serial` | `/dev/ttyACM0` | Flight-controller serial port |
| `fc_baud` | `921600` | Serial baud rate |
| `gcs_ip` | `10.0.0.100` | Ground-station IP |
| `gcs_port` | `14550` | GCS telemetry UDP port (QGC/Mission Planner) |
| `local_port` | `14551` | Local return-path UDP port |
| `stream_rate_hz` | `10` | Requested MAVLink stream rate |

## `video` — GStreamer Pipeline

| Field | Default | Description |
|-------|---------|-------------|
| `mode` | `off` | `off` \| `sender` \| `receiver` (note: quote as string) |
| `source_device` | `null` | Auto-detect; or `/dev/video0`, `libcamera`, `nvidia`, `test`, a file |
| `caps` | `video/x-raw,width=1280,height=720,framerate=30/1` | Source caps |
| `bitrate_kbps` | `4000` | x264 / NVENC bitrate |
| `transport` | `unicast` | `unicast` \| `multicast` |
| `fec` | `true` | Insert RTP ULP FEC elements |
| `adaptive` | `true` | RTCP-driven adaptive bitrate (config metadata) |
| `dest_ip` | `10.0.0.100` | Receiver IP (sender mode) |
| `dest_port` | `5000` | RTP destination / listen port |
| `multicast_group` | `239.255.77.77` | Multicast group (multicast mode) |

## `dashboard` — Web UI

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `false` | Serve the dashboard on this node |
| `host` | `0.0.0.0` | Bind address |
| `port` | `8080` | Listen port |
| `template_dir` | `null` | Override the bundled template directory |

## `management` — Remote Plane

| Field | Default | Description |
|-------|---------|-------------|
| `token` | `change-me` | Shared token — **set this** (`meshctl token`) |
| `udp_port` | `9000` | JSON-RPC UDP port used by `meshctl -d <ip>` |
| `bind_interface` | `bat0` | Interface the RPC binds to |

> The token can be overridden at runtime with the `MESH_MGMT_TOKEN`
> environment variable (see `deploy/units/meshd.service`).

## Example Configurations

### Drone (default)

```yaml
node:
  id: drone-01
  role: drone
  ip: 10.0.0.3
mesh:
  id: drone-mesh
  essid: drone-mesh
  ibss_bssid: "02:12:34:56:78:9a"
  routing_algo: BATMAN_V
radios:
  - name: radioA
    iface: auto
    mode: auto
    band: 2.4g
    channel: 6
management:
  token: change-me   # generate with: meshctl token
```

### Ground station (dashboard + GPS)

```yaml
node:
  id: ground-station
  role: ground-station
  ip: 10.0.0.100
dashboard:
  enabled: true
  port: 8080
telemetry:
  gps:
    enabled: true
    fixed_location: "48.858222,2.2945,358"   # no GPS receiver installed
```

### Drone with video sender + MAVLink

```yaml
node:
  id: drone-02
  role: drone
  ip: 10.0.0.2
video:
  mode: sender
  source_device: /dev/video0
  bitrate_kbps: 4000
  dest_ip: 10.0.0.100
  dest_port: 5000
telemetry:
  mavlink:
    enabled: true
    fc_serial: /dev/ttyACM0
    fc_baud: 921600
    gcs_ip: 10.0.0.100
    gcs_port: 14550
```

### Gateway node (shares internet)

```yaml
node:
  id: drone-01
  role: relay
  ip: 10.0.0.1
mesh:
  gateway: server
  gateway_download_mbit: 100
  gateway_upload_mbit: 100
  external_iface: eth0

---

**See also:** [Getting Started](Getting-Started.md) · [Monitoring](Monitoring.md) · [Troubleshooting](Troubleshooting.md)