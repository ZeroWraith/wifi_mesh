"""Management plane: JSON-RPC over the mesh + alfred node registry.

Every node publishes its identity (node_id, role, ip, udp_port) into an
alfred data type so ``meshctl`` can discover the fleet and issue RPC calls
(UDP/JSON-RPC 2.0) to a specific ``--device``. This is the "cross-node",
authenticated management plane that the local UNIX control socket deliberately
does not expose.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from meshd.config import ManagementConfig
from meshd.context import DaemonContext
from meshd.control import build_status
from meshd.lifecycle import Lifecycle
from meshd.logs import get_logger
from meshd.netdev import Executor
from meshd.services import Service

log = get_logger("management")

ALFRED_REGISTRY_TYPE = "129"
REGISTRY_PUBLISH_INTERVAL = 30.0
RPC_TIMEOUT = 5.0

Response = dict[str, Any]
Handler = Callable[[DaemonContext, list], Awaitable[Response]]


class ManagementService(Service):
    name = "management"

    def __init__(self, config: ManagementConfig):
        self.cfg = config
        self.lifecycle: Optional[Lifecycle] = None
        self.on_stop: Optional[Callable[[], None]] = None
        self.on_restart: Optional[Callable[[], None]] = None
        self._server: Optional[asyncio.DatagramProtocol] = None
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._registry_task: Optional[asyncio.Task] = None
        self._handlers: dict[str, Handler] = {
            "ping": self._rpc_ping,
            "status": self._rpc_status,
            "stop": self._rpc_stop,
            "restart": self._rpc_restart,
            "health": self._rpc_health,
        }

    async def start(self, ctx: DaemonContext) -> None:
        self.lifecycle = ctx.extra.get("lifecycle")
        loop = asyncio.get_running_loop()
        self._server = _RpcProtocol(
            service=self, ctx=ctx,
            verify_token=lambda tok: tok == self.cfg.token,
        )
        bind_ips = [self._resolve_bind_ip(ctx)]
        transport = None
        last_err = None
        for bind_ip in bind_ips:
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: self._server, local_addr=(bind_ip, self.cfg.udp_port)
                )
                break
            except OSError as exc:
                last_err = exc
        if transport is None:
            # Node IP not yet assigned (mesh down?) — bind all interfaces.
            bind_ip = "0.0.0.0"
            transport, _ = await loop.create_datagram_endpoint(
                lambda: self._server, local_addr=(bind_ip, self.cfg.udp_port)
            )
            if last_err:
                log.info("could not bind %s: %s — falling back to 0.0.0.0",
                         bind_ips[0], last_err)
        self._transport = transport
        log.info("management RPC listening on %s:%d", bind_ip, self.cfg.udp_port)

        self._registry_task = asyncio.create_task(
            self._publish_registry(ctx)
        )

    async def stop(self, ctx: DaemonContext) -> None:
        if self._registry_task:
            self._registry_task.cancel()
            try:
                await self._registry_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._transport:
            self._transport.close()

    def status(self) -> dict:
        return {
            "name": self.name,
            "udp_port": self.cfg.udp_port,
            "listening": self._transport is not None,
        }

    def _resolve_bind_ip(self, ctx: DaemonContext) -> str:
        # Default to the node's bat0 address; fall back to any-interface if
        # the mesh is not up yet (management listens early).
        return ctx.config.node.ip if ctx.config.node.ip else "0.0.0.0"

    async def _publish_registry(self, ctx: DaemonContext) -> None:
        payload = {
            "node_id": ctx.config.node.id,
            "role": ctx.config.node.role,
            "ip": ctx.config.node.ip,
            "udp_port": self.cfg.udp_port,
            "ts": time.time(),
        }
        while True:
            try:
                await ctx.exec.run_with_stdin(
                    ["alfred", "-i", "bat0", "-s", ALFRED_REGISTRY_TYPE],
                    stdin=json.dumps(payload),
                    timeout=10,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("registry publish failed: %s", exc)
            await asyncio.sleep(REGISTRY_PUBLISH_INTERVAL)

    # -- RPC handlers ---------------------------------------------------------

    async def _rpc_ping(self, ctx: DaemonContext, params: list) -> Response:
        return {"pong": True, "node_id": ctx.config.node.id}

    async def _rpc_status(self, ctx: DaemonContext, params: list) -> Response:
        if self.lifecycle is None:
            return {"error": "lifecycle not bound"}
        return build_status(ctx, self.lifecycle)

    async def _rpc_health(self, ctx: DaemonContext, params: list) -> Response:
        return {"health": ctx.extra.get("health_last")}

    async def _rpc_stop(self, ctx: DaemonContext, params: list) -> Response:
        if self.on_stop:
            self.on_stop()
        return {"stopping": True}

    async def _rpc_restart(self, ctx: DaemonContext, params: list) -> Response:
        if self.on_restart:
            self.on_restart()
        return {"restarting": True}


class _RpcProtocol(asyncio.DatagramProtocol):
    """JSON-RPC 2.0 over UDP.

    Requests: ``{"jsonrpc":"2.0","id":1,"method":"status","params":[],"token":"..."}``
    Responses are JSON-RPC 2.0 with ``result`` or ``error``.
    """

    def __init__(self, service: ManagementService, ctx: DaemonContext,
                 verify_token: Callable[[str], bool]):
        self.service = service
        self.ctx = ctx
        self.verify_token = verify_token

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        pass

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if not data:
            return
        try:
            req = json.loads(data.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(addr, self._jsonrpc_error(None, -32700, f"parse error: {exc}"))
            return
        asyncio.ensure_future(self._dispatch(req, addr))

    def error_received(self, exc: Exception) -> None:
        log.debug("management datagram error: %s", exc)

    async def _dispatch(self, req: dict, addr: tuple) -> None:
        rid = req.get("id")
        method = req.get("method")
        if not method:
            self._send(addr, self._jsonrpc_error(rid, -32601, "method required"))
            return
        if self.ctx.running is False and method not in ("ping",):
            self._send(addr, self._jsonrpc_error(rid, -32000, "daemon is stopping"))
            return
        token = req.get("token")
        if not self.verify_token(token or ""):
            self._send(addr, self._jsonrpc_error(rid, -32001, "invalid token"))
            return
        handler = self.service._handlers.get(method)
        if handler is None:
            self._send(addr, self._jsonrpc_error(rid, -32601, f"unknown method: {method}"))
            return
        try:
            params = req.get("params")
            if not isinstance(params, list):
                params = [params] if params is not None else []
            result = await handler(self.ctx, params)
            self._send(addr, {"jsonrpc": "2.0", "id": rid, "result": result})
        except Exception as exc:  # noqa: BLE001
            log.exception("rpc %s failed", method)
            self._send(addr, self._jsonrpc_error(rid, -32603, str(exc)))

    def _send(self, addr: tuple, payload: dict) -> None:
        if self.service._transport is None:
            return
        self.service._transport.sendto(json.dumps(payload).encode(), addr)

    @staticmethod
    def _jsonrpc_error(rid, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0", "id": rid,
            "error": {"code": code, "message": message},
        }


# ---------------------------------------------------------------------------
# Fleet discovery + remote client (used by meshctl)
# ---------------------------------------------------------------------------

async def list_nodes(exec: Executor) -> list[dict]:
    """Read every node's identity record from the alfred registry."""
    out = await exec.output(["alfred", "-i", "bat0", "-r", ALFRED_REGISTRY_TYPE],
                            timeout=10)
    nodes = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            nodes.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return nodes


async def remote_call(ip: str, udp_port: int, token: str, method: str,
                      params: list | None = None,
                      timeout: float = RPC_TIMEOUT) -> dict:
    """Fire a JSON-RPC 2.0 request at a mesh node and await the response."""
    req = {
        "jsonrpc": "2.0", "id": 1, "method": method,
        "params": params or [], "token": token,
    }
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict] = loop.create_future()

    class _Client(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple) -> None:
            try:
                fut.set_result(json.loads(data.decode()))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if not fut.done():
                    fut.set_exception(exc)

        def error_received(self, exc: Exception) -> None:
            if not fut.done():
                fut.set_exception(exc)

    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Client(), local_addr=("0.0.0.0", 0),
    )
    transport.sendto(json.dumps(req).encode(), (ip, udp_port))
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        transport.close()
