# Video Streaming

Stream camera video over the batman-adv mesh network with the meshd GStreamer pipeline.

> [Home](Home.md) > Video Streaming

## Overview

`meshd` builds and supervises the `gst-launch-1.0` pipeline for you. Video is
encoded as H.264 and sent over UDP through the mesh; the ground station
receives and decodes the stream. `video.mode: sender` runs the encode/send
pipeline, `video.mode: receiver` runs the receive/display pipeline.

```
Camera -> [meshd video.mode=sender] H.264 -> UDP -> Mesh -> [meshd video.mode=receiver] -> Display
```

**Bandwidth requirements:**

| Quality | Resolution | FPS | Bitrate |
|---------|-----------|-----|---------|
| Low | 640x480 | 30 | ~2 Mbps |
| Medium | 1280x720 | 30 | ~4-8 Mbps |
| High | 1920x1080 | 30 | ~8-15 Mbps |

## Quick Start

### Sender (on the drone)

Edit `/opt/mesh/config/mesh.yaml`:

```yaml
video:
  mode: sender
  source_device: /dev/video0   # or libcamera / nvidia / a file / test
  bitrate_kbps: 4000
  dest_ip: 10.0.0.100
  dest_port: 5000
```

```bash
sudo systemctl restart meshd
meshctl status                  # radios/video service listed under services
```

### Receiver (on the ground station)

```yaml
video:
  mode: receiver
  dest_port: 5000
```

```bash
sudo systemctl restart meshd
```

`meshd` supervises the pipeline: if it crashes it restarts (up to 5 times with
a 5s backoff before giving up — visible in `meshctl status`).

## Source Selection (`video.source_device`)

| Value | Source |
|-------|--------|
| `null` (auto) | First existing `/dev/video0..4`, else a test pattern |
| `/dev/video0` | USB/HDMI camera via `v4l2src` |
| `libcamera` | Raspberry Pi camera via `libcamerasrc` |
| `nvidia` | Jetson `nvarguscamerasrc` + `nvv4l2h264enc` hardware encode |
| `test` | `videotestsrc` test pattern (debugging) |
| path to a file | Replay an H.264 media file (legacy demo behaviour, no transcode) |

## Transport (`video.transport`)

| Value | Description |
|-------|-------------|
| `unicast` | Sends to `dest_ip:dest_port` |
| `multicast` | Sends to `multicast_group:dest_port` (239.0.0.0/8) |

In `multicast` mode the receiver listens on the group:

```yaml
video:
  mode: receiver
  transport: multicast
  multicast_group: 239.255.77.77
  dest_port: 5000
```

## FEC (`video.fec`)

`fec: true` (default) inserts the RTP ULP FEC elements (`rtpulpfecenc` on the
sender, `rtpulpfecdec` on the receiver). FEC packets share the RTP session and
improve resilience over lossy mesh links:

| Field | Default | Notes |
|-------|---------|-------|
| `fec` | `true` | Add ULP FEC elements |
| `adaptive` | `true` | RTCP-driven adaptive bitrate (config metadata) |

## Generated Pipelines

For reference, meshd builds these `gst-launch-1.0` pipelines.

### Sender (USB camera, unicast, no FEC)

```
gst-launch-1.0 -e v4l2src device=/dev/video0
  ! video/x-raw,width=1280,height=720,framerate=30/1
  ! videoconvert ! x264enc tune=zerolatency bitrate=4000 speed-preset=superfast
  ! rtph264pay config-interval=1 pt=96
  ! udpsink sync=false async=false host=10.0.0.100 port=5000
```

### Receiver (unicast, no FEC)

```
gst-launch-1.0 -e udpsrc port=5000 caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000"
  ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert
  ! autovideosink sync=false
```

With `fec: true`, meshd inserts `! rtpulpfecenc ssrc=3000000001` (sender) and
`! rtpjitterbuffer ! rtpulpfecdec ignore-out-of-order=true` (receiver).

## Receiving in Other Tools

### QGroundControl

1. Application Settings -> General -> Video Settings
2. Source: UDP h.264 Video Stream
3. UDP Port: 5000

### VLC Media Player

1. Media -> Open Network Stream
2. Enter: `udp://@:5000`
3. Click Play

### FFplay

```bash
ffplay udp://@:5000 -protocol_whitelist file,udp,rtp
```

## Quality Profiles

| Profile | Resolution | Bitrate | Encoder Options |
|---------|-----------|---------|-----------------|
| Low | 640x480 | 2000 kbps | `tune=zerolatency speed-preset=superfast` |
| Medium | 1280x720 | 4000 kbps | `tune=zerolatency speed-preset=superfast` |
| High | 1920x1080 | 8000 kbps | `tune=zerolatency speed-preset=fast` |

Set resolution via `video.caps` and bitrate via `video.bitrate_kbps`:

```yaml
video:
  mode: sender
  caps: "video/x-raw,width=1920,height=1080,framerate=30/1"
  bitrate_kbps: 8000
```

**Tip:** For real-time drone video, use "low" quality to minimize latency. Use
"medium" or "high" only if mesh throughput supports it.

**See also:** [Configuration](Configuration.md) · [Monitoring](Monitoring.md) · [Troubleshooting](Troubleshooting.md)