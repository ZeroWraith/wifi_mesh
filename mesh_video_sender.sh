#!/bin/bash
# =============================================================================
# GStreamer Video Sender — Mesh Demo
# =============================================================================
# Streams a video file over UDP via the batman-adv mesh.
# Usage: ./mesh_video_sender.sh [DEST_IP] [PORT] [VIDEO_FILE]
# =============================================================================

DEST_IP="${1:-10.0.0.100}"
PORT="${2:-5000}"
VIDEO_FILE="${3:-/home/pi/sample_video.mp4}"

if [ ! -f "$VIDEO_FILE" ]; then
    echo "Error: Video file not found: $VIDEO_FILE"
    exit 1
fi

echo "=========================================="
echo " GStreamer Mesh Video Sender"
echo "=========================================="
echo "  Destination: ${DEST_IP}:${PORT}"
echo "  Video file:  ${VIDEO_FILE}"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop."
echo ""

# Loop the video continuously
while true; do
    gst-launch-1.0 -e \
        filesrc location="${VIDEO_FILE}" \
        ! qtdemux \
        ! h264parse \
        ! rtph264pay config-interval=1 pt=96 \
        ! udpsink host="${DEST_IP}" port="${PORT}" sync=false async=false

    echo "Replaying video..."
    sleep 1
done
