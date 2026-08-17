"""Dashboard service: Flask-based mesh visualization served by meshd.

Bundles the dashboard that previously lived as a standalone Flask app
(``mesh_dashboard/``) into the daemon so it is supervised by meshd and can
read mesh state from the Executor (batctl/batadv-vis/alfred) rather than
shelling out from a detached process. Serving is optional: if Flask is not
installed, the service degrades gracefully to "off".
"""

from __future__ import annotations

import json
import os
import time
from importlib import resources
from typing import Any

from meshd.config import DashboardConfig
from meshd.context import DaemonContext
from meshd.logs import get_logger
from meshd.services import Service

log = get_logger("dashboard")

try:
    from flask import Flask, jsonify, render_template
    _HAVE_FLASK = True
except ImportError:  # pragma: no cover - exercised on systems w/o flask
    _HAVE_FLASK = False

    class Flask:  # type: ignore[no-redef]
        pass

DEFAULT_RENDER_TIMEOUT = 5.0


def bundled_template_dir() -> str:
    """Directory of the dashboard template bundled inside the meshd package."""
    return str(resources.files("meshd").joinpath("dashboard_templates"))


class DashboardService(Service):
    name = "dashboard"

    def __init__(self, config: DashboardConfig):
        self.cfg = config
        self.exec = None
        self._app = None
        self._server = None
        self._thread: Any | None = None

    async def start(self, ctx: DaemonContext) -> None:
        if not self.cfg.enabled:
            log.info("dashboard disabled (dashboard.enabled=false)")
            return
        if not _HAVE_FLASK:
            log.warning("dashboard requested but flask is not installed "
                        "(pip install 'meshd[dashboard]')")
            return
        self.exec = ctx.exec
        self._app = self._build_app(ctx)
        await self._serve(ctx)

    async def _serve(self, ctx: DaemonContext) -> None:
        import threading
        from wsgiref.simple_server import WSGIServer, make_server

        class _Server(WSGIServer):
            daemon_threads = True
            allow_reuse_address = True

        host = self.cfg.host or "0.0.0.0"
        try:
            self._server = make_server(
                host, self.cfg.port, self._app, server_class=_Server
            )
        except OSError as exc:
            log.error("dashboard could not bind %s:%d: %s", host, self.cfg.port, exc)
            return
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("dashboard listening on http://%s:%d", host, self.cfg.port)

    async def stop(self, ctx: DaemonContext) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._server = None

    def status(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.cfg.enabled and self._server is not None,
            "host": self.cfg.host,
            "port": self.cfg.port,
        }

    # -- Flask app ------------------------------------------------------------

    def _build_app(self, ctx: DaemonContext):
        if not _HAVE_FLASK:
            return None
        app = Flask(__name__)

        template_dir = self.cfg.template_dir or bundled_template_dir()
        if os.path.isdir(template_dir):
            app.template_folder = template_dir
        else:
            log.warning("dashboard template dir '%s' missing", template_dir)

        @app.route("/")
        def index():
            return render_template("index.html")

        @app.route("/api/mesh/status")
        def api_status():
            return self._json_or_error(self._api_agg_status())

        @app.route("/api/mesh/topology")
        def api_topology():
            return self._json_or_error(self._api_topology())

        @app.route("/api/mesh/originators")
        def api_originators():
            return self._json_or_error({"originators": self._batctl_json("oj")})

        @app.route("/api/mesh/neighbors")
        def api_neighbors():
            return self._json_or_error({"neighbors": self._batctl_json("nj")})

        @app.route("/api/mesh/interfaces")
        def api_interfaces():
            return self._json_or_error(self._api_interfaces())

        @app.route("/api/mesh/gateways")
        def api_gateways():
            return self._json_or_error({"gateways": self._batctl_json("gwj")})

        @app.route("/api/mesh/gps")
        def api_gps():
            return self._json_or_error({"positions": self._alfred_compact("128")})

        @app.route("/api/mesh/nodes")
        def api_nodes():
            return self._json_or_error({"nodes": self._alfred_compact("129")})

        @app.route("/api/health")
        def api_health():
            return self._json_or_error(self._api_health(ctx))

        return app

    def _json_or_error(self, data):
        try:
            return jsonify(data)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500

    # -- Data providers -------------------------------------------------------

    def _run(self, argv: list, timeout: float = DEFAULT_RENDER_TIMEOUT) -> str:
        import asyncio

        if self.exec is None:
            return ""
        try:
            return asyncio.run(self.exec.output(argv, timeout=timeout))
        except Exception:  # noqa: BLE001
            return ""

    def _batctl_json(self, flag: str) -> Any:
        out = self._run(["batctl", flag])
        if not out:
            return []
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return []

    def _alfred_compact(self, data_typ: str) -> list:
        """`alfred -r <type>` emits JSON per line; compact into a list."""
        out = self._run(["alfred", "-i", "bat0", "-r", data_typ], timeout=6)
        items = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return items

    def _api_agg_status(self) -> dict:
        bat0_ip = ""
        bat0_up = False
        out = self._run(["ip", "-4", "addr", "show", "dev", "bat0"])
        for line in out.splitlines():
            if "state UP" in line:
                bat0_up = True
            if "inet " in line:
                bat0_ip = line.split()[1].split("/")[0]

        originators = self._batctl_json("oj")
        node_count, nodes = 0, []
        stale_threshold_ms = 30000
        for orig in originators:
            last_seen = orig.get("last_seen_msecs", 0)
            stale = last_seen > stale_threshold_ms
            node_count += 0 if stale else 1
            nodes.append({
                "mac": orig.get("orig_address", orig.get("originator", "unknown")),
                "tq": orig.get("tq", 0) if not stale else 0,
                "nexthop": orig.get("next_hop", ""),
                "outgoing_interface": orig.get("hard_ifname",
                                               orig.get("outgoing_iface", "")),
                "last_seen_ms": last_seen,
                "stale": stale,
            })

        neighbors = self._batctl_json("nj")
        neighbor_count = len(neighbors) if isinstance(neighbors, list) else 0

        gateways = self._batctl_json("gwj")
        gateway_count = len(gateways) if isinstance(gateways, list) else 0

        return {
            "local_ip": bat0_ip,
            "bat0_up": bat0_up,
            "mesh_active": bat0_up and node_count > 0,
            "node_count": node_count,
            "neighbor_count": neighbor_count,
            "gateway_count": gateway_count,
            "nodes": nodes,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _api_topology(self) -> list:
        out = self._run(["batadv-vis", "-f", "json"], timeout=6)
        entries = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return entries

    def _api_interfaces(self) -> dict:
        out = self._run(["batctl", "if"])
        ifaces = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and ":" in parts[0]:
                ifaces.append({"name": parts[0].rstrip(":"),
                               "status": parts[1] if len(parts) > 1 else "unknown"})
        return {"interfaces": ifaces}

    def _api_health(self, ctx: DaemonContext) -> dict:
        lc = ctx.extra.get("lifecycle")
        return {
            "running": ctx.running,
            "state": lc.effective_state().value if lc else "unknown",
            "health": ctx.extra.get("health_last"),
            "node": ctx.bindings(),
        }

