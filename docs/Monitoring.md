# Monitoring

Checking mesh network health and status with `meshd`, `meshctl`, and `batctl`.

> [Home](Home.md) > Monitoring

## meshctl status

The primary operator view. Run on any node:

```bash
meshctl status
```

Sample output:

```
Node            : drone-01 (drone)
IP (bat0)       : 10.0.0.3
State           : up
Radios          :
  - radioA: wlan0 [mesh] joined
Health          : bat0_up=True originators=3
```

Fields included in the JSON returned by the control socket:

| Field | Description |
|-------|-------------|
| `node` | node id, role, IP, netmask, mesh id |
| `lifecycle` | current state (`down`, `configuring`, `up`, `degraded`, …) |
| `radios` | per-radio mode, interface, joined/error, txpower quirk |
| `config_hash` | SHA of the active config |
| `health` | last health tick (`bat0_up`, originator count) |
| `running` | daemon liveness |
| `services` | per-service status (alfred, telemetry, video, dashboard) |

## meshctl fleet + remote

```bash
meshctl nodes                # all nodes in the alfred registry
meshctl -d 10.0.0.100 status # remote node status over mesh JSON-RPC
meshctl ping                 # local daemon liveness
```

Remote management requires `management.token` to be set and identical on all
nodes (generate with `meshctl token`).

## Dashboard

The dashboard (`dashboard.enabled: true`) exposes JSON endpoints you can query
directly from any browser or script:

| Endpoint | Description |
|----------|-------------|
| `/api/mesh/status` | Aggregated node/neighbor/gateway counts |
| `/api/mesh/topology` | batadv-vis JSON topology |
| `/api/mesh/originators` | batctl originators (JSON) |
| `/api/mesh/neighbors` | batctl neighbors (JSON) |
| `/api/mesh/interfaces` | bat0 member interfaces |
| `/api/mesh/gateways` | batctl gateways (JSON) |
| `/api/mesh/gps` | Positions published via alfred (type 128) |
| `/api/mesh/nodes` | Fleet registry (alfred type 129) |
| `/api/health` | daemon health + lifecycle state |

```bash
curl -s http://localhost:8080/api/mesh/status | python3 -m json.tool
```

## batctl Commands

`batctl` provides direct access to batman-adv internals.

### Core Commands

| Command | Description |
|---------|-------------|
| `batctl o` | Show originators (all mesh nodes) |
| `batctl n` | Show direct neighbors |
| `batctl if` | Show interfaces added to batman-adv |
| `batctl gwl` | Show available gateways |
| `batctl tg` | Show global translation table |
| `batctl tl` | Show local translation table |

### JSON Output

Append `j` to any command for JSON output:

| Command | Description |
|---------|-------------|
| `batctl oj` | Originators in JSON |
| `batctl nj` | Neighbors in JSON |
| `batctl gwj` | Gateways in JSON |
| `batctl tgj` | Translation table in JSON |

### Diagnostic Commands

| Command | Description |
|---------|-------------|
| `batctl tp <MAC>` | Test throughput to a specific node |
| `batctl traceroute <IP>` | Trace route through the mesh |
| `batctl event` | Monitor batman-adv events in real-time |

### Reading TQ Values

TQ (Transmission Quality) ranges from 0-255:

| TQ Range | Quality | Meaning |
|----------|---------|---------|
| 200-255 | Excellent | Strong signal, direct neighbor |
| 128-199 | Good | Reliable connection |
| 64-127 | Fair | Multi-hop or weak signal |
| 0-63 | Poor | Unstable, may drop |

**Percentage:** `TQ / 255 * 100`

## System Logs

### Daemon logs

```bash
sudo journalctl -u meshd -f              # Live follow
sudo journalctl -u meshd --since today   # Today's logs
sudo journalctl -u meshd | grep -i error # Errors only
```

### Batman-Adv Kernel Messages

```bash
dmesg | grep batman-adv
```

### Service logs

Each supervised service (alfred, video, telemetry) logs under its own name;
watch them with:

```bash
sudo journalctl -u meshd -f | grep -E "alfred|video|telemetry|gpsd"
```

## Health Tick

While running, `meshd` logs a health summary every 10 seconds:

```
health: bat0_up=True originators=3
```

The latest value is exposed via `meshctl status` (the `health` field) and the
dashboard `/api/health` endpoint.

## Systemd Service Status

```bash
sudo systemctl status meshd
sudo systemctl restart meshd
sudo systemctl stop meshd
```

## Script Output Example

```
Node            : drone-01 (drone)
IP (bat0)       : 10.0.0.3
State           : up
Radios          :
  - radioA: wlan0 [mesh] joined
Health          : bat0_up=True originators=3
```

**See also:** [Ground Station](Ground-Station.md) · [Troubleshooting](Troubleshooting.md) · [Configuration](Configuration.md)