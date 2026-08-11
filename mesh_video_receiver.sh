#!/bin/bash
# =============================================================================
# GStreamer Video Receiver — Mesh Demo
# =============================================================================
# Receives H.264 video over UDP from the batman-adv mesh and displays it.
# Usage: ./mesh_video_receiver.sh [PORT]
# =============================================================================

PORT="${1:-5000}"

echo "=========================================="
echo " GStreamer Mesh Video Receiver"
echo "=========================================="
echo "  Listening:  0.0.0.0:${PORT}"
echo "  Display:    autovideosink"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop."
echo ""

gst-launch-1.0 -e \
    udpsrc port="${PORT}" \
        caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000" \
    ! rtph264depay \
    ! h264parse \
    ! avdec_h264 \
    ! videoconvert \
    ! autovideosink sync=false

echo ""
echo "Receiver stopped."
