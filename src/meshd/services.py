"""Child-service supervision for the control plane.

The daemon spawns and supervises long-running helper processes (alfred,
batadv-vis, alfred-gpsd, video engine, ...). A ``SupervisedProc`` restarts a
process that dies unexpectedly (systemd-style ``Restart=on-failure``) and
marks it failed after too many consecutive restarts.
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional

from meshd.context import DaemonContext
from meshd.logs import get_logger

log = get_logger("services")

MAX_RESTARTS = 5
RESTART_BACKOFF = 5.0  # seconds


class Service:
    name = "service"

    async def start(self, ctx: DaemonContext) -> None:
        raise NotImplementedError

    async def stop(self, ctx: DaemonContext) -> None:
        raise NotImplementedError

    def status(self) -> dict:
        return {"name": self.name, "running": True}


class SupervisedProc:
    """Long-running subprocess with auto-restart and health state."""

    def __init__(self, name: str, argv: List[str], *, env: Optional[dict] = None,
                 required: bool = False):
        self.name = name
        self.argv = argv
        self.env = env
        self.required = required
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.restarts = 0
        self.last_error: str = ""
        self.started_at: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    def status(self) -> dict:
        return {
            "name": self.name,
            "running": self.running,
            "restarts": self.restarts,
            "last_error": self.last_error,
            "uptime": round(time.time() - self.started_at, 1) if self.started_at else 0.0,
        }

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while not self._stop.is_set():
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=self.env,
            )
            self.started_at = time.time()
            log.info("service '%s' started (pid %s)", self.name, self.proc.pid)
            try:
                await self.proc.wait()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"wait failed: {exc}"
                log.error("service '%s' wait failed: %s", self.name, exc)
                self._stop.set()
            if self._stop.is_set():
                break
            self.restarts += 1
            self.last_error = f"exited rc={self.proc.returncode}"
            if self.restarts > MAX_RESTARTS:
                log.error("service '%s' gave up after %s restarts",
                          self.name, MAX_RESTARTS)
                break
            log.warning("service '%s' exited rc=%s; restarting in %ss "
                        "(%s/%s)", self.name, self.proc.returncode,
                        RESTART_BACKOFF, self.restarts, MAX_RESTARTS)
            await asyncio.sleep(RESTART_BACKOFF)

    async def stop(self) -> None:
        self._stop.set()
        if self.proc is not None and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        if self._task:
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


class AlfredService(Service):
    """alfred (L2 data exchange) + batadv-vis (topology collection)."""

    name = "alfred"

    def __init__(self):
        self.alfred = SupervisedProc(
            "alfred", ["alfred", "-i", "bat0", "-b", "bat0"], required=False
        )
        self.vis = SupervisedProc(
            "batadv-vis", ["batadv-vis", "-i", "bat0", "-s"], required=False
        )

    async def start(self, ctx: DaemonContext) -> None:
        await self.alfred.start()
        await self.vis.start()

    async def stop(self, ctx: DaemonContext) -> None:
        await self.vis.stop()
        await self.alfred.stop()

    def status(self) -> dict:
        return {
            "name": self.name,
            "children": [self.alfred.status(), self.vis.status()],
        }


class ServiceManager:
    """Owns all child services; exposes combined status."""

    def __init__(self, ctx: DaemonContext):
        self.ctx = ctx
        self.services: List[Service] = []

    def add(self, service: Service) -> None:
        self.services.append(service)

    async def start_all(self) -> None:
        for svc in self.services:
            try:
                await svc.start(self.ctx)
            except Exception as exc:  # noqa: BLE001
                log.error("service '%s' failed to start: %s", svc.name, exc)

    async def stop_all(self) -> None:
        for svc in reversed(self.services):
            try:
                await svc.stop(self.ctx)
            except Exception as exc:  # noqa: BLE001
                log.error("service '%s' failed to stop: %s", svc.name, exc)

    def status(self) -> List[dict]:
        return [svc.status() for svc in self.services]
