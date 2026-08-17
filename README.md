# Batman-Adv Drone Mesh Network

![Platform](https://img.shields.io/badge/platform-Linux-lightgrey)
![Python](https://img.shields.io/badge/language-Python-blue)
![Batman-Adv](https://img.shields.io/badge/batman--adv-Layer%202%20mesh-blue)

True peer-to-peer WiFi mesh networking for drone swarms using batman-adv, controlled by a single `meshd` daemon on every node. Every drone is an identical peer — no hierarchy, no central controller, automatic self-healing.

## What is this?

A complete drone-mesh software stack. Each node runs one daemon (`meshd`) that owns the whole data plane and control plane:

- **Data plane** — radios, bat0 interface, routing settings, QoS
- **Control plane** — lifecycle, local operator socket, and a JSON-RPC management plane over the mesh
- **Services** — alfred, GPS distribution, MAVLink forwarding, video pipeline, web dashboard

## Features

- **Self-healing mesh** — automatic reroute within 3-5 seconds when nodes fail
- **True peer-to-peer** — every node runs identical configuration
- **Multi-hop routing** — traffic routes through intermediate drones transparently
- **Declarative config** — a single `mesh.yaml` per node, validated at startup
- **Lifecycle management** — every bring-up step is retried, supervised, and rolled back if the mesh fails
- **Video streaming** — supervised GStreamer H.264 pipeline (sender or receiver)
- **MAVLink integration** — forward flight-controller telemetry to the ground station
- **GPS distribution** — share GPS positions across the mesh via alfred
- **QoS** — strict-priority classes for command & control + video
- **Web dashboard** — Flask dashboard served by meshd, backed by live mesh data
- **Remote management** — `meshctl -d <ip>` JSON-RPC to any node over the mesh
- **Ad-hoc fallback** — works with adapters that don't support 802.11s

## Architecture

```
TRUE PEER MESH (No Hierarchy):

    +-----------+         +-----------+        +-----------+
    |  Drone 1  |<------->|  Drone 2  |<------>|  Drone 3  |
    | 10.0.0.1  |         | 10.0.0.2  |        | 10.0.0.3  |
    +-----+-----+         +-----+-----+        +-----+-----+
          |                     ^                    |
          +---------------------+--------------------+
                                |
                           +----+----+
                           |  Ground  |
                           | Station  |
                           |10.0.0.100|
                           +----+-----+
                                |
                          +-----+------+
                          |  Dashboard  |
                          |  (meshd:8080)|
                          +-------------+

Every node runs `meshd` and is reachable via multi-hop.
batman-adv handles routing; meshd handles everything else.
```

## Supported Hardware

| Device | CPU | Role |
|--------|-----|------|
| Raspberry Pi 4/5 | Quad ARM Cortex-A72/A76 | Companion computer |
| Jetson Nano/Orin | Quad ARM / 6-core Arm | Vision/AI companion |
| Any x86 Linux PC | Various | Ground station |

## Quick Start

```bash
# 1. Install dependencies (run once per node)
sudo ./install_packages.sh

# 2. Install meshd + systemd unit (creates /opt/mesh, venv, config)
sudo ./install.sh --with-all

# 3. Edit per-node configuration
sudo nano /opt/mesh/config/mesh.yaml    # set node.id, node.ip, management.token

# 4. Validate and start
sudo meshctl -c /opt/mesh/config/mesh.yaml validate
sudo systemctl start meshd

# 5. Inspect
meshctl status
```

The ground station additionally enables `dashboard: enabled: true` (default in
the shipped `config/mesh.yaml`) and opens **http://localhost:8080**.

## Repo layout

| Path | Purpose |
|------|---------|
| `src/meshd/` | The `meshd` daemon package |
| `tests/` | pytest suite (46 tests) |
| `config/mesh.yaml` | Example node configuration |
| `deploy/units/meshd.service` | systemd unit |
| `install.sh` | Install to `/opt/mesh` + enable systemd |
| `install_packages.sh` | OS packages (batctl, alfred, gpsd, GStreamer…) |
| `uninstall.sh` | Remove all mesh configuration |
| `docs/` | Wiki-style documentation |
| `BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md` | The fully-built reference guide |

## CLI

| Command | Purpose |
|---------|---------|
| `meshd` | Run the daemon (`-c` config, `--init`, `--dry-run`) |
| `meshctl status` | Local node status (radios, lifecycle, health) |
| `meshctl ping / stop / restart` | Local control |
| `meshctl nodes` | List fleet nodes from the alfred registry |
| `meshctl -d <ip> status` | Remote node status over mesh JSON-RPC |
| `meshctl token` | Generate a management token |

## Dashboard

Served by `meshd` when `dashboard.enabled` is true (Flask):

- **Force-directed graph** — interactive D3.js topology visualization
- **Link quality indicators** — strong/medium/weak with color coding
- **Node list** — discovered nodes with TQ metrics
- **Neighbor list** — direct neighbors and connection quality
- **GPS panel** — positions published through alfred
- **Auto-refresh** — updates every 3 seconds

Access at **http://<node-ip>:8080**.

## Documentation

- **[docs/](docs/)** — wiki-style documentation organized by topic
  - [Getting Started](docs/Getting-Started.md)
  - [Configuration](docs/Configuration.md) (`mesh.yaml` reference)
  - [Monitoring](docs/Monitoring.md)
  - [Video Streaming](docs/Video-Streaming.md)
  - [Ground Station](docs/Ground-Station.md)
  - [Architecture](docs/Architecture.md)
  - [Troubleshooting](docs/Troubleshooting.md)
- **[Full Implementation Guide](BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md)** — comprehensive reference covering protocol details, hardware setup, and advanced configuration

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test,dashboard,telemetry]"
.venv/bin/pytest          # run the test suite
.venv/bin/ruff check src  # lint
```

## Troubleshooting

```bash
# Check the daemon
meshctl status

# Check batman-adv neighbors
sudo batctl o    # originators
sudo batctl n    # neighbors

# Check kernel module
lsmod | grep batman

# View logs
sudo journalctl -u meshd -f
```

See [docs/Troubleshooting.md](docs/Troubleshooting.md) for detailed debugging.

## Uninstall

```bash
sudo ./uninstall.sh
```

Removes `meshd.service`, the legacy `batman-mesh.service`, `/opt/mesh`, kernel
config, firewall rules, and IP forwarding settings. Does not remove installed
packages.