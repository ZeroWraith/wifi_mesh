# CLI & Script Reference

Reference for `meshd`, `meshctl`, and the helper scripts in the repository.

> [Home](Home.md) > CLI & Script Reference

## meshd — the daemon

`meshd` is the control-plane daemon that owns the data plane (radios, bat0,
QoS), lifecycle, management plane, and supervised services.

```bash
meshd [options]

  -c, --config PATH   mesh.yaml location (default /opt/mesh/config/mesh.yaml)
  -v, --verbose       debug logging
  -f, --foreground    run in the foreground (log to stderr)
      --dry-run       validate config and exit
      --init          write a template mesh.yaml and exit
  -V, --version       show version
```

Run as a service:

```bash
sudo systemctl start meshd
sudo systemctl status meshd
```

## meshctl — operator CLI

Talking to the local daemon over its control socket, or to remote nodes over
the mesh management plane.

```bash
meshctl [options] COMMAND

Global options:
  -s, --socket PATH   local daemon control socket
  -c, --config PATH   mesh.yaml (for validate / remote commands)
  -d, --device IP     target remote mesh node for JSON-RPC
```

### Commands

| Command | Description |
|---------|-------------|
| `token` | Generate a management token |
| `init` | Write a template mesh.yaml |
| `validate` | Validate the local config (dry-run) |
| `ping` | Ping the local daemon |
| `status` | Show local daemon status |
| `stop` | Gracefully stop the local mesh |
| `restart` | Restart the local mesh |
| `start` | Start `meshd` via systemd |
| `nodes` | List fleet nodes from the alfred registry |

### Remote management

```bash
meshctl -d 10.0.0.100 status   # status of a remote node over the mesh
meshctl -d 10.0.0.100 ping
meshctl -d 10.0.0.100 restart
```

Requires `management.token` (identical on all nodes; override with the
`MESH_MGMT_TOKEN` env var).

### Examples

```bash
meshctl token                                   # -> a fresh management token
meshctl -c /opt/mesh/config/mesh.yaml validate
meshctl status
meshctl nodes                                   # fleet from alfred (type 129)
meshctl -d 10.0.0.100 status
```

## Install scripts

### install_packages.sh

Installs all required system packages and kernel modules.

```bash
sudo ./install_packages.sh
```

**What it does:**
1. Detects OS (Debian/Ubuntu, Fedora/RHEL, Arch)
2. Updates package lists
3. Installs batctl, alfred, batadv-vis, iw, GStreamer, gpsd, python3-venv
4. Installs `pymavlink` (into `/opt/mesh/.venv` when present)
5. Loads batman_adv, cfg80211, mac80211 kernel modules
6. Enables modules at boot via `/etc/modules-load.d/`
7. Checks for batman-adv kernel and mesh-point WiFi support

**Requires root.**

### install.sh

Installs meshd to `/opt/mesh` and enables the systemd unit.

```bash
sudo ./install.sh [--with-telemetry] [--with-dashboard] [--with-all]
```

**What it does:**
1. Runs `install_packages.sh`
2. Creates `/opt/mesh` layout and a virtualenv at `/opt/mesh/.venv`
3. Installs `meshd` (+ optional telemetry/dashboard extras)
4. Writes a default `mesh.yaml` (via `meshd --init`)
5. Installs and enables `deploy/units/meshd.service`

**After running:** edit `/opt/mesh/config/mesh.yaml` (set `node.id`,
`node.ip`, `management.token`) then `systemctl start meshd`.

### Uninstall

```bash
sudo ./uninstall.sh
```

Removes `meshd.service` and the legacy `batman-mesh.service`, `/opt/mesh`,
kernel module-load config, IP-forwarding settings, firewall rules, and the
mesh log. Does **not** remove installed packages.

## Legacy helper scripts

These manual scripts remain for reference / out-of-band use but are **no
longer required** — `meshd` replaces their functionality and supervises it as
a service.

| Script | Former purpose | meshd equivalent |
|--------|----------------|------------------|
| `config.sh` | Variable-based config | `mesh.yaml` |
| `setup_mesh.sh` | 802.11s mesh bring-up | data-plane lifecycle steps |
| `setup_adhoc.sh` | IBSS mesh bring-up | `radios[].mode: ibss` |
| `setup_ground_station.sh` | GCS with detached dashboard | `role: ground-station` + `dashboard.enabled` |
| `start_mesh.sh` / `stop_mesh.sh` | manual start/stop | `systemctl start/stop meshd` |
| `mesh_status.sh` | status snapshot | `meshctl status` |
| `mesh_video_sender.sh` / `mesh_video_receiver.sh` | manual GStreamer pipelines | `video.mode: sender/receiver` |
| `build_batman_adv.sh` | build module on Jetson | still used for Jetson kernels |

See [Jetson Build](Jetson-Build.md) for building batman-adv on Tegra kernels.

## docs layout

| Path | Purpose |
|------|---------|
| `deploy/units/meshd.service` | systemd unit (`meshd` daemon) |
| `config/mesh.yaml` | fully-commented example configuration |
| `mesh_dashboard/` | dashboard front-end template (bundled into meshd) |