# Script Reference

Detailed documentation for every script in the project.

> [Home](Home.md) > Script Reference

## config.sh

Central configuration file. Edit this on each drone.

```bash
# Source this in other scripts
source config.sh
```

**Sections:**
- **Drone Identity** — `DRONE_IP`, `PHYS_IFACE`, `MESH_IFACE`
- **Mesh Network** — `MESH_ID`, `MESH_BSSID`, `MESH_CHANNEL`, `MESH_BAND`
- **Batman-Adv** — `BATMAN_ROUTING`, `GATEWAY_MODE`, `GW_DOWNLOAD`, `GW_UPLOAD`
- **Network** — `NETMASK`, `BROADCAST`, `DNS_SERVER`
- **Advanced** — `WIFI_DRIVER_OPTIONS`, `MESH_MAC`, `BATMAN_PARAMS`
- **Logging** — `DEBUG_LOG`, `LOG_LEVEL`

See [Configuration](Configuration.md) for the full parameter reference.

## install_packages.sh

Installs all required system packages and kernel modules.

```bash
sudo ./install_packages.sh
```

**What it does:**
1. Detects OS (Debian/Ubuntu, Fedora/RHEL, Arch)
2. Updates package lists
3. Installs batctl, alfred, iw, GStreamer, gpsd, pymavlink
4. Loads batman_adv, cfg80211, mac80211 kernel modules
5. Enables modules at boot via `/etc/modules-load.d/`
6. Checks for batman-adv kernel support
7. Checks for mesh point WiFi support

**Requires root.**

## install.sh

Installs mesh scripts to `/opt/mesh` and sets up systemd service.

```bash
sudo ./install.sh
```

**What it does:**
1. Copies scripts to `/opt/mesh/`
2. Makes scripts executable
3. Installs `batman-mesh.service` to `/etc/systemd/system/`
4. Enables service at boot

**After running:** configure with `sudo nano /opt/mesh/config.sh` then `sudo /opt/mesh/setup_mesh.sh`

## setup_mesh.sh

Configures batman-adv mesh using **802.11s mesh point mode**.

```bash
sudo ./setup_mesh.sh
```

**What it does:**
1. Loads config.sh
2. Auto-detects WiFi interface (if not set)
3. Stops conflicting services (NetworkManager, hostapd, wpa_supplicant)
4. Configures WiFi channel
5. Creates batman-adv interface (bat0)
6. Joins mesh network with SAE authentication
7. Assigns IP address
8. Configures gateway (if enabled)
9. Enables IP forwarding
10. Configures firewall rules
11. Starts alfred for GPS distribution
12. Verifies the setup

**Requires root.**

## setup_adhoc.sh

Configures batman-adv mesh using **Ad-hoc (IBSS) mode**. Auto-detects if mesh point mode is available and falls back to ad-hoc if needed.

```bash
sudo ./setup_adhoc.sh
```

**What it does:**
1. Loads config.sh (requires `MESH_BSSID` for fixed BSSID)
2. Auto-detects WiFi interface
3. Stops conflicting services
4. Checks adapter health (txpower)
5. Sets up IBSS mode with fixed BSSID
6. Creates batman-adv interface (bat0)
7. Assigns IP address
8. Enables IP forwarding and firewall
9. Verifies the setup

**Key difference from setup_mesh.sh:** Uses ad-hoc mode instead of 802.11s. More compatible but slightly lower performance.

**Requires root.**

## setup_ground_station.sh

Complete ground station setup — installs packages, configures mesh, and starts web dashboard.

```bash
sudo ./setup_ground_station.sh
```

**What it does:**
1. Detects WiFi adapter
2. Installs all packages (including Flask for dashboard)
3. Stops conflicting services
4. Loads kernel modules
5. Sets up IBSS (ad-hoc) mode
6. Configures batman-adv
7. Assigns IP `10.0.0.100`
8. Starts alfred and batadv-vis
9. Creates systemd services for mesh and dashboard
10. Installs dashboard to `/opt/mesh/mesh_dashboard/`

**Requires root.**

## start_mesh.sh

Starts the mesh network. Called by the systemd service or run manually.

```bash
sudo ./start_mesh.sh
```

**What it does:**
1. Loads config.sh
2. Unblocks WiFi rfkill
3. Disables NetworkManager on mesh interface
4. Loads kernel modules
5. Runs `setup_mesh.sh`
6. Waits for mesh to stabilize
7. Shows mesh status

## stop_mesh.sh

Stops the mesh network (802.11s mode).

```bash
sudo ./stop_mesh.sh
```

**What it does:**
1. Stops alfred
2. Removes bat0 interface
3. Takes down physical interface
4. Leaves mesh network
5. Disables IP forwarding
6. Removes iptables rules

## stop_adhoc.sh

Stops the mesh network (Ad-hoc mode) and restores WiFi to managed mode.

```bash
sudo ./stop_adhoc.sh
```

**What it does:**
1. Stops dashboard service
2. Stops alfred and batadv-vis
3. Removes bat0 interface
4. Restores WiFi to managed mode
5. Re-enables NetworkManager
6. Disables IP forwarding
7. Removes iptables rules
8. Unloads batman_adv module

**Key difference from stop_mesh.sh:** Restores WiFi to managed mode so NetworkManager can use it again.

## stop_gcs_mesh.sh

Stops the ground station mesh network.

```bash
sudo ./stop_gcs_mesh.sh
```

Same as `stop_adhoc.sh` but hardcoded for the ground station interface.

## mesh_status.sh

Displays the current state of the mesh network.

```bash
sudo ./mesh_status.sh
```

**Output includes:**
- batman_adv module status
- Interface status (physical + bat0)
- Mesh neighbors (batctl n)
- Routing table / originators (batctl o)
- Gateway status
- Translation tables (local + global)
- Network statistics (RX/TX bytes)
- Connectivity test (ping common IPs)

**Options:**
- `-j` / `--json` — output status in JSON format
- `-h` / `--help` — show help

## mesh_video_sender.sh

Streams a video file over UDP via the batman-adv mesh.

```bash
./mesh_video_sender.sh [DEST_IP] [PORT] [VIDEO_FILE]
```

**Defaults:**
- `DEST_IP`: `10.0.0.100` (ground station)
- `PORT`: `5000`
- `VIDEO_FILE`: `/home/pi/sample_video.mp4`

Loops the video continuously. Press Ctrl+C to stop.

## mesh_video_receiver.sh

Receives H.264 video over UDP and displays it.

```bash
./mesh_video_receiver.sh [PORT]
```

**Defaults:**
- `PORT`: `5000`

Uses GStreamer with `autovideosink` for display.

## build_batman_adv.sh

Builds the batman_adv kernel module from source for Jetson Tegra kernels.

```bash
sudo ./build_batman_adv.sh
```

**What it does:**
1. Verifies kernel source exists
2. Enables batman_adv in kernel config
3. Builds the module
4. Installs to `/lib/modules/`
5. Updates module dependencies
6. Tests module load

**Requires root and kernel headers.** See [Jetson Build](Jetson-Build.md) for details.

## uninstall.sh

Completely removes mesh configuration and restores system defaults.

```bash
sudo ./uninstall.sh
```

**What it removes:**
- systemd service (`batman-mesh.service`)
- `/opt/mesh/` installation directory
- Kernel module loading config
- IP forwarding settings from `/etc/sysctl.conf`
- Firewall rules (iptables, UFW, firewalld)
- Mesh log file (`/var/log/mesh.log`)

**What it does NOT remove:**
- Installed packages (batctl, alfred, etc.)
- WiFi adapter drivers

**Requires root.** Prompts for confirmation before proceeding.
