# Ad-Hoc (IBSS) Mode

Using batman-adv with ad-hoc wireless networking as an alternative to 802.11s mesh point mode.

> [Home](Home.md) > Ad-Hoc Mode

## When to Use Ad-Hoc Mode

Use ad-hoc mode when:
- Your WiFi adapter does **not** support 802.11s mesh point mode
- You need quick setup for testing/development
- Your hardware driver only supports IBSS

**Check if your adapter supports mesh point:**

```bash
iw phy | grep -A8 "interface modes"
```

If you see `mesh point` in the output, use standard 802.11s setup. If you only see `IBSS`, use ad-hoc mode.

## Comparison

| Feature | Mesh Point (802.11s) | Ad-Hoc (IBSS) |
|---------|---------------------|---------------|
| Batman-adv support | Yes | Yes |
| Performance | Better throughput | Slightly lower |
| Reliability | More robust | Adequate for testing |
| SAE authentication | Supported | Not available |
| Setup complexity | Higher (wpa_supplicant) | Lower (iwconfig) |

## Quick Setup

```bash
sudo ./setup_adhoc.sh
```

The script:
1. Auto-detects your WiFi interface
2. Checks for mesh point support
3. Configures ad-hoc mode with fixed BSSID
4. Creates bat0 and assigns IP
5. Verifies the setup

## Manual Setup

If you prefer to configure manually:

### Step 1: Set Interface to IBSS

```bash
sudo ip link set wlp0s20f3 down
sudo iw dev wlp0s20f3 set type ibss
sudo ip link set wlp0s20f3 up
```

### Step 2: Join IBSS Network

```bash
sudo iw dev wlp0s20f3 ibss join drone-mesh 2437 fixed-freq 02:12:34:56:78:9a
```

- `drone-mesh` — ESSID (must be same on all nodes)
- `2437` — frequency in MHz (channel 6 = 2437)
- `fixed-freq` — forces this frequency
- `02:12:34:56:78:9a` — BSSID (must be same on all nodes)

### Step 3: Configure Batman-Adv

```bash
sudo modprobe batman_adv
sudo batctl if add wlp0s20f3
sudo ip link set bat0 up
sudo batctl routing_algo BATMAN_IV
sudo ip addr add 10.0.0.3/24 dev bat0
```

### Step 4: Verify

```bash
sudo batctl o    # Wait 10-30 seconds for neighbors
ping 10.0.0.1   # Test connectivity
```

## Fixed BSSID

In ad-hoc mode, both nodes must join with the **same BSSID** to be in the same network. The default BSSID is:

```
02:12:34:56:78:9a
```

This is configured in `config.sh` as `MESH_BSSID`. Change it if you have multiple independent mesh networks in the same area.

**Why is this needed?** Without a fixed BSSID, each node might create its own IBSS network with a random BSSID, preventing them from communicating.

## Adapter Health Check

The `setup_adhoc.sh` script checks adapter txpower:

```bash
iw dev wlp0s20f3 info | grep txpower
```

**Known quirk:** Some Realtek adapters report `txpower = -100 dBm` in managed mode. This is normal and does not affect ad-hoc operation.

If `tx_dropped` increases rapidly after joining IBSS, the adapter may need a physical power-cycle (unplug/replug USB).

## Restoring Managed Mode

After stopping the mesh, WiFi is automatically restored to managed mode by `stop_adhoc.sh`. If you need to do this manually:

```bash
sudo ip link set wlp0s20f3 down
sudo iw dev wlp0s20f3 ibss leave
sudo iw dev wlp0s20f3 set type managed
sudo ip link set wlp0s20f3 up
sudo rfkill unblock wifi
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `iwconfig: command not found` | Install wireless-tools: `sudo apt install wireless-tools` |
| `Mode:Auto` after setting ad-hoc | Interface must be down before changing mode |
| No neighbors in `batctl o` | Wait 10-30 seconds for OGM propagation |
| `batman_adv: Unknown symbol` | Module not built for your kernel, rebuild from source |
| ESSID mismatch | All nodes must use the EXACT same ESSID |
| Channel mismatch | All nodes must be on the SAME channel |
| BSSID mismatch | All nodes must use the same `MESH_BSSID` |
