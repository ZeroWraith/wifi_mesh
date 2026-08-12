# Configuration

Full reference for the `config.sh` parameters.

> [Home](Home.md) > Configuration

## Overview

Each drone has its own copy of `config.sh`. Most settings must be identical across all drones — only `DRONE_IP` is unique per drone.

## Drone Identity

| Parameter | Default | Required | Description |
|-----------|---------|----------|-------------|
| `DRONE_IP` | `10.0.0.3` | Yes | Unique IP for this drone (format: `10.0.0.X`) |
| `PHYS_IFACE` | `wlp0s20f3` | No | WiFi interface name. Leave empty for auto-detection |
| `MESH_IFACE` | `bat0` | No | Virtual mesh interface. Usually `bat0` |
| `EXTERNAL_IFACE` | `""` | No | Additional interface for internet/GCS access |

**IP addressing scheme:**

```
Drone 1:    10.0.0.1
Drone 2:    10.0.0.2
Drone 3:    10.0.0.3
...
Ground:     10.0.0.100
```

## Mesh Network Settings

| Parameter | Default | Must Match | Description |
|-----------|---------|------------|-------------|
| `MESH_ID` | `drone-mesh` | Yes | Network name — must be identical on all drones |
| `MESH_BSSID` | `02:12:34:56:78:9a` | Yes | Fixed BSSID for ad-hoc mode — must be identical |
| `MESH_CHANNEL` | `6` | Yes | WiFi channel — must be identical on all drones |
| `MESH_BAND` | `2g` | Yes | Frequency band: `2g` for 2.4GHz, `5g` for 5GHz |

**Channel selection:**
- 2.4 GHz: channels 1-11 (use 1, 6, or 11 to avoid overlap)
- 5 GHz: channels 36-165

## Batman-Adv Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BATMAN_ROUTING` | `BATMAN_IV` | Routing algorithm. Use `BATMAN_V` for throughput-based routing (recommended for drones) |
| `GATEWAY_MODE` | `off` | Gateway mode: `off`, `client`, or `server` |
| `GW_DOWNLOAD` | `100` | Gateway download bandwidth in Mbit (only if `GATEWAY_MODE=server`) |
| `GW_UPLOAD` | `100` | Gateway upload bandwidth in Mbit (only if `GATEWAY_MODE=server`) |

**Routing algorithm comparison:**

| Algorithm | Metric | Best for |
|-----------|--------|----------|
| `BATMAN_IV` | TQ (Transmission Quality) | Simple setups, older hardware |
| `BATMAN_V` | Throughput | Drone swarms, video streaming |

## Network Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NETMASK` | `255.255.255.0` | Subnet mask for mesh network |
| `BROADCAST` | `10.0.0.255` | Broadcast address |
| `DNS_SERVER` | `8.8.8.8` | DNS server for internet access via gateway |

## Advanced Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `WIFI_DRIVER_OPTIONS` | `""` | Driver-specific options (e.g., `rtwl8xxcu rtw_channel=6` for Alfa AWUS036ACH) |
| `MESH_MAC` | `""` | Custom MAC address for mesh interface (leave empty for auto) |
| `BATMAN_PARAMS` | `""` | Additional batman-adv module parameters |

## Logging

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEBUG_LOG` | `false` | Enable debug logging to `/var/log/mesh.log` |
| `LOG_LEVEL` | `info` | Log level: `info`, `debug`, `warn`, `error` |

## Example Configurations

### Drone (Default)

```bash
DRONE_IP="10.0.0.3"
PHYS_IFACE="wlp0s20f3"
MESH_IFACE="bat0"
MESH_ID="drone-mesh"
MESH_BSSID="02:12:34:56:78:9a"
MESH_CHANNEL=6
MESH_BAND="2g"
BATMAN_ROUTING="BATMAN_IV"
GATEWAY_MODE="off"
```

### Drone (BATMAN_V with video)

```bash
DRONE_IP="10.0.0.2"
PHYS_IFACE=""
MESH_IFACE="bat0"
MESH_ID="drone-swarm-001"
MESH_BSSID="02:12:34:56:78:9a"
MESH_CHANNEL=1
MESH_BAND="2g"
BATMAN_ROUTING="BATMAN_V"
GATEWAY_MODE="off"
DEBUG_LOG=true
LOG_LEVEL="debug"
```

### Gateway Drone (shares internet)

```bash
DRONE_IP="10.0.0.1"
PHYS_IFACE="wlan0"
MESH_IFACE="bat0"
EXTERNAL_IFACE="eth0"
MESH_ID="drone-mesh"
MESH_BSSID="02:12:34:56:78:9a"
MESH_CHANNEL=6
BATMAN_ROUTING="BATMAN_V"
GATEWAY_MODE="server"
GW_DOWNLOAD=100
GW_UPLOAD=100
```

### Ground Station

The ground station uses hardcoded settings in `setup_ground_station.sh`:
- IP: `10.0.0.100`
- ESSID: `drone-mesh`
- BSSID: `02:12:34:56:78:9a`
- Channel: 6
- Routing: `BATMAN_IV`
