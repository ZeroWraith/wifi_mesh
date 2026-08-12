# Ground Station Setup

Setting up the ground station PC to communicate with drones over the mesh network.

> [Home](Home.md) > Ground Station

## Overview

The ground station is a Linux PC that joins the batman-adv mesh as a peer node. It receives telemetry from drones, sends commands, and visualizes the mesh topology via a web dashboard.

## Quick Setup

```bash
sudo ./setup_ground_station.sh
```

This single script handles everything:
1. Installs all required packages
2. Configures WiFi in ad-hoc mode
3. Sets up batman-adv mesh
4. Assigns IP `10.0.0.100`
5. Starts the web dashboard on port 8080
6. Creates systemd services for persistence

## Ground Station Configuration

The ground station uses hardcoded settings (not from `config.sh`):

| Setting | Value |
|---------|-------|
| IP Address | `10.0.0.100` |
| Mesh ESSID | `drone-mesh` |
| BSSID | `02:12:34:56:78:9a` |
| Channel | `6` |
| Routing Algorithm | `BATMAN_IV` |

**Important:** These must match the drone configuration. If you changed `MESH_ID` or `MESH_CHANNEL` on drones, update `setup_ground_station.sh` accordingly.

## Web Dashboard

### Access

After setup, open a browser to:

```
http://localhost:8080
```

### Features

- **Force-directed graph** — interactive D3.js visualization of mesh topology
- **Link quality** — color-coded: green (strong), orange (medium), red (weak)
- **Node list** — all discovered mesh nodes with TQ metrics
- **Neighbor list** — direct neighbors and connection quality
- **Network stats** — node count, neighbor count
- **Auto-refresh** — updates every 3 seconds
- **Zoom/pan** — mouse wheel to zoom, drag to pan
- **Drag nodes** — drag individual nodes to reposition

### API Endpoints

The dashboard provides a REST API:

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard HTML page |
| `GET /api/mesh/status` | Overall mesh status (node count, bat0 state, etc.) |
| `GET /api/mesh/topology` | Full mesh topology from batadv-vis |
| `GET /api/mesh/originators` | All mesh nodes (batctl oj) |
| `GET /api/mesh/neighbors` | Direct neighbors (batctl nj) |
| `GET /api/mesh/interfaces` | Batman-adv interfaces (batctl if) |
| `GET /api/mesh/gateways` | Available gateways (batctl gwj) |
| `GET /api/mesh/gps` | GPS positions of all nodes |

### Manual Dashboard Start

If you need to start the dashboard separately:

```bash
cd mesh_dashboard
python3 app.py
```

Requires Flask: `pip3 install flask`

## Connecting QGroundControl

### UDP Connection

1. Open QGroundControl
2. Application Settings -> Comm Links
3. Add new connection:
   - Type: **UDP**
   - Port: **14550**
4. Connect — telemetry flows via batman-adv mesh

### MAVLink Forwarding

For MAVLink forwarding from drone flight controllers, see the full guide:
[BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md](../BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md#7-mavlink-integration)

## Connecting Mission Planner

1. Open Mission Planner
2. Select **UDP** port **14550**
3. Click Connect
4. Telemetry flows via batman-adv mesh

## Systemd Services

The setup creates two systemd services:

### batman-gcs.service

```bash
sudo systemctl status batman-gcs
sudo systemctl start batman-gcs
sudo systemctl stop batman-gcs
```

### mesh-dashboard.service

```bash
sudo systemctl status mesh-dashboard
sudo systemctl start mesh-dashboard
sudo systemctl stop mesh-dashboard
```

## Stopping the Ground Station

```bash
sudo ./stop_gcs_mesh.sh
```

This:
1. Stops alfred and batadv-vis
2. Removes bat0 interface
3. Restores WiFi to managed mode
4. Re-enables NetworkManager

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Dashboard not loading | Check `systemctl status mesh-dashboard` |
| No nodes in dashboard | Verify mesh on drones, wait 10-30 seconds |
| Cannot connect QGC | Check UDP port 14550, verify bat0 is up |
| WiFi not connecting | Run `sudo rfkill unblock wifi` |
