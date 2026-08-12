# Getting Started

This guide walks through setting up the batman-adv mesh network for the first time.

> [Home](Home.md) > Getting Started

## Prerequisites

- Linux system (Raspberry Pi OS, Ubuntu, or Jetson JetPack)
- WiFi adapter with Ad-hoc (IBSS) support
- Root/sudo access
- Internet connection (for initial package installation)

## Step 1: Install Packages

```bash
sudo ./install_packages.sh
```

This installs:
- `batctl` — batman-adv control tool
- `alfred` — distributed data exchange
- GStreamer plugins — for video streaming
- `pymavlink` — MAVLink Python library
- Kernel modules (batman_adv, cfg80211, mac80211)

## Step 2: Configure

Edit `config.sh` on each drone:

```bash
nano config.sh
```

**Minimum required changes:**

| Parameter | What to set |
|-----------|-------------|
| `DRONE_IP` | Unique IP: `10.0.0.1`, `10.0.0.2`, etc. |
| `PHYS_IFACE` | Your WiFi interface name (leave empty for auto-detect) |
| `MESH_ID` | Same on all drones (default: `drone-mesh`) |
| `MESH_CHANNEL` | Same on all drones (default: `6`) |

**Find your WiFi interface name:**

```bash
iw dev
# Look for "Interface" lines — e.g., wlp0s20f3, wlan0
```

## Step 3: Start Mesh (Drone)

```bash
sudo ./setup_adhoc.sh
```

The script will:
1. Auto-detect your WiFi interface
2. Check for mesh point support (falls back to ad-hoc if needed)
3. Create batman-adv interface (bat0)
4. Assign IP address
5. Verify the setup

**Repeat on all drones** with different `DRONE_IP` values.

## Step 4: Start Mesh (Ground Station)

```bash
sudo ./setup_ground_station.sh
```

This sets up the ground station at `10.0.0.100` and starts the web dashboard.

## Step 5: Verify

Check mesh status from any node:

```bash
sudo ./mesh_status.sh
```

Or use batctl directly:

```bash
sudo batctl o    # Show all mesh nodes (originators)
sudo batctl n    # Show direct neighbors
ping 10.0.0.1    # Test connectivity to another drone
```

## Step 6: Access Dashboard

Open a browser and go to:

```
http://localhost:8080
```

The dashboard shows a real-time force-directed graph of the mesh topology, updated every 3 seconds.

## Boot Persistence

To auto-start mesh at boot:

```bash
# Install the systemd service
sudo ./install.sh

# Enable and start
sudo systemctl enable batman-mesh
sudo systemctl start batman-mesh
```

## Next Steps

- [Configuration](Configuration.md) — tune mesh parameters
- [Video Streaming](Video-Streaming.md) — stream camera over mesh
- [Ground Station](Ground-Station.md) — connect QGroundControl
- [Monitoring](Monitoring.md) — check mesh health
