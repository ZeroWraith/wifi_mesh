# Getting Started

This guide walks through setting up the batman-adv mesh network for the first time using the `meshd` control-plane daemon.

> [Home](Home.md) > Getting Started

## Prerequisites

- Linux system (Raspberry Pi OS, Ubuntu, or Jetson JetPack)
- WiFi adapter with Ad-hoc (IBSS) support
- Root/sudo access
- Internet connection (for initial package installation)
- Python 3.10+

## Step 1: Install Packages

```bash
sudo ./install_packages.sh
```

This installs:
- `batctl` — batman-adv control tool
- `alfred` — distributed data exchange
- `batadv-vis` — topology visualization
- GStreamer plugins — for video streaming
- `gpsd` / `gpsd-clients` — GPS distribution
- Kernel modules (batman_adv, cfg80211, mac80211)

## Step 2: Install meshd

```bash
sudo ./install.sh --with-all
```

This:
1. Runs `install_packages.sh`
2. Creates `/opt/mesh` and a Python virtualenv at `/opt/mesh/.venv`
3. Installs `meshd` + `meshctl` (plus telemetry and dashboard extras)
4. Writes a default config to `/opt/mesh/config/mesh.yaml`
5. Installs and enables `meshd.service`

## Step 3: Configure

Edit `mesh.yaml` on each node (there is a copy in `config/mesh.yaml` in the repo):

```bash
sudo nano /opt/mesh/config/mesh.yaml
```

**Minimum required changes** (unique per node):

| Field | What to set |
|-------|-------------|
| `node.id` | Unique ID: `drone-01`, `drone-02`, `ground-station`… |
| `node.ip` | Unique IP: `10.0.0.1`, `10.0.0.2`, … `10.0.0.100` (GCS) |
| `node.role` | `drone` \| `ground-station` \| `relay` |
| `management.token` | Same on all nodes — generate with `meshctl token` |

**Must be identical on all nodes:**

| Field | Default |
|-------|---------|
| `mesh.id` | `drone-mesh` |
| `mesh.essid` | `drone-mesh` |
| `mesh.ibss_bssid` | `02:12:34:56:78:9a` |
| `mesh.routing_algo` | `BATMAN_V` |
| `mesh.channel` (per radio) | `6` |

**Find your WiFi interface name:**

```bash
iw dev
# Look for "Interface" lines — e.g., wlp0s20f3, wlan0
```

The config's `radios[].iface` defaults to `auto` (first free wireless
interface), so you usually don't need to set it explicitly.

## Step 4: Validate and Start

```bash
# Validate the config (no changes made)
meshctl -c /opt/mesh/config/mesh.yaml validate

# Start the mesh
sudo systemctl start meshd

# Check status (should show radios "joined", lifecycle state "up")
meshctl status
```

Repeat on all drones with different `node.id` / `node.ip` values.

## Step 5: Ground Station

The ground station config sets `node.role: ground-station`, typically
`node.ip: 10.0.0.100`, and enables the dashboard:

```yaml
dashboard:
  enabled: true
  port: 8080
```

After `sudo systemctl start meshd`, open a browser at:

```
http://<gcs-ip>:8080
```

The dashboard shows a real-time force-directed graph of the mesh topology,
updated every 3 seconds.

## Step 6: Verify

```bash
meshctl status                 # daemon + radios + health
meshctl nodes                  # fleet nodes from the alfred registry
meshd -d <ip> status           # REMOTE node status over mesh JSON-RPC
```

Or use batctl directly:

```bash
sudo batctl o    # Show all mesh nodes (originators)
sudo batctl n    # Show direct neighbors
ping 10.0.0.1    # Test connectivity to another drone
```

## Boot Persistence

`install.sh` already enabled `meshd.service`, so it starts at boot:

```bash
sudo systemctl enable meshd    # done by install.sh
sudo systemctl start meshd
```

## Optional Features

| Feature | Config | Extra install |
|---------|--------|---------------|
| GPS distribution | `telemetry.gps.enabled: true` | gpsd + alfred-gpsd |
| MAVLink forwarding | `telemetry.mavlink.enabled: true` | `pip install meshd[telemetry]` |
| Video streaming | `video.mode: sender/receiver` | GStreamer |
| Dashboard | `dashboard.enabled: true` | `pip install meshd[dashboard]` |
| QoS | `qos.enabled: true` | — |

## Next Steps

- [Configuration](Configuration.md) — full `mesh.yaml` reference
- [Video Streaming](Video-Streaming.md) — stream camera over the mesh
- [Ground Station](Ground-Station.md) — connect QGroundControl
- [Monitoring](Monitoring.md) — check mesh health