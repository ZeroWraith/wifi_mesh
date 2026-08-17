"""Local operator control socket (JSON-lines over a UNIX socket).

`meshctl` talks to the running daemon through this socket for safe,
unauthed-by-design, local-only operations: status, stop, restart, health.
Cross-node management (JSON-RPC over the mesh) is a separate plane added in
the management phase.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from meshd.context import DaemonContext
from meshd.lifecycle import Lifecycle
from meshd.logs import get_logger

log = get_logger("control")

RequestHandler = Callable[[dict], Awaitable[dict]]


def build_status(ctx: DaemonContext, lifecycle: Lifecycle) -> dict:
    """Shared status payload for the local socket and the mesh JSON-RPC server."""
    store = ctx.store
    return {
        "node": ctx.bindings(),
        "lifecycle": lifecycle.status(),
        "radios": ctx.radios.all_states() if ctx.radios else [],
        "config_hash": store.config_hash(),
        "health": ctx.extra.get("health_last"),
        "running": ctx.running,
        "services": [
            s.status() for s in (ctx.services.services if ctx.services else [])
        ],
    }


class ControlServer:
    def __init__(self, ctx: DaemonContext, lifecycle: Lifecycle,
                 on_stop: Callable[[], None] | None = None,
                 on_restart: Callable[[], None] | None = None):
        self.ctx = ctx
        self.lifecycle = lifecycle
        self.on_stop = on_stop
        self.on_restart = on_restart
        self.path = f"{ctx.store.run_dir}/mesh.sock"
        self._server: asyncio.AbstractServer | None = None

    async def _remove_stale(self) -> None:
        try:
            import os
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    async def start(self) -> None:
        await self._remove_stale()
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self.path
        )
        log.info("control socket listening on %s", self.path)

    async def shutdown(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line)
                    resp = await self._handle(req)
                except (json.JSONDecodeError, ValueError) as exc:
                    resp = {"error": f"bad request: {exc}"}
                writer.write((json.dumps(resp) + "\n").encode())
                await writer.drain()
        except ConnectionResetError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def _handle(self, req: dict) -> dict:
        cmd = req.get("cmd")
        if cmd == "ping":
            return {"pong": True, "version": "meshd"}
        if cmd == "status":
            return await self._status()
        if cmd == "stop":
            if self.on_stop:
                self.on_stop()
            return {"stopping": True}
        if cmd == "restart":
            if self.on_restart:
                self.on_restart()
            return {"restarting": True}
        return {"error": f"unknown command: {cmd}"}

    async def _status(self) -> dict:
        return build_status(self.ctx, self.lifecycle)


# ---------------------------------------------------------------------------
# Client used by ``meshctl``
# ---------------------------------------------------------------------------

async def rpc(sock_path: str, req: dict, timeout: float = 10.0) -> dict:
    reader, writer = await asyncio.open_unix_connection(path=sock_path)
    try:
        writer.write((json.dumps(req) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not line:
            return {"error": "no response from daemon"}
        return json.loads(line)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
