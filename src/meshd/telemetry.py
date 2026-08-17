"""Telemetry services: GPS distribution + MAVLink forwarder.

* Hardware/ground-station GPS is published via ``alfred-gpsd`` (supervised
  child process).
* On a drone companion computer, the flight controller's position is bridged
  from MAVLink into an alfred data type (128) so any mesh node can query every
  other node's position.
* The MAVLink forwarder relays FC <-> GCS telemetry bidirectionally over the
  mesh (matching the demo guide's design, but as a supervised in-process
  thread rather than a detached script).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from typing import Optional

from meshd.config import TelemetryConfig
from meshd.logs import get_logger
from meshd.services import Service, SupervisedProc

log = get_logger("telemetry")

ALFRED_GPS_TYPE = "128"
GPS_POLL_INTERVAL = 1.0

GPS_DEVICE_CANDIDATES = (
    "/dev/ttyUSB0", "/dev/ttyAMA0", "/dev/ttyACM0", "/dev/ttyS0", "/dev/ttyTHS1",
)


def detect_gps_device() -> Optional[str]:
    for dev in GPS_DEVICE_CANDIDATES:
        if os.path.exists(dev):
            return dev
    return None


# ---------------------------------------------------------------------------
# MAVLink forwarder
# ---------------------------------------------------------------------------

class MavlinkForwarder(threading.Thread):
    def __init__(self, config: TelemetryConfig, gcs_ip: str):
        super().__init__(name="mavlink-forwarder", daemon=True)
        self.cfg = config.mavlink
        self._gcs_ip = gcs_ip
        self._stop = threading.Event()
        self.last_gps: Optional[dict] = None
        self.fc_connected = False
        self.last_error = ""
        self._udp: Optional[socket.socket] = None

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            from pymavlink import mavutil
        except ImportError:
            self.last_error = "pymavlink not installed (pip install meshd[telemetry])"
            log.warning(self.last_error)
            return

        try:
            fc = mavutil.mavlink_connection(self.cfg.fc_serial, baud=self.cfg.fc_baud)
            fc.wait_heartbeat(timeout=10)
            self.fc_connected = True
            log.info("connected to FC on %s (system=%s)",
                     self.cfg.fc_serial, fc.target_system)
            fc.mav.request_data_stream_send(
                fc.target_system, fc.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                self.cfg.stream_rate_hz, 1,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"FC connect failed: {exc}"
            log.error(self.last_error)
            return

        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp.bind(("0.0.0.0", self.cfg.local_port))
        self._udp.settimeout(0.1)

        while not self._stop.is_set():
            try:
                # FC -> GCS
                msg = fc.recv_msg()
                if msg is not None:
                    self._udp.sendto(msg.get_msgbuf(), (self._gcs_ip, self.cfg.gcs_port))
                    self._maybe_capture_gps(msg)
                # GCS -> FC
                try:
                    data, _ = self._udp.recvfrom(4096)
                    if data:
                        fc.write(data)
                except socket.timeout:
                    pass
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                log.warning("mavlink loop error: %s", exc)
                time.sleep(0.2)

        try:
            fc.close()
        except Exception:  # noqa: BLE001
            pass
        log.info("mavlink forwarder stopped")

    def _maybe_capture_gps(self, msg) -> None:
        try:
            lat = getattr(msg, "lat", None)
            lon = getattr(msg, "lon", None)
            alt = getattr(msg, "alt", None)
            if lat is None or lon is None:
                return
            self.last_gps = {
                "lat": lat / 1e7,
                "lon": lon / 1e7,
                "alt": alt,
                "ts": time.time(),
            }
        except Exception:  # noqa: BLE001
            pass

    def status(self) -> dict:
        return {
            "name": "mavlink",
            "running": self.is_alive(),
            "fc_connected": self.fc_connected,
            "last_error": self.last_error,
            "gps": self.last_gps is not None,
        }


# ---------------------------------------------------------------------------
# Alfred GPS publisher (bridges MAVLink GPS into alfred)
# ---------------------------------------------------------------------------

class GpsPublisher:
    """Publishes the MAVLink-captured GPS into alfred every ``interval``."""

    def __init__(self, forwarder: MavlinkForwarder, exec, node_id: str,
                 gps_type: str = ALFRED_GPS_TYPE, interval: float = GPS_POLL_INTERVAL):
        self.forwarder = forwarder
        self.exec = exec
        self.node_id = node_id
        self.gps_type = gps_type
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                gps = self.forwarder.last_gps
                if gps:
                    payload = {
                        "node": self.node_id,
                        "source": "mavlink",
                        "tpv": {
                            "lat": gps["lat"],
                            "lon": gps["lon"],
                            "alt": gps["alt"],
                        },
                    }
                    await self._publish(payload)
            except Exception as exc:  # noqa: BLE001
                log.warning("gps publish failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def _publish(self, payload: dict) -> None:
        data = json.dumps(payload)
        await self.exec.run_with_stdin(
            ["alfred", "-i", "bat0", "-s", self.gps_type], stdin=data, timeout=10,
        )


# ---------------------------------------------------------------------------
# Telemetry service (supervises GPS + MAVLink pieces)
# ---------------------------------------------------------------------------

class TelemetryService(Service):
    name = "telemetry"

    def __init__(self, config: TelemetryConfig, node_id: str):
        self.cfg = config
        self.node_id = node_id
        self.gpsd_proc: Optional[SupervisedProc] = None
        self.alfred_gpsd: Optional[SupervisedProc] = None
        self.forwarder: Optional[MavlinkForwarder] = None
        self.publisher: Optional[GpsPublisher] = None
        self.exec = None

    async def start(self, ctx) -> None:
        self.exec = ctx.exec

        if self.cfg.gps.enabled:
            await self._start_gps(ctx)

        if self.cfg.mavlink.enabled:
            await self._start_mavlink(ctx)

    async def _start_gps(self, ctx) -> None:
        device = self.cfg.gps.device or detect_gps_device()
        fixed = self.cfg.gps.fixed_location

        if device is None and fixed is None:
            log.info("gps: no device and no fixed location; skipping gpsd")
            return

        # Local GPS hardware: supervise gpsd ourselves (no systemd dependency).
        if device:
            self.gpsd_proc = SupervisedProc(
                "gpsd", ["gpsd", "-n", device], required=False
            )
            await self.gpsd_proc.start()

        argv = ["alfred-gpsd", "-s"]
        if fixed:
            argv += ["-l", fixed]
        elif device is None:
            log.info("gps: no hardware GPS; alfred-gpsd only publishes fixed location")

        self.alfred_gpsd = SupervisedProc("alfred-gpsd", argv, required=False)
        await self.alfred_gpsd.start()

    async def _start_mavlink(self, ctx) -> None:
        if not os.path.exists(self.cfg.mavlink.fc_serial):
            log.warning("mavlink disabled: %s not present",
                        self.cfg.mavlink.fc_serial)
            return
        try:
            import pymavlink  # noqa: F401
        except ImportError:
            log.warning("mavlink disabled: pymavlink not installed "
                        "(pip install meshd[telemetry])")
            return

        self.forwarder = MavlinkForwarder(self.cfg, gcs_ip=self.cfg.mavlink.gcs_ip)
        self.forwarder.start()
        self.publisher = GpsPublisher(self.forwarder, ctx.exec, self.node_id)
        await self.publisher.start()

    async def stop(self, ctx) -> None:
        if self.publisher:
            await self.publisher.stop()
        if self.forwarder:
            self.forwarder.stop()
            self.forwarder.join(timeout=3)
        if self.alfred_gpsd:
            await self.alfred_gpsd.stop()
        if self.gpsd_proc:
            await self.gpsd_proc.stop()

    def status(self) -> dict:
        return {
            "name": self.name,
            "gps": {
                "alfred_gpsd": self.alfred_gpsd.status() if self.alfred_gpsd else None,
                "gpsd": self.gpsd_proc.status() if self.gpsd_proc else None,
            },
            "mavlink": self.forwarder.status() if self.forwarder else None,
        }
