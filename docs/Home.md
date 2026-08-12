# Batman-Adv Drone Mesh Network — Wiki

Welcome to the documentation for the batman-adv drone mesh network system.

This project enables true peer-to-peer WiFi mesh networking for drone swarms using the batman-adv Linux kernel module. Every drone is an identical peer with no hierarchy — the mesh self-heals and reroutes automatically.

## Quick Links

- **[Getting Started](Getting-Started.md)** — first-time setup walkthrough
- **[Script Reference](Script-Reference.md)** — documentation for all scripts
- **[Configuration](Configuration.md)** — config.sh parameter reference
- **[Troubleshooting](Troubleshooting.md)** — common issues and debugging

## Documentation Index

### Setup & Configuration
| Page | Description |
|------|-------------|
| [Getting Started](Getting-Started.md) | Step-by-step first-time setup for drones and ground station |
| [Configuration](Configuration.md) | Full reference for config.sh parameters |
| [Ad-Hoc Mode](Ad-Hoc-Mode.md) | Using IBSS mode when 802.11s is not supported |
| [Ground Station](Ground-Station.md) | Ground station setup with web dashboard |
| [Jetson Build](Jetson-Build.md) | Building batman-adv from source for Jetson Tegra |

### Usage & Monitoring
| Page | Description |
|------|-------------|
| [Video Streaming](Video-Streaming.md) | GStreamer video sender/receiver configuration |
| [Monitoring](Monitoring.md) | mesh_status.sh, batctl commands, and JSON output |
| [Script Reference](Script-Reference.md) | Detailed documentation for every script |

### Reference
| Page | Description |
|------|-------------|
| [Architecture](Architecture.md) | batman-adv protocol, OGM propagation, multi-hop routing |
| [Troubleshooting](Troubleshooting.md) | Common issues, debugging, and reset procedures |

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
- Python 3 + Flask (for dashboard)
- GStreamer 1.x (for video streaming)
