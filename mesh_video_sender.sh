#!/bin/bash
# =============================================================================
# GStreamer Video Sender — Mesh Demo
# =============================================================================
# Streams a test pattern (or camera) over UDP via the batman-adv mesh.
# Usage: ./mesh_video_sender.sh [DEST_IP] [PORT] [WIDTH] [HEIGHT]
# =============================================================================

DEST_IP="${1:-10.0.0.100}"
PORT="${2:-5000}"
WIDTH="${3:-640}"
HEIGHT="${4:-480}"
FRAMERATE="${5:-30}"

echo "=========================================="
echo " GStreamer Mesh Video Sender"
echo "=========================================="
echo "  Destination: ${DEST_IP}:${PORT}"
echo "  Resolution:  ${WIDTH}x${HEIGHT}@${FRAMERATE}fps"
echo "  Source:      videotestsrc (test pattern)"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop."
echo ""

gst-launch-1.0 -e \
    videotestsrc is-live=true \
    ! "video/x-raw,width=${WIDTH},height=${HEIGHT},framerate=${FRAMERATE}/1" \
    ! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=${FRAMERATE} bitrate=500 \
    ! "video/x-h264,profile=baseline" \
    ! h264parse \
    ! rtph264pay config-interval=1 pt=96 \
    ! udpsink host="${DEST_IP}" port="${PORT}" sync=false async=false

echo ""
echo "Stream stopped."
