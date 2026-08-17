# Ground Station Setup

Setting up the ground station PC to communicate with drones over the mesh network.

> [Home](Home.md) > Ground Station

## Overview

The ground station is a Linux PC that joins the batman-adv mesh as a peer node. It receives telemetry from drones, sends commands, and visualizes the mesh topology via the meshd web dashboard.

## Quick Setup

The ground station runs the same `meshd` stack as every other node — just with `role: ground-station`, a fixed IP, and the dashboard enabled.

```bash
sudo ./install_packages.sh
sudo ./install.sh --with-all
```

Then edit `/opt/mesh/config/mesh.yaml`:

```yaml
node:
  id: ground-station
  role: ground-station
  ip: 10.0.0.100
dashboard:
  enabled: true
  port: 8080
```

Start and verify:

```bash
sudo systemctl start meshd
meshctl status
```

## Ground Station Configuration

| Setting | Value |
|---------|-------|
| `node.role` | `ground-station` |
| `node.ip` | `10.0.0.100` |
| `mesh.id` / `essid` | `drone-mesh` (must match drones) |
| `mesh.ibss_bssid` | `02:12:34:56:78:9a` (must match drones) |
| radio channel | must match drones |

**Important:** `mesh.*`, radio channel/band, and `management.token` must match
the drone configuration. See [Configuration](Configuration.md).

## Web Dashboard

### Access

After `meshd` is running with `dashboard.enabled: true`:

```
http://localhost:8080
```

(From the drones over the mesh: `http://10.0.0.100:8080`.)

### Features

- **Force-directed graph** — interactive D3.js visualization of mesh topology
- **Link quality** — color-coded: green (strong), orange (medium), red (weak)
- **Node list** — all discovered mesh nodes with TQ metrics
- **Neighbor list** — direct neighbors and connection quality
- **Network stats** — node count, neighbor count
- **GPS panel** — positions shared through alfred
- **Auto-refresh** — updates every 3 seconds
- **Zoom/pan** — mouse wheel to zoom, drag to pan
- **Drag nodes** — drag individual nodes to reposition

### API Endpoints

The dashboard is served by `meshd` and exposes a REST API:

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard HTML page |
| `GET /api/mesh/status` | Overall mesh status (node count, bat0 state, etc.) |
| `GET /api/mesh/topology` | Full mesh topology from batadv-vis |
| `GET /api/mesh/originators` | All mesh nodes (batctl oj) |
| `GET /api/mesh/neighbors` | Direct neighbors (batctl nj) |
| `GET /api/mesh/interfaces` | Batman-adv interfaces (batctl if) |
| `GET /api/mesh/gateways` | Available gateways (batctl gwj) |
| `GET /api/mesh/gps` | GPS positions published via alfred (type 128) |
| `GET /api/mesh/nodes` | Fleet registry (alfred type 129) |
| `GET /api/health` | daemon health + lifecycle state |

## Connecting QGroundControl

### UDP Connection

1. Open QGroundControl
2. Application Settings -> Comm Links
3. Add new connection:
   - Type: **UDP**
   - Port: **14550**
4. Connect — telemetry flows via batman-adv mesh

### MAVLink Forwarding

On the drone, enable the meshd MAVLink forwarder in `/opt/mesh/config/mesh.yaml`:

```yaml
telemetry:
  mavlink:
    enabled: true
    fc_serial: /dev/ttyACM0
    fc_baud: 921600
    gcs_ip: 10.0.0.100
    gcs_port: 14550
```

Restart `meshd` after changing config. See the
[full guide](../BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md#7-mavlink-integration)
for details.

## Connecting Mission Planner

1. Open Mission Planner
2. Select **UDP** port **14550**
3. Click Connect
4. Telemetry flows via batman-adv mesh

## GPS without a Receiver

Ground stations without a GPS receiver can still publish a fixed position:

```yaml
telemetry:
  gps:
    enabled: true
    fixed_location: "48.858222,2.2945,358"
```

## Systemd Service

The ground station uses the same unit as every node:

```bash
sudo systemctl status meshd
sudo systemctl restart meshd
sudo systemctl stop meshd
```

## Stopping the Ground Station

```bash
sudo systemctl stop meshd
```

`meshd` tears down the data plane on shutdown: it stops alfred/batadv-vis,
removes the bat0 interface, and restores the WiFi adapter.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Dashboard not loading | Check `dashboard.enabled: true` and `systemctl status meshd`; confirm Flask is installed (`install.sh --with-dashboard`) |
| No nodes in dashboard | Verify mesh on drones, wait 10-30 seconds |
| Cannot connect QGC | Check UDP port 14550, verify bat0 is up (`meshctl status`) |
| WiFi not connecting | Run `sudo rfkill unblock wifi` |
