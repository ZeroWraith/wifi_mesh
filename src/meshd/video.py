"""Video service: supervised GStreamer sender/receiver pipelines.

Replaces the standalone ``mesh_video_sender.sh`` / ``mesh_video_receiver.sh``
scripts: the daemon builds the appropriate ``gst-launch-1.0`` pipeline from
``video:`` in mesh.yaml and supervises it via :class:`SupervisedProc`, so a
crashed encoder/decoder restarts automatically.

Source selection (``video.source_device``):
  * ``null``         — auto-detect: first existing of /dev/video0..4, else test
  * ``/dev/videoX``  — USB/HDMI ``v4l2src``
  * ``libcamera``    — Raspberry Pi ``libcamerasrc``
  * ``nvidia``       — ``nvarguscamerasrc`` + hardware ``nvv4l2h264enc``
  * existing file    — replay H.264 media file (legacy demo behaviour)
  * ``test``         — ``videotestsrc`` pattern (debugging)
"""

from __future__ import annotations

import os
import shutil

from meshd.config import VideoConfig
from meshd.context import DaemonContext
from meshd.logs import get_logger
from meshd.services import Service, SupervisedProc

log = get_logger("video")

CAMERA_CANDIDATES = (
    "/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3", "/dev/video4",
)


def detect_camera() -> str | None:
    for dev in CAMERA_CANDIDATES:
        if os.path.exists(dev):
            return dev
    return None


def _caps_args(cfg: VideoConfig) -> list[str]:
    """['!', 'video/x-raw,width=1280,height=720,framerate=30/1']"""
    return ["!", cfg.caps]


def _is_file(cfg: VideoConfig) -> bool:
    return bool(cfg.source_device and os.path.isfile(cfg.source_device))


def _is_nvidia(cfg: VideoConfig) -> bool:
    return cfg.source_device == "nvidia"


def _is_libcamera(cfg: VideoConfig) -> bool:
    return cfg.source_device == "libcamera"


def build_sender_pipeline(cfg: VideoConfig) -> list[str]:
    """gst-launch-1.0 argv that captures, encodes, and streams H.264 RTP.

    Pipeline shape::

        <src> [caps] [videoconvert] [encoder] ! rtph264pay ... ! udpsink

    With ``video.fec`` the ``rtpulpfecenc`` element is inserted between the
    payloader and the sink; ULP FEC packets share the RTP session and the
    receiver's ``rtpulpfecdec`` strips them.
    """
    argv: list[str] = ["gst-launch-1.0", "-e"]

    if _is_file(cfg):
        # Pre-encoded H.264 file: no transcode, straight to RTP.
        argv += ["filesrc", f"location={cfg.source_device}",
                 "!", "qtdemux", "!", "h264parse"]
    else:
        src = _source_element(cfg)
        if src == "test":
            argv += ["videotestsrc"]
        elif src == "libcamera":
            argv += ["libcamerasrc", *_caps_args(cfg)]
        elif src == "nvidia":
            argv += ["nvarguscamerasrc"]
        else:
            device = src or detect_camera()
            if device is None:
                log.warning("no camera found; falling back to videotestsrc")
                argv += ["videotestsrc"]
            else:
                argv += ["v4l2src", f"device={device}"]

        argv += _caps_args(cfg)

        # Encoder.
        if _is_nvidia(cfg):
            argv += ["!", "nvv4l2h264enc", f"bitrate={cfg.bitrate_kbps}"]
        elif src == "test" or not src:
            # raw pattern -> x264
            argv += ["!", "videoconvert",
                     "!", "x264enc", "tune=zerolatency",
                     f"bitrate={cfg.bitrate_kbps}", "speed-preset=superfast"]
        else:
            # v4l2/libcamera already YUYV/NV12 -> convert then x264
            argv += ["!", "videoconvert",
                     "!", "x264enc", "tune=zerolatency",
                     f"bitrate={cfg.bitrate_kbps}", "speed-preset=superfast"]

    argv += ["!", "rtph264pay", "config-interval=1", "pt=96"]

    if cfg.fec:
        argv += ["!", "rtpulpfecenc", "ssrc=3000000001"]

    sink = _sink(cfg)
    argv += ["!", sink]
    return argv


def build_receiver_pipeline(cfg: VideoConfig) -> list[str]:
    """gst-launch-1.0 argv that receives H.264 RTP and displays it.

    Uses ``dest_port`` as the listen port (mesh is symmetric; the sender
    streams to its configured ``dest_ip:dest_port``).
    """
    caps = ("application/x-rtp,media=video,encoding-name=H264,"
            "payload=96,clock-rate=90000")
    if cfg.transport == "multicast":
        src = ["udpsrc", f"address={cfg.multicast_group}",
               f"port={cfg.dest_port}", "caps=" + caps]
    else:
        src = ["udpsrc", f"port={cfg.dest_port}", "caps=" + caps]

    argv: list[str] = ["gst-launch-1.0", "-e", *src]

    if cfg.fec:
        argv += ["!", "rtpjitterbuffer", "!", "rtpulpfecdec",
                 "ignore-out-of-order=true"]
    argv += ["!", "rtph264depay", "!", "h264parse", "!", "avdec_h264",
             "!", "videoconvert", "!", "autovideosink", "sync=false"]
    return argv


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _source_element(cfg: VideoConfig) -> str | None:
    src = cfg.source_device
    if src and src.startswith("/dev/"):
        return src
    return src if src in ("libcamera", "nvidia", "test") else None


def _sink(cfg: VideoConfig) -> str:
    if cfg.transport == "multicast":
        return (f"udpsink sync=false async=false auto-multicast=true "
                f"host={cfg.multicast_group} port={cfg.dest_port}")
    return (f"udpsink sync=false async=false "
            f"host={cfg.dest_ip} port={cfg.dest_port}")


class VideoService(Service):
    name = "video"

    def __init__(self, config: VideoConfig):
        self.cfg = config
        self.proc: SupervisedProc | None = None

    async def start(self, ctx: DaemonContext) -> None:
        if self.cfg.mode == "off":
            log.info("video disabled (video.mode=off)")
            return

        if shutil.which("gst-launch-1.0") is None:
            log.warning("video requested but gst-launch-1.0 is not installed")
            return

        if self.cfg.mode == "sender":
            argv = build_sender_pipeline(self.cfg)
        else:
            argv = build_receiver_pipeline(self.cfg)

        self.proc = SupervisedProc("video", argv, required=False)
        await self.proc.start()
        log.info("video pipeline started (%s): %s", self.cfg.mode, " ".join(argv))

    async def stop(self, ctx: DaemonContext) -> None:
        if self.proc:
            await self.proc.stop()
            self.proc = None

    def status(self) -> dict:
        proc = self.proc.status() if self.proc else {
            "running": False, "restarts": 0, "last_error": ""}
        return {
            "name": self.name,
            "mode": self.cfg.mode,
            "running": proc.get("running", False) and self.cfg.mode != "off",
            "restarts": proc.get("restarts", 0),
            "last_error": proc.get("last_error", ""),
        }

