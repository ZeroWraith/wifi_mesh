"""QoS engine — URLLC command & control priority over the mesh.

Mirrors the Doodle Labs "Optimize C&C for URLLC" model: flows are classified
by port/protocol and stamped with a DSCP value, then a ``tc`` HTB hierarchy on
``bat0`` enforces per-class rates/priorities. C&C traffic (DSCP CS6/EF) gets a
strict-priority, low-bandwidth class that preempts video and best-effort.

Note: this is *egress queueing* — it protects your own radio from being
swamped by your own bulk traffic. It cannot fix RF airtime contention imposed
by other transmitters; that is a PHY concern out of software's reach.
"""

from __future__ import annotations

from meshd.config import QosClassConfig, QosConfig
from meshd.logs import get_logger
from meshd.netdev import Executor

log = get_logger("qos")

# DSCP name -> 6-bit value (RFC 2474 / RFC 3246 / RFC 4594).
DSCP_VALUES: dict[str, int] = {
    "CS0": 0, "CS1": 8, "CS2": 16, "CS3": 24, "CS4": 32,
    "CS5": 40, "CS6": 48, "CS7": 56,
    "EF": 46,
    "AF11": 10, "AF12": 12, "AF13": 14,
    "AF21": 18, "AF22": 20, "AF23": 22,
    "AF31": 26, "AF32": 28, "AF33": 30,
    "AF41": 34, "AF42": 36, "AF43": 38,
}

ROOT_HANDLE = "1:"
ROOT_CLASS = "1:1"
# Class numbers start at 1:11 to avoid the root (1:1).
CLS_BASE = 11


def dscp_tos(dscp: int) -> int:
    """DSCP (6 bits) -> full TOS byte shift for `tc u32` matches."""
    return dscp << 2


def parse_rate(rate: str) -> str:
    """Normalise '10mbit' / '1000kbit' for tc; pass through otherwise."""
    r = rate.strip().lower()
    if r.endswith("mbit"):
        try:
            val = float(r[:-4])
            return f"{int(val * 1000)}kbit"
        except ValueError:
            pass
    return r


