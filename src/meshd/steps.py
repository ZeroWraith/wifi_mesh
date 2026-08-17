"""Lifecycle step implementations for the data-plane bring-up.

```provisioning -> radios_up -> mesh_joined -> ip_assigned
                -> qos_applied -> services_started -> ready```
"""

from __future__ import annotations

from meshd import batman
from meshd.context import DaemonContext
from meshd.lifecycle import Lifecycle, LifecycleState, Step
from meshd.logs import get_logger

log = get_logger("steps")

BAT_FIREWALL_RULES = (
    ("iptables", "-I", "INPUT", "-i", batman.BAT0, "-j", "ACCEPT"),
    ("iptables", "-I", "FORWARD", "-i", batman.BAT0, "-j", "ACCEPT"),
    ("iptables", "-I", "FORWARD", "-o", batman.BAT0, "-j", "ACCEPT"),
)


# -- provisioning -------------------------------------------------------------

async def _provision_start(ctx: DaemonContext) -> None:
    """Clean any stale state from a previous run so bring-up is idempotent."""
    if await batman.bat0_exists(ctx.exec):
        await batman.del_interface(ctx.exec, "bat0")
        await ctx.exec.run(["ip", "addr", "flush", "dev", batman.BAT0])
        await ctx.exec.run(["ip", "link", "set", batman.BAT0, "down"])
        log.info("removed stale bat0")
    # Remove any gateway NAT we may have left behind.
    if ctx.config.mesh.external_iface:
        await batman.teardown_nat(ctx.exec, ctx.config.mesh.external_iface)
    await batman.set_ip_forwarding(ctx.exec, False)


async def _provision_stop(ctx: DaemonContext) -> None:
    pass


# -- radios -------------------------------------------------------------------

async def _radios_start(ctx: DaemonContext) -> None:
    states = await ctx.radios.bring_up_all()
    joined = [s["name"] for s in states if s["joined"]]
    if not joined:
        errors = {s["name"]: s["error"] for s in states if s["error"]}
        raise RuntimeError(f"no radio joined the mesh: {errors}")
    ctx.extra["radio_states"] = {s["name"]: s for s in states}


async def _radios_stop(ctx: DaemonContext) -> None:
    await ctx.radios.teardown_all(restore_managed=True)


# -- mesh / batman ------------------------------------------------------------

async def _mesh_start(ctx: DaemonContext) -> None:
    cfg = ctx.config
    await batman.load_module(ctx.exec, cfg.mesh.routing_algo)

    attached = []
    for iface in ctx.radios.attached_ifaces():
        ok = await batman.add_interface(ctx.exec, iface)
        log.info("batctl if add %s -> %s", iface, ok)
        if ok:
            ctx.radios.mark_attached(iface)
            attached.append(iface)
    if not attached:
        raise RuntimeError("no interfaces attached to batman-adv")

    await batman.set_orig_interval(ctx.exec, cfg.mesh.orig_interval_ms)
    await batman.set_hop_penalty(ctx.exec, cfg.mesh.hop_penalty)
    await batman.set_fragmentation(ctx.exec, cfg.mesh.fragmentation)
    if cfg.mesh.interface_routing:
        await batman.set_interface_routing(ctx.exec, True)
    if cfg.mesh.network_coding:
        await batman.set_network_coding(ctx.exec, True)


async def _mesh_stop(ctx: DaemonContext) -> None:
    for iface in ctx.radios.attached_ifaces():
        await batman.del_interface(ctx.exec, iface)
    if not await ctx.exec.ok(["pgrep", "-x", "alfred"]):
        await batman.unload_module(ctx.exec)


# -- ip / gateway -------------------------------------------------------------

async def _ip_start(ctx: DaemonContext) -> None:
    cfg = ctx.config
    if not await batman.assign_ip(ctx.exec, cfg.node.ip_cidr):
        raise RuntimeError(f"failed to assign IP {cfg.node.ip_cidr} to bat0")
    if not await batman.bring_up_bat0(ctx.exec):
        raise RuntimeError("failed to bring up bat0")
    await batman.set_mtu(ctx.exec)

    if cfg.mesh.gateway == "server":
        await batman.set_gateway_mode(
            ctx.exec, "server",
            cfg.mesh.gateway_download_mbit, cfg.mesh.gateway_upload_mbit,
        )
        if cfg.mesh.external_iface:
            await batman.configure_nat(ctx.exec, cfg.mesh.external_iface)
    elif cfg.mesh.gateway == "client":
        await batman.set_gateway_mode(ctx.exec, "client")

    await batman.set_ip_forwarding(ctx.exec, True)
    for rule in BAT_FIREWALL_RULES:
        await ctx.exec.run(tuple(rule))


async def _ip_stop(ctx: DaemonContext) -> None:
    for rule in BAT_FIREWALL_RULES:
        # Turn "-I" into "-D" to delete the rule.
        delete_rule = [rule[0], "-D"] + list(rule[2:])
        await ctx.exec.run(tuple(delete_rule))
    if ctx.config.mesh.external_iface:
        await batman.teardown_nat(ctx.exec, ctx.config.mesh.external_iface)
    if await batman.bat0_exists(ctx.exec):
        await batman.set_gateway_mode(ctx.exec, "off")
        await ctx.exec.run(["ip", "addr", "flush", "dev", batman.BAT0])
        await ctx.exec.run(["ip", "link", "set", batman.BAT0, "down"])
        await batman.del_interface(ctx.exec, "bat0")
    await batman.set_ip_forwarding(ctx.exec, False)


async def _qos_start(ctx: DaemonContext) -> None:
    if ctx.qos is None:
        return
    await ctx.qos.apply()


async def _qos_stop(ctx: DaemonContext) -> None:
    if ctx.qos is None:
        return
    await ctx.qos.teardown()


def register_data_plane_steps(lifecycle: Lifecycle, ctx: DaemonContext) -> None:
    lifecycle.register(
        LifecycleState.PROVISIONING,
        Step("provisioning", start=_provision_start, stop=_provision_stop),
    )
    lifecycle.register(
        LifecycleState.RADIOS_UP,
        Step("radios", start=_radios_start, stop=_radios_stop),
    )
    lifecycle.register(
        LifecycleState.MESH_JOINED,
        Step("mesh_joined", start=_mesh_start, stop=_mesh_stop),
    )
    lifecycle.register(
        LifecycleState.IP_ASSIGNED,
        Step("ip_assigned", start=_ip_start, stop=_ip_stop),
    )


async def _services_start(ctx: DaemonContext) -> None:
    if ctx.services is None:
        return
    await ctx.services.start_all()


async def _services_stop(ctx: DaemonContext) -> None:
    if ctx.services is None:
        return
    await ctx.services.stop_all()


def register_qos_step(lifecycle: Lifecycle, ctx: DaemonContext) -> None:
    """QoS is optional: if applying it fails, the mesh still runs (degraded)."""
    lifecycle.register(
        LifecycleState.QOS_APPLIED,
        Step("qos", start=_qos_start, stop=_qos_stop, required=False),
    )


def register_services_step(lifecycle: Lifecycle, ctx: DaemonContext) -> None:
    lifecycle.register(
        LifecycleState.SERVICES_STARTED,
        Step("services", start=_services_start, stop=_services_stop, required=False),
    )
