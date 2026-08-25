"""batman-adv data-plane control: kernel module, ``batctl``, ``bat0``.

Wraps module loading (with routing-algorithm validation at load time, the
JetPack gotcha from the demo), interface attachment, tunables, gateway mode
and NAT for internet sharing.
"""

from __future__ import annotations

import os

from meshd.logs import get_logger
from meshd.netdev import MTU_DEFAULT, Executor

log = get_logger("batman")

BAT0 = "bat0"
MODULE = "batman_adv"
SYSFS_PREFIX = "/sys/module/batman_adv/parameters"

KNOWN_ALGOS = ("BATMAN_IV", "BATMAN_V")


class BatmanError(Exception):
    pass


async def module_loaded(exec: Executor) -> bool:
    out = await exec.output(["lsmod"])
    return any(line.split() and line.split()[0] == MODULE for line in out.splitlines())


async def module_available(exec: Executor) -> bool:
    return await exec.ok(["modinfo", MODULE])


async def load_module(exec: Executor, routing_algo: str) -> None:
    """Load batman_adv with the requested routing algorithm.

    The routing algorithm is a module parameter and (on most kernels) only
    applied at load time, so we unload first if needed.
    """
    if await module_loaded(exec):
        current = await sysfs_param(exec, "routing_algo")
        if current is not None and current.strip().upper() == routing_algo.upper():
            return
        log.info("reloading %s to apply routing_algo=%s", MODULE, routing_algo)
        await exec.run(["rmmod", MODULE])
        if await module_loaded(exec):
            raise BatmanError("could not unload existing batman_adv module")

    res = await exec.run(["modprobe", MODULE, f"routing_algo={routing_algo}"])
    if not res.ok:
        # Some distro kernels need alloc=0 / different param names; else build.
        res2 = await exec.run(["modprobe", MODULE])
        if not res2.ok:
            raise BatmanError("failed to load batman_adv module (try deploy/jetson-build.sh)")

    applied = await sysfs_param(exec, "routing_algo")
    if applied is not None and applied.strip().upper() != routing_algo.upper():
        log.warning("kernel reports routing_algo=%s (requested %s)", applied.strip(), routing_algo)
    log.info("batman_adv loaded (routing_algo=%s)", applied.strip() if applied else routing_algo)


async def unload_module(exec: Executor) -> None:
    await exec.run(["rmmod", MODULE])


async def sysfs_param(exec: Executor, name: str) -> str | None:
    path = os.path.join(SYSFS_PREFIX, name)
    try:
        with open(path) as fh:
            return fh.read().strip()
    except (FileNotFoundError, PermissionError):
        return None


async def add_interface(exec: Executor, iface: str) -> bool:
    res = await exec.run(["batctl", "if", "add", iface])
    return res.ok


async def del_interface(exec: Executor, iface: str = "bat0") -> None:
    await exec.run(["batctl", "if", "del", iface])


async def bat0_exists(exec: Executor) -> bool:
    out = await exec.output(["ip", "-o", "link", "show"])
    return any("bat0" == line.split()[1].rstrip(":") for line in out.splitlines())


async def set_orig_interval(exec: Executor, ms: int) -> bool:
    return (await exec.run(["batctl", "orig_interval", str(ms)])).ok


async def set_hop_penalty(exec: Executor, penalty: int) -> bool:
    return (await exec.run(["batctl", "hop_penalty", str(penalty)])).ok


async def set_fragmentation(exec: Executor, enabled: bool) -> bool:
    return (await exec.run(["batctl", "fragmentation", "1" if enabled else "0"])).ok


async def set_interface_routing(exec: Executor, enabled: bool) -> bool:
    """Allow routing between hard interfaces (required for multi-radio)."""
    return (await exec.run(["batctl", "interface_routing", "1" if enabled else "0"])).ok


async def set_network_coding(exec: Executor, enabled: bool) -> bool:
    return (await exec.run(["batctl", "nc", "1" if enabled else "0"])).ok


async def set_gateway_mode(exec: Executor, mode: str,
                           dlink_mbit: int = 100, ulink_mbit: int = 100) -> bool:
    if mode in ("off", "client"):
        return (await exec.run(["batctl", "gw", mode])).ok
    if mode == "server":
        return (await exec.run(["batctl", "gw", "server", f"{dlink_mbit}/{ulink_mbit}"])).ok
    return False


async def set_ip_forwarding(exec: Executor, enabled: bool) -> None:
    await exec.run(["sysctl", "-w", "net.ipv4.ip_forward=" + ("1" if enabled else "0")])


async def configure_nat(exec: Executor, external_iface: str) -> bool:
    """MASQUERADE bat0 traffic out the external interface (gateway role)."""
    ok = True
    # Check if MASQUERADE rule exists; only insert if it doesn't.
    check_args = ["iptables", "-t", "nat", "-C", "POSTROUTING", "-o", external_iface,
                  "-j", "MASQUERADE"]
    res = await exec.run(check_args)
    if not res.ok:
        insert_args = ["iptables", "-t", "nat", "-I", "POSTROUTING", "-o", external_iface,
                       "-j", "MASQUERADE"]
        res = await exec.run(insert_args)
        ok = res.ok
    await exec.run(["iptables", "-I", "FORWARD", "-i", BAT0, "-o", external_iface,
                    "-j", "ACCEPT"])
    await exec.run(["iptables", "-I", "FORWARD", "-i", external_iface, "-o", BAT0,
                    "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"])
    return ok


async def teardown_nat(exec: Executor, external_iface: str) -> None:
    await exec.run(["iptables", "-t", "nat", "-D", "POSTROUTING", "-o", external_iface,
                    "-j", "MASQUERADE"])
    await exec.run(["iptables", "-D", "FORWARD", "-i", BAT0, "-o", external_iface,
                    "-j", "ACCEPT"])
    await exec.run(["iptables", "-D", "FORWARD", "-i", external_iface, "-o", BAT0,
                    "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"])


async def assign_ip(exec: Executor, ip_cidr: str) -> bool:
    await exec.run(["ip", "addr", "flush", "dev", BAT0])
    return (await exec.run(["ip", "addr", "add", ip_cidr, "dev", BAT0])).ok


async def bring_up_bat0(exec: Executor) -> bool:
    return (await exec.run(["ip", "link", "set", BAT0, "up"])).ok


async def set_mtu(exec: Executor, mtu: int = MTU_DEFAULT) -> bool:
    return (await exec.run(["ip", "link", "set", BAT0, "mtu", str(mtu)])).ok


async def bat0_addrs(exec: Executor) -> list:
    out = await exec.output(["ip", "-4", "-o", "addr", "show", "dev", BAT0])
    addrs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3].startswith("10."):
            addrs.append(parts[3])
    return addrs
