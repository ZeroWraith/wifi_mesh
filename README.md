# Batman-Adv Drone Mesh Network

![Platform](https://img.shields.io/badge/platform-Linux-lightgrey)
![Shell](https://img.shields.io/badge/language-Bash-green)
![Batman-Adv](https://img.shields.io/badge/batman--adv-Layer%202%20mesh-blue)

True peer-to-peer WiFi mesh networking for drone swarms using batman-adv. Every drone is an identical peer — no hierarchy, no central controller, automatic self-healing.

## Features

- **Self-healing mesh** — automatic reroute within 3-5 seconds when nodes fail
- **True peer-to-peer** — every drone runs identical configuration
- **Multi-hop routing** — traffic routes through intermediate drones transparently
- **Video streaming** — GStreamer H.264 over UDP via mesh
- **MAVLink integration** — forward flight controller telemetry to ground station
- **GPS distribution** — share GPS positions across the mesh via alfred
- **Web dashboard** — real-time D3.js visualization of mesh topology
- **Ad-hoc fallback** — works with adapters that don't support 802.11s

## Architecture

```
TRUE PEER MESH (No Hierarchy):

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

Every node can reach every other node via multi-hop.
Batman-adv handles all routing automatically.
```

## Supported Hardware

| Device | CPU | Role |
|--------|-----|------|
| Raspberry Pi 4/5 | Quad ARM Cortex-A72/A76 | Companion computer |
| Jetson Nano/Orin | Quad ARM / 6-core Arm | Vision/AI companion |
| Any x86 Linux PC | Various | Ground station |

## Quick Start

```bash
# 1. Install dependencies (run once per drone)
sudo ./install_packages.sh

# 2. Edit configuration
nano config.sh    # Set DRONE_IP, MESH_IFACE, MESH_ID

# 3. Start mesh (Ad-hoc mode — works on most adapters)
sudo ./setup_adhoc.sh
```

For ground station:

```bash
sudo ./setup_ground_station.sh
```

Access the dashboard at **http://localhost:8080**

## Script Reference

| Script | Purpose |
|--------|---------|
| `config.sh` | Configuration — IP, mesh ID, channel, batman settings |
| `install_packages.sh` | Install required packages (batctl, alfred, GStreamer, etc.) |
| `install.sh` | Install scripts to `/opt/mesh` and set up systemd service |
| `setup_mesh.sh` | Configure batman-adv mesh (802.11s mesh point mode) |
| `setup_adhoc.sh` | Configure batman-adv mesh (Ad-hoc/IBSS mode, auto-detects) |
| `setup_ground_station.sh` | Full ground station setup with web dashboard |
| `start_mesh.sh` | Start the mesh network (loads modules, runs setup) |
| `stop_mesh.sh` | Stop the mesh network (802.11s mode) |
| `stop_adhoc.sh` | Stop the mesh network (Ad-hoc mode, restores managed WiFi) |
| `stop_gcs_mesh.sh` | Stop ground station mesh |
| `mesh_status.sh` | Display mesh status — neighbors, routes, gateways, stats |
| `mesh_video_sender.sh` | Stream video file over UDP via mesh (GStreamer) |
| `mesh_video_receiver.sh` | Receive and display H.264 video stream (GStreamer) |
| `build_batman_adv.sh` | Build batman-adv kernel module from source (Jetson Tegra) |
| `uninstall.sh` | Remove all mesh configuration and restore system defaults |

## Dashboard

The web dashboard provides real-time mesh topology visualization:

- **Force-directed graph** — interactive D3.js network visualization
- **Link quality indicators** — strong/medium/weak with color coding
- **Node list** — all discovered mesh nodes with TQ metrics
- **Neighbor list** — direct neighbors and connection quality
- **Auto-refresh** — updates every 3 seconds

Start the dashboard manually:

```bash
cd mesh_dashboard && python3 app.py
# Access at http://localhost:8080
```

## Key Configuration

Edit `config.sh` on each drone:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DRONE_IP` | `10.0.0.3` | Unique IP for this drone (10.0.0.X) |
| `PHYS_IFACE` | `wlp0s20f3` | WiFi interface (auto-detected if empty) |
| `MESH_ID` | `drone-mesh` | Must be same on all drones |
| `MESH_CHANNEL` | `6` | Must be same on all drones |
| `BATMAN_ROUTING` | `BATMAN_IV` | `BATMAN_V` recommended for drones |
| `GATEWAY_MODE` | `off` | Set `server` to share internet |

## Documentation

- **[Full Implementation Guide](BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md)** — comprehensive 1900-line reference covering protocol details, hardware setup, and advanced configuration
- **[docs/](docs/)** — wiki-style documentation organized by topic

## Video Streaming

```bash
# Sender (on drone)
./mesh_video_sender.sh 10.0.0.100 5000 /path/to/video.mp4

# Receiver (on ground station)
./mesh_video_receiver.sh 5000
```

## Troubleshooting

```bash
# Check mesh status
sudo ./mesh_status.sh

# Check batman-adv neighbors
sudo batctl o    # originators
sudo batctl n    # neighbors

# Check kernel module
lsmod | grep batman

# View logs
cat /var/log/mesh.log
```

See [docs/Troubleshooting.md](docs/Troubleshooting.md) for detailed debugging.

## Uninstall

```bash
sudo ./uninstall.sh
```

Removes systemd services, scripts, kernel config, firewall rules, and IP forwarding settings. Does not remove installed packages.
