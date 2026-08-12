# Troubleshooting

Common issues and how to fix them.

> [Home](Home.md) > Troubleshooting

## Quick Diagnostics

Run these commands to quickly assess the situation:

```bash
# Module loaded?
lsmod | grep batman

# bat0 exists?
ip link show bat0

# Interfaces added?
batctl if

# Any neighbors?
batctl o

# Any errors in logs?
dmesg | grep batman-adv | tail -20
```

## Common Issues

### No Neighbors Visible

**Symptoms:** `batctl o` or `batctl n` shows nothing.

**Causes:**
- Mesh interface not added to batman-adv
- Other drone not running or not on same channel
- WiFi adapter not in correct mode

**Solutions:**
```bash
# Verify interface is added
batctl if
# Should show your WiFi interface

# If not added:
batctl if add wlp0s20f3

# Wait 10-30 seconds for OGM propagation
# Check on the other drone too
```

### No bat0 Interface

**Symptoms:** `ip link show bat0` fails.

**Cause:** batman-adv module not loaded or interface not created.

**Solutions:**
```bash
# Load module
sudo modprobe batman_adv

# Create interface
sudo batctl if add wlp0s20f3

# Bring up
sudo ip link set bat0 up
```

### High Latency / Slow Response

**Symptoms:** Ping works but is slow (100ms+).

**Cause:** OGM interval too high or too many hops.

**Solutions:**
```bash
# Reduce OGM interval (faster updates, more overhead)
sudo batctl orig_interval 500

# Check hop count
sudo batctl o  # Look at the metric/TQ values
```

### Flapping Routes

**Symptoms:** Nodes appear and disappear from `batctl o`.

**Cause:** Unstable wireless link, interference, or mobility.

**Solutions:**
```bash
# Increase hop penalty to prefer stable routes
sudo batctl hop_penalty 20

# Check signal strength
sudo iw dev wlp0s20f3 station dump

# Change to a less congested channel
# Edit config.sh: MESH_CHANNEL=11
```

### Gateway Not Selected

**Symptoms:** `batctl gw` shows "No gateways".

**Cause:** Gateway mode not configured on any node.

**Solutions:**
```bash
# On the drone with internet access:
sudo batctl gw server 100/100

# On drones that want internet:
sudo batctl gw client
```

### Packet Loss

**Symptoms:** Ping fails or shows high packet loss.

**Causes:** Interference, distance, or channel mismatch.

**Solutions:**
```bash
# Check signal strength
sudo iw dev wlp0s20f3 station dump | grep signal

# Change channel (edit config.sh)
# Try channels 1, 6, or 11 for 2.4GHz

# Check for interference
sudo iw dev wlp0s20f3 scan | grep freq
```

### Video Stuttering

**Symptoms:** Video stream is choppy or drops frames.

**Cause:** Insufficient mesh bandwidth.

**Solutions:**
- Reduce video quality (lower resolution/bitrate)
- Check mesh throughput: `sudo batctl tp <MAC>`
- Reduce number of hops (move drones closer)
- Use 5GHz channel for more bandwidth

### MAVLink Timeout

**Symptoms:** QGroundControl shows "No Heartbeat".

**Cause:** Flight controller not connected or wrong baud rate.

**Solutions:**
```bash
# Check serial connection
ls /dev/ttyAMA* /dev/ttyACM*

# Check baud rate (should match Pixhawk SERIAL2_BAUD)
# Default: 921600

# Test with pymavlink
python3 -c "from pymavlink import mavutil; m = mavutil.mavlink_connection('/dev/ttyAMA0', baud=921600); m.wait_heartbeat(); print('Connected')"
```

### WiFi Interface Not Found

**Symptoms:** Scripts report "No WiFi interface found".

**Solutions:**
```bash
# List all interfaces
iw dev

# Check USB adapters
lsusb | grep -i wifi

# Check if driver is loaded
lsmod | grep -i rtl  # For Realtek
lsmod | grep -i ath  # For Atheros
```

## Reset Procedures

### Reset Mesh (Keep System Running)

```bash
# Stop everything
sudo ./stop_adhoc.sh

# Wait 5 seconds, then restart
sudo ./setup_adhoc.sh
```

### Full Reset

```bash
# Stop services
sudo systemctl stop batman-mesh
sudo systemctl stop mesh-dashboard

# Teardown mesh
sudo ./stop_adhoc.sh

# Reload kernel module
sudo rmmod batman_adv
sudo modprobe batman_adv

# Reconfigure
sudo ./setup_adhoc.sh

# Restart services
sudo systemctl start batman-mesh
sudo systemctl start mesh-dashboard
```

### Nuclear Option

```bash
# Remove everything
sudo ./uninstall.sh
sudo reboot

# Start fresh
sudo ./install_packages.sh
sudo ./setup_adhoc.sh
```

## Getting Help

```bash
# Check script help
./setup_adhoc.sh --help
./mesh_status.sh --help

# View full guide
cat BATMAN_ADV_DRONE_MESH_COMPLETE_GUIDE.md

# Check batman-adv kernel documentation
modinfo batman_adv
```
