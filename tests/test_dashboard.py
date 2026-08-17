"""Tests for the meshd dashboard service (Flask app + data endpoints)."""

import asyncio
import json

import pytest

from meshd.config import DashboardConfig, dump_template, load_config
from meshd.context import DaemonContext
from meshd.dashboard import DashboardService
from meshd.netdev import Executor
from meshd.store import Store


@pytest.mark.asyncio
async def test_dashboard_endpoints_respond(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    cfg.dashboard.enabled = True
    cfg.dashboard.port = 8091
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    ctx = DaemonContext(config=cfg, store=store, exec=Executor())

    svc = DashboardService(cfg.dashboard)
    await svc.start(ctx)
    await asyncio.sleep(0.2)
    try:
        data = await _get("http://127.0.0.1:8091/api/mesh/status")
        assert data["bat0_up"] is False
        assert "mesh_active" in data
        assert data["node_count"] == 0

        gps = await _get("http://127.0.0.1:8091/api/mesh/gps")
        assert isinstance(gps["positions"], list)

        health = await _get("http://127.0.0.1:8091/api/health")
        assert health["node"]["node_id"] == "drone-01"
        assert health["running"] is True

        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8091/", timeout=3) as resp:
            body = resp.read()
            assert resp.status == 200
            assert b"BATMAN-ADV" in body
    finally:
        await svc.stop(ctx)


@pytest.mark.asyncio
async def test_dashboard_disabled_does_not_bind(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    cfg.dashboard.enabled = False
    cfg.dashboard.port = 8092
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    ctx = DaemonContext(config=cfg, store=store, exec=Executor())

    svc = DashboardService(cfg.dashboard)
    await svc.start(ctx)
    assert svc._server is None
    await svc.stop(ctx)
    assert svc.status()["enabled"] is False


@pytest.mark.asyncio
async def test_dashboard_config_roundtrip(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    d = DashboardConfig(enabled=True, port=9090, host="0.0.0.0")
    d.validate()
    assert d.port == 9090
    assert cfg.dashboard.validate is not None


async def _get(url: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(url, timeout=3) as resp:
        return json.loads(resp.read().decode())