class QosManager:
    def __init__(self, exec: Executor, config: QosConfig, iface: str = "bat0"):
        self.exec = exec
        self.config = config
        self.iface = iface
        self._enabled = False
        self._nums: dict[str, int] = {}

    def _assign_numbers(self) -> None:
        """Map each class name to a unique tc class number (1:11, 1:12, ...)."""
        self._nums = {
            c.name: CLS_BASE + i for i, c in enumerate(self.config.classes)
        }

    # -- public ---------------------------------------------------------------

    async def apply(self) -> None:
        if not self.config.enabled:
            log.info("qos disabled in config; skipping")
            return
        await self._flush()
        await self._add_tc_tree()
        await self._add_mangle_rules()
        self._enabled = True
        log.info("qos applied on %s", self.iface)

    async def teardown(self) -> None:
        await self._remove_mangle_rules()
        await self._remove_tc_tree()
        self._enabled = False
        log.info("qos removed from %s", self.iface)

    async def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "configured": self.config.enabled,
            "classes": [c.name for c in self.config.classes],
            "iface": self.iface,
        }

    # -- tc -------------------------------------------------------------------

    async def _flush(self) -> None:
        await self._remove_tc_tree()

    async def _remove_tc_tree(self) -> None:
        await self.exec.run(["tc", "qdisc", "del", "dev", self.iface, "root"])

    async def _add_tc_tree(self) -> None:
        classes = [c for c in self.config.classes]
        if not classes:
            return
        self._assign_numbers()

        default_clsid = self._clsid_for_default(classes)

        cmds = [
            ["tc", "qdisc", "add", "dev", self.iface, "root", "handle", ROOT_HANDLE,
             "htb", "default", default_clsid],
            ["tc", "class", "add", "dev", self.iface, "parent", ROOT_HANDLE,
             "classid", ROOT_CLASS, "htb", "rate", "100mbit"],
        ]
        for c in classes:
            clsid = self._class_id(c)
            leaf = self._leaf_qdisc(c)
            cmds.append(
                ["tc", "class", "add", "dev", self.iface, "parent", ROOT_CLASS,
                 "classid", clsid, "htb",
                 "rate", parse_rate(c.rate or "10mbit"),
                 "ceil", parse_rate(c.ceil or "100mbit"),
                 "prio", str(c.prio)]
            )
            if leaf:
                cmds.append(["tc", "qdisc", "add", "dev", self.iface,
                             "parent", clsid, *leaf])

        for cmd in cmds:
            await self.exec.run(cmd)

        await self._add_filters(classes)

    def _clsid_for_default(self, classes: list[QosClassConfig]) -> str:
        default = next((c for c in classes if c.is_default), classes[-1])
        return self._class_id(default)

    def _class_id(self, c: QosClassConfig) -> str:
        return f"1:{self._nums[c.name]:x}"

    @staticmethod
    def _leaf_qdisc(c: QosClassConfig) -> list[str] | None:
        return ["sfq", "perturb", "10"]

    async def _add_filters(self, classes: list[QosClassConfig]) -> None:
        prio = 1
        for c in classes:
            clsid = self._class_id(c)
            for dscp_name in c.dscp:
                dscp = DSCP_VALUES.get(dscp_name.upper())
                if dscp is None:
                    log.warning("qos class '%s': unknown DSCP '%s'", c.name, dscp_name)
                    continue
                tos = dscp_tos(dscp)
                await self.exec.run(
                    ["tc", "filter", "add", "dev", self.iface, "parent", ROOT_HANDLE,
                     "protocol", "ip", "prio", str(prio), "u32",
                     "match", "ip", "tos", hex(tos), "0xfc",
                     "flowid", clsid]
                )
                prio += 1
        # Catch-all to best-effort.
        default_clsid = self._clsid_for_default(classes)
        await self.exec.run(
            ["tc", "filter", "add", "dev", self.iface, "parent", ROOT_HANDLE,
             "protocol", "ip", "prio", "100", "u32",
             "match", "u32", "0", "0", "flowid", default_clsid]
        )

    # -- iptables mangle ------------------------------------------------------

    def _mangle_cmds(self) -> list[list[str]]:
        cmds: list[list[str]] = []
        for c in self.config.classes:
            if not c.dscp:
                continue
            dscp = DSCP_VALUES.get(c.dscp[0].upper())
            if dscp is None:
                continue
            for m in c.matches:
                args = m.to_iptables_args()
                # Locally-generated traffic and transit traffic egressing bat0.
                for chain in ("OUTPUT", "FORWARD"):
                    cmds.append(
                        ["iptables", "-t", "mangle", "-A", chain,
                         "-o", self.iface, *args,
                         "-j", "DSCP", "--set-dscp", str(dscp)]
                    )
        return cmds

    def _mangle_delete_cmds(self) -> list[list[str]]:
        deletes: list[list[str]] = []
        for c in self.config.classes:
            if not c.dscp:
                continue
            dscp = DSCP_VALUES.get(c.dscp[0].upper())
            if dscp is None:
                continue
            for m in c.matches:
                args = m.to_iptables_args()
                for chain in ("OUTPUT", "FORWARD"):
                    deletes.append(
                        ["iptables", "-t", "mangle", "-D", chain,
                         "-o", self.iface, *args,
                         "-j", "DSCP", "--set-dscp", str(dscp)]
                    )
        return deletes

    async def _add_mangle_rules(self) -> None:
        for cmd in self._mangle_cmds():
            await self.exec.run(cmd)
        self._applied_classes = [c.name for c in self.config.classes]

    async def _remove_mangle_rules(self) -> None:
        for cmd in self._mangle_delete_cmds():
            await self.exec.run(cmd)


async def status_of(exec: Executor, iface: str = "bat0") -> dict:
    """Human/API-facing summary of the current tc hierarchy on ``iface``."""
    out = await exec.output(["tc", "-s", "qdisc", "show", "dev", iface])
    return {"iface": iface, "qdisc": out.strip()}
