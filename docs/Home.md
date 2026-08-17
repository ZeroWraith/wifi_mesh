# Batman-Adv Drone Mesh Network — Wiki

Welcome to the documentation for the batman-adv drone mesh network system.

This project enables true peer-to-peer WiFi mesh networking for drone swarms using the batman-adv Linux kernel module, controlled by the `meshd` control-plane daemon. Every node runs identical configuration — no hierarchy, no central controller — and the mesh self-heals and reroutes automatically.

## Quick Links

- **[Getting Started](Getting-Started.md)** — first-time setup walkthrough
- **[Configuration](Configuration.md)** — `mesh.yaml` parameter reference
- **[Monitoring](Monitoring.md)** — `meshctl status`, dashboard, batctl commands
- **[Troubleshooting](Troubleshooting.md)** — common issues and debugging

## Documentation Index

### Setup & Configuration
| Page | Description |
|------|-------------|
| [Getting Started](Getting-Started.md) | Step-by-step first-time setup for drones and ground station |
| [Configuration](Configuration.md) | Full reference for `mesh.yaml` parameters |
| [Ad-Hoc Mode](Ad-Hoc-Mode.md) | Using IBSS mode when 802.11s is not supported |
| [Ground Station](Ground-Station.md) | Ground station setup with web dashboard |
| [Jetson Build](Jetson-Build.md) | Building batman-adv from source for Jetson Tegra |

### Usage & Monitoring
| Page | Description |
|------|-------------|
| [Video Streaming](Video-Streaming.md) | GStreamer video pipeline configuration via `meshd` |
| [Monitoring](Monitoring.md) | `meshctl`, dashboard, batctl commands, and JSON output |
| [Architecture](Architecture.md) | batman-adv protocol, OGM propagation, meshd lifecycle |

### Reference
| Page | Description |
|------|-------------|
| [Script Reference](Script-Reference.md) | `meshd` / `meshctl` CLI and install scripts |
| [Troubleshooting](Troubleshooting.md) | Common issues, debugging, and reset procedures |

## Components

| Component | Purpose |
|-----------|---------|
| `meshd` | Daemon: data plane, lifecycle, QoS, services, control socket |
| `meshctl` | Operator CLI: status, control, fleet discovery, remote RPC |
| `mesh.yaml` | Declarative per-node configuration |
| `deploy/units/meshd.service` | systemd unit |
| `mesh_dashboard/` | Dashboard front-end (served by meshd) |

## Supported Hardware

| Device | Role | Notes |
|--------|------|-------|
| Raspberry Pi 4B | Companion computer | Built-in WiFi + USB adapter |
| Raspberry Pi 5 | Companion computer | Built-in WiFi + USB adapter |
| Jetson Nano | Vision/AI companion | Requires USB WiFi adapter |
| Jetson Orin Nano | Advanced AI companion | Requires USB WiFi adapter |
| Any x86 Linux PC | Ground station | Requires USB WiFi adapter |

## System Requirements

- Linux kernel with batman-adv support (or ability to build from source)
- WiFi adapter supporting Ad-hoc (IBSS) mode
- Python 3.10+
- GStreamer 1.x (for video streaming)
- Optional: gpsd / alfred-gpsd (GPS distribution), pymavlink (MAVLink), Flask (dashboard)