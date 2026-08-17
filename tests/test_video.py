"""Tests for the video service (GStreamer pipeline construction)."""

from meshd.config import VideoConfig
from meshd.video import build_receiver_pipeline, build_sender_pipeline


def _simple_cfg(**kw) -> VideoConfig:
    defaults = dict(mode="sender", source_device=None,
                    caps="video/x-raw,width=1280,height=720,framerate=30/1",
                    bitrate_kbps=4000, transport="unicast", fec=False,
                    dest_ip="10.0.0.100", dest_port=5000, multicast_group="239.255.77.77")
    defaults.update(kw)
    cfg = VideoConfig(**defaults)
    cfg.validate()
    return cfg


def test_unicast_sender_v4l2():
    argv = build_sender_pipeline(_simple_cfg())
    text = " ".join(argv)
    assert argv[0] == "gst-launch-1.0"
    assert "v4l2src" in text
    assert "x264enc" in text
    assert "bitrate=4000" in text
    assert "rtph264pay" in text
    assert "host=10.0.0.100 port=5000" in text
    assert "udpsink" in text


def test_sender_multicast_uses_group():
    argv = build_sender_pipeline(_simple_cfg(transport="multicast"))
    text = " ".join(argv)
    assert "auto-multicast=true" in text
    assert "host=239.255.77.77" in text


def test_sender_fec_adds_ulpfec():
    argv = build_sender_pipeline(_simple_cfg(fec=True))
    text = " ".join(argv)
    assert "rtpulpfecenc" in text
    assert "rtph264pay" in text
    assert text.index("rtph264pay") < text.index("rtpulpfecenc")


def test_sender_nvidia_uses_hw_encoder():
    argv = build_sender_pipeline(_simple_cfg(source_device="nvidia"))
    text = " ".join(argv)
    assert "nvarguscamerasrc" in text
    assert "nvv4l2h264enc" in text
    assert "x264enc" not in text


def test_sender_file_replays_without_transcode():
    import os
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "clip.mp4")
    open(path, "w").close()
    argv = build_sender_pipeline(_simple_cfg(source_device=path))
    text = " ".join(argv)
    assert "filesrc" in text
    assert "qtdemux" in text
    assert "x264enc" not in text


def test_sender_test_pattern():
    argv = build_sender_pipeline(_simple_cfg(source_device="test"))
    text = " ".join(argv)
    assert "videotestsrc" in text


def test_unicast_receiver():
    argv = build_receiver_pipeline(_simple_cfg(mode="receiver"))
    text = " ".join(argv)
    assert argv[0] == "gst-launch-1.0"
    assert "udpsrc" in text
    assert "port=5000" in text
    assert "rtph264depay" in text
    assert "avdec_h264" in text
    assert "autovideosink" in text


def test_receiver_fec_adds_dec():
    argv = build_receiver_pipeline(_simple_cfg(mode="receiver", fec=True))
    text = " ".join(argv)
    assert "rtpulpfecdec" in text
    assert "rtpjitterbuffer" in text


def test_receiver_multicast_listens_on_group():
    argv = build_receiver_pipeline(
        _simple_cfg(mode="receiver", transport="multicast"))
    text = " ".join(argv)
    assert "address=239.255.77.77" in text
    assert "port=5000" in text

