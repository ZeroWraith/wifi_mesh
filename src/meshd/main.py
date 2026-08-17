"""meshd — batman-adv drone mesh control-plane daemon entry point."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from meshd import __version__, steps
from meshd.config import ConfigError, MeshConfigFile, dump_template, load_config
from meshd.context import DaemonContext
from meshd.control import ControlServer
from meshd.lifecycle import Lifecycle, LifecycleState
from meshd.logs import get_logger, setup_logging
from meshd.netdev import Executor
from meshd.qos import QosManager
from meshd.radios import RadioManager
from meshd.services import AlfredService, ServiceManager
from meshd.store import Store
from meshd.telemetry import TelemetryService

log = get_logger("main")

DEFAULT_CONFIG = "/opt/mesh/config/mesh.yaml"


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="meshd", description="batman-adv drone mesh control-plane daemon"
    )
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help=f"path to mesh.yaml (default: {DEFAULT_CONFIG})")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("-f", "--foreground", action="store_true",
                        help="run in the foreground (log to stderr)")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate config and exit")
    parser.add_argument("--init", action="store_true",
                        help="write a template mesh.yaml and exit")
    parser.add_argument("-V", "--version", action="version",
                        version=f"meshd {__version__}")
    return parser.parse_args(argv)


async def _run(ctx: DaemonContext) -> int:
    loop = asyncio.get_running_loop()
    lifecycle = Lifecycle(ctx, store=ctx.store)
    ctx.extra["lifecycle"] = lifecycle
    steps.register_data_plane_steps(lifecycle, ctx)
    if ctx.qos is not None:
        steps.register_qos_step(lifecycle, ctx)
    if ctx.services is not None:
        steps.register_services_step(lifecycle, ctx)

    stop_event = asyncio.Event()
    _install_signal_handlers(loop, stop_event)

    control = ControlServer(
        ctx, lifecycle,
        on_stop=lambda: (ctx.__setattr__("running", False), stop_event.set()),
    )
    await control.start()

    mgmt = ctx.extra.get("management")
    if mgmt is not None:
        mgmt.lifecycle = lifecycle
        mgmt.on_stop = lambda: (ctx.__setattr__("running", False), stop_event.set())
        mgmt.on_restart = lambda: stop_event.set()
        await mgmt.start(ctx)
    try:
        while ctx.running:
            results = await lifecycle.start()
            failed = [r for r in results if not r.ok]
            if failed and lifecycle.state == LifecycleState.FAILED:
                log.error("mesh failed to come up; rolling back %s", [
                    r.error for r in failed if r.error])
                await lifecycle.stop()
                return 1

            log.info("mesh online (state=%s)", lifecycle.effective_state().value)

            supervise = asyncio.create_task(_supervise(ctx, stop_event))
            await stop_event.wait()
            supervise.cancel()
            try:
                await supervise
            except asyncio.CancelledError:
                pass

            if not ctx.running:
                log.info("stopping mesh...")
                await lifecycle.stop()
                break

            # restart requested
            log.info("restarting mesh...")
            stop_event.clear()
            ctx.__setattr__("running", True)
            await lifecycle.stop()
    finally:
        if mgmt is not None:
            await mgmt.stop(ctx)
        await control.shutdown()
    return 0


def _install_signal_handlers(loop: asyncio.AbstractEventLoop,
                             stop_event: asyncio.Event) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig, lambda s=sig: (log.info("received %s", s.name),
                                    stop_event.set()))
        except NotImplementedError:
            pass


async def _supervise(ctx: DaemonContext, stop_event: asyncio.Event,
                     interval: float = 10.0) -> None:
    """Watchdog loop: log radio + bat01 health each tick."""
    while not stop_event.is_set():
        try:
            await asyncio.sleep(interval)
            if not ctx.running:
                break
            await _health_tick(ctx)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            log.exception("health tick failed")


async def _health_tick(ctx: DaemonContext) -> None:
    try:
        bat0_up = await ctx.exec.ok(["ip", "link", "show", "dev", "bat0"])
        originators_out = await ctx.exec.output(["batctl", "o"])
        originators = sum(
            1 for line in originators_out.splitlines()
            if line.strip() and not line.strip().startswith(("BATMAN", "Multicast"))
        )
        log.info("health: bat0_up=%s originators=%s", bat0_up, originators)
        ctx.extra["health_last"] = {"bat0_up": bat0_up, "originators": originators}
    except Exception as exc:  # noqa: BLE001
        log.warning("health check failed: %s", exc)


def main(argv: list | None = None) -> int:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose, foreground=args.foreground)

    cfg_path = Path(args.config)

    if args.init:
        dump_template(cfg_path)
        log.info("wrote template config to %s", cfg_path)
        return 0

    try:
        config: MeshConfigFile = load_config(cfg_path)
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return 2

    if config.management.token == "change-me":
        log.warning("management.token is the insecure default '%s' — generate one "
                    "with: meshctl token", config.management.token)

    if args.dry_run:
        log.info("configuration OK for node '%s' (ip %s)", config.node.id,
                 config.node.ip_cidr)
        return 0

    store = Store()
    exec = Executor()
    ctx = DaemonContext(
        config=config,
        store=store,
        exec=exec,
        radios=RadioManager(
            exec,
            radios=config.radios,
            mesh_id=config.mesh.id,
            essid=config.mesh.essid,
            ibss_bssid=config.mesh.ibss_bssid,
        ),
        qos=QosManager(exec, config.qos),
    )
    ctx.services = ServiceManager(ctx)
    ctx.services.add(AlfredService())
    if config.telemetry.gps.enabled or config.telemetry.mavlink.enabled:
        ctx.services.add(
            TelemetryService(config.telemetry, node_id=config.node.id)
        )
    if config.dashboard.enabled:
        try:
            from meshd.dashboard import DashboardService
            ctx.services.add(DashboardService(config.dashboard))
        except Exception as exc:  # noqa: BLE001
            log.warning("dashboard service failed to initialize: %s", exc)
    if config.video.mode != "off":
        from meshd.video import VideoService
        ctx.services.add(VideoService(config.video))

    if config.management.udp_port:
        from meshd.management import ManagementService
        ctx.extra["management"] = ManagementService(config.management)

    try:
        return asyncio.run(_run(ctx))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
