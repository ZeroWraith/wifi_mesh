# Video Streaming

Stream camera video over the batman-adv mesh network using GStreamer.

> [Home](Home.md) > Video Streaming

## Overview

Video is encoded as H.264 and sent over UDP through the mesh. The ground station receives and decodes the stream.

```
Camera -> GStreamer (H.264 encode) -> UDP -> Mesh -> GStreamer (decode) -> Display
```

**Bandwidth requirements:**

| Quality | Resolution | FPS | Bitrate |
|---------|-----------|-----|---------|
| Low | 640x480 | 30 | ~2 Mbps |
| Medium | 1280x720 | 30 | ~4-8 Mbps |
| High | 1920x1080 | 30 | ~8-15 Mbps |

## Quick Start

### Sender (on drone)

```bash
./mesh_video_sender.sh 10.0.0.100 5000 /path/to/video.mp4
```

### Receiver (on ground station)

```bash
./mesh_video_receiver.sh 5000
```

## Sender Details

`mesh_video_sender.sh` streams a video file in a loop:

```bash
./mesh_video_sender.sh [DEST_IP] [PORT] [VIDEO_FILE]

# Defaults:
#   DEST_IP=10.0.0.100
#   PORT=5000
#   VIDEO_FILE=/home/pi/sample_video.mp4
```

**GStreamer pipeline:**

```
filesrc -> qtdemux -> h264parse -> rtph264pay -> udpsink
```

Press Ctrl+C to stop. The script will replay the video in a loop.

## Receiver Details

`mesh_video_receiver.sh` receives and displays the H.264 stream:

```bash
./mesh_video_receiver.sh [PORT]

# Default: PORT=5000
```

**GStreamer pipeline:**

```
udpsrc -> rtph264depay -> h264parse -> avdec_h264 -> videoconvert -> autovideosink
```

## Camera Types

### Raspberry Pi Camera (libcamerasrc)

```bash
gst-launch-1.0 -v libcamerasrc \
    ! video/x-raw,width=640,height=480,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

### Jetson Camera (nvarguscamerasrc)

```bash
gst-launch-1.0 -v nvarguscamerasrc \
    ! video/x-raw,width=640,height=480,framerate=30/1 \
    ! videoconvert \
    ! nvv4l2h264enc bitrate=2000 \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

### USB Camera (v4l2src)

```bash
gst-launch-1.0 -v v4l2src device=/dev/video0 \
    ! video/x-raw,width=640,height=480,framerate=30/1 \
    ! videoconvert \
    ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast \
    ! rtph264pay config-interval=1 \
    ! udpsink host=10.0.0.100 port=5000
```

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

**Tip:** For real-time drone video, use "low" quality to minimize latency. Use "medium" or "high" only if mesh throughput supports it.
