"""Tests for the mesh management plane (JSON-RPC over UDP + fleet discovery)."""

import asyncio
import json

import pytest

from meshd.config import dump_template, load_config
from meshd.context import DaemonContext
from meshd.lifecycle import Lifecycle
from meshd.management import ManagementService, remote_call
from meshd.netdev import Executor
from meshd.radios import RadioManager
from meshd.store import Store


@pytest.mark.asyncio
async def test_management_rpc_ping_status_and_auth(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    cfg.management.token = "sekrit"
    cfg.node.ip = "127.0.0.1"
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    exec = Executor()
    ctx = DaemonContext(config=cfg, store=store, exec=exec,
                        radios=RadioManager(exec, cfg.radios))
    lifecycle = Lifecycle(ctx, store=store)
    ctx.extra["lifecycle"] = lifecycle

    svc = ManagementService(cfg.management)
    await svc.start(ctx)
    try:
        # Ping
        res = await remote_call("127.0.0.1", cfg.management.udp_port, "sekrit", "ping")
        assert res["result"]["pong"] is True
        assert res["result"]["node_id"] == "drone-01"

        # Status
        res = await remote_call("127.0.0.1", cfg.management.udp_port, "sekrit", "status")
        result = res["result"]
        assert result["node"]["node_id"] == "drone-01"
        assert result["lifecycle"]["state"] == "down"

        # Bad token rejected
        res = await remote_call("127.0.0.1", cfg.management.udp_port, "wrong", "status")
        assert "error" in res
        assert res["error"]["code"] == -32001

        # Unknown method
        res = await remote_call("127.0.0.1", cfg.management.udp_port, "sekrit", "nope")
        assert "error" in res
        assert res["error"]["code"] == -32601
    finally:
        await svc.stop(ctx)


@pytest.mark.asyncio
async def test_management_rpc_stop_invokes_callback(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    cfg.management.token = "sekrit"
    cfg.node.ip = "127.0.0.1"
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    exec = Executor()
    ctx = DaemonContext(config=cfg, store=store, exec=exec,
                        radios=RadioManager(exec, cfg.radios))
    lifecycle = Lifecycle(ctx, store=store)
    ctx.extra["lifecycle"] = lifecycle

    stopped = []
    svc = ManagementService(cfg.management)
    svc.on_stop = lambda: stopped.append(True)
    await svc.start(ctx)
    try:
        res = await remote_call("127.0.0.1", cfg.management.udp_port, "sekrit", "stop")
        assert res["result"]["stopping"] is True
        assert stopped == [True]
    finally:
        await svc.stop(ctx)


@pytest.mark.asyncio
async def test_management_rejects_malformed_json(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    cfg.management.token = "sekrit"
    cfg.node.ip = "127.0.0.1"
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    exec = Executor()
    ctx = DaemonContext(config=cfg, store=store, exec=exec,
                        radios=RadioManager(exec, cfg.radios))
    svc = ManagementService(cfg.management)
    await svc.start(ctx)
    try:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        class _Probe(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                if not fut.done():
                    fut.set_result(json.loads(data.decode()))

        transport, _ = await loop.create_datagram_endpoint(
            lambda: _Probe(), local_addr=("127.0.0.1", 0)
        )
        transport.sendto(b"{not json", ("127.0.0.1", cfg.management.udp_port))
        resp = await asyncio.wait_for(fut, timeout=2)
        transport.close()
        assert "error" in resp
        assert resp["error"]["code"] == -32700
    finally:
        await svc.stop(ctx)


@pytest.mark.asyncio
async def test_management_rpc_with_params_still_works(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    cfg.management.token = "sekrit"
    cfg.node.ip = "127.0.0.1"
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    exec = Executor()
    ctx = DaemonContext(config=cfg, store=store, exec=exec,
                        radios=RadioManager(exec, cfg.radios))
    svc = ManagementService(cfg.management)
    await svc.start(ctx)
    try:
        res = await remote_call("127.0.0.1", cfg.management.udp_port,
                                "sekrit", "ping", params=["x"])
        assert res["result"]["pong"] is True
    finally:
        await svc.stop(ctx)
