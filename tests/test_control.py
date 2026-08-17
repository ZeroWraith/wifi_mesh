"""Tests for the local operator control socket (ping / status / stop)."""


import pytest

from meshd.config import dump_template, load_config
from meshd.context import DaemonContext
from meshd.control import ControlServer, rpc
from meshd.lifecycle import Lifecycle
from meshd.netdev import Executor
from meshd.radios import RadioManager
from meshd.store import Store


@pytest.mark.asyncio
async def test_control_socket_ping_status_stop(tmp_path):
    dump_template(tmp_path / "mesh.yaml")
    cfg = load_config(tmp_path / "mesh.yaml")
    store = Store(state_dir=str(tmp_path / "lib"), run_dir=str(tmp_path / "run"))
    exec = Executor()
    ctx = DaemonContext(config=cfg, store=store, exec=exec,
                        radios=RadioManager(exec, cfg.radios))
    lifecycle = Lifecycle(ctx, store=store)

    server = ControlServer(ctx, lifecycle, on_stop=lambda: None)
    await server.start()
    try:
        pong = await rpc(server.path, {"cmd": "ping"})
        assert pong["pong"] is True

        status = await rpc(server.path, {"cmd": "status"})
        assert status["node"]["node_id"] == "drone-01"
        assert status["lifecycle"]["state"] == "down"
        assert status["radios"][0]["name"] == "radioA"

        stop = await rpc(server.path, {"cmd": "stop"})
        assert stop["stopping"] is True

        unknown = await rpc(server.path, {"cmd": "nope"})
        assert "error" in unknown
    finally:
        await server.shutdown()
