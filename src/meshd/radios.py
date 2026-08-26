"""Radio farm: bring up and tear down each configured WiFi radio.

Handles automatic interface selection, 802.11s mesh-point vs IBSS fallback
(auto-detection from the adapter's capabilities, as in the demo), fixed-BSSID
IBSS joining, channel / txpower application and the Realtek txpower quirk.
"""

from __future__ import annotations

from dataclasses import dataclass

from meshd import netdev
from meshd.config import RadioConfig
from meshd.logs import get_logger
from meshd.netdev import Executor

log = get_logger("radios")

DEFAULT_IBSS_BSSID = "02:12:34:56:78:9a"


@dataclass
class RadioState:
    name: str
    iface: str = ""
    mode: str = "auto"          # resolved: "mesh" | "ibss"
    joined: bool = False
    attached: bool = False
    txpower: float | None = None
    txpower_quirk: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "iface": self.iface,
            "mode": self.mode,
            "joined": self.joined,
            "attached": self.attached,
            "txpower": self.txpower,
            "txpower_quirk": self.txpower_quirk,
            "error": self.error,
        }


class RadioManager:
    def __init__(self, exec: Executor, radios: list[RadioConfig],
                 mesh_id: str = "drone-mesh", essid: str = "drone-mesh",
                 ibss_bssid: str = DEFAULT_IBSS_BSSID):
        self.exec = exec
        self.radios = radios
        self.mesh_id = mesh_id
        self.essid = essid
        self.ibss_bssid = ibss_bssid
        self.states: dict[str, RadioState] = {
            r.name: RadioState(name=r.name, mode=r.mode) for r in radios
        }
        self._used_ifaces: set = set()

    def state(self, name: str) -> RadioState:
        return self.states[name]

    def all_states(self) -> list[dict]:
        return [s.to_dict() for s in self.states.values()]

    # -- interface resolution ------------------------------------------------

    async def _resolve_iface(self, cfg: RadioConfig) -> str:
        if cfg.iface and cfg.iface != "auto":
            if not await netdev.iface_exists(self.exec, cfg.iface):
                raise RuntimeError(f"radio '{cfg.name}': interface {cfg.iface} not found")
            return cfg.iface
        wifis = await netdev.wireless_interfaces(self.exec)
        free = [w for w in wifis if w not in self._used_ifaces]
        if not free:
            raise RuntimeError(
                f"radio '{cfg.name}': no free wireless interface to auto-select"
            )
        log.info("radio '%s': auto-selected interface %s", cfg.name, free[0])
        return free[0]

    async def _resolve_mode(self, iface: str) -> str:
        if await netdev.supports_mesh_point(self.exec, iface):
            return "mesh"
        return "ibss"

    # -- bring-up -------------------------------------------------------------

    async def bring_up_all(self) -> list[dict]:
        for cfg in self.radios:
            await self._bring_up_one(cfg)
        return self.all_states()

    async def _bring_up_one(self, cfg: RadioConfig) -> None:
        state = self.states[cfg.name]
        try:
            iface = await self._resolve_iface(cfg)
            state.iface = iface
            self._used_ifaces.add(iface)

            await netdev.rfkill_unblock_wifi(self.exec)
            if await self.exec.ok(["nmcli", "version"]):
                await netdev.set_unmanaged_nm(self.exec, iface)

            # Clear any stale wireless state before reconfiguring.
            await netdev.leave_ibss(self.exec, iface)
            await netdev.leave_mesh(self.exec, iface)
            await netdev.flush_addrs(self.exec, iface)
            await netdev.link_down(self.exec, iface)

            if cfg.mac:
                await netdev.set_mac(self.exec, iface, cfg.mac)

            if cfg.mode == "auto":
                state.mode = await self._resolve_mode(iface)
            else:
                state.mode = cfg.mode

            log.info("radio '%s' (%s): mode=%s channel=%s band=%s",
                     cfg.name, iface, state.mode, cfg.channel, cfg.band)

            if state.mode == "mesh":
                state.joined = await netdev.join_mesh_point(
                    self.exec, iface, self.mesh_id, cfg.frequency_mhz
                )
                if not state.joined:
                    state.error = "mesh join failed"
            else:
                _, joined_bssid = await netdev.join_ibss(
                    self.exec, iface, self.essid, cfg.frequency_mhz, self.ibss_bssid
                )
                if joined_bssid is None:
                    joined_bssid = await netdev.ibss_joined_bssid(self.exec, iface)
                state.joined = joined_bssid is not None
                if not state.joined:
                    if "does not support IBSS" in (state.error or ""):
                        state.error = ("IBSS not supported by hardware/firmware. "
                                       "Pi 4 built-in WiFi (BCM43455) lacks IBSS support. "
                                       "Use USB WiFi dongle (ath9k/rtl8812au/mt7601u) "
                                       "or set radio mode='mesh' for 802.11s if supported.")
                    else:
                        state.error = "IBSS join could not be verified"

            if cfg.txpower_dbm:
                await netdev.set_txpower(self.exec, iface, cfg.txpower_dbm)

            txp = await netdev.read_txpower(self.exec, iface)
            state.txpower = txp
            state.txpower_quirk = netdev.txpower_is_quirk(txp)
            if state.txpower_quirk:
                log.warning("radio '%s' txpower=%s dBm (known Realtek quirk)",
                            cfg.name, txp)

            if cfg.driver_options:
                await netdev.apply_driver_options(self.exec, cfg.driver_options)

        except Exception as exc:  # noqa: BLE001
            state.error = str(exc)
            log.error("radio '%s' failed: %s", cfg.name, exc)

    # -- teardown -------------------------------------------------------------

    async def teardown_all(self, restore_managed: bool = True) -> None:
        for cfg in reversed(self.radios):
            await self._teardown_one(cfg, restore_managed)

    async def _teardown_one(self, cfg: RadioConfig, restore_managed: bool) -> None:
        state = self.states[cfg.name]
        if not state.iface:
            return
        iface = state.iface
        log.info("radio '%s' (%s): tearing down", cfg.name, iface)
        if restore_managed:
            await netdev.restore_managed(self.exec, iface)
        else:
            await netdev.leave_ibss(self.exec, iface)
            await netdev.leave_mesh(self.exec, iface)
            await netdev.flush_addrs(self.exec, iface)
            await netdev.link_down(self.exec, iface)
        state.joined = False
        state.attached = False

    # -- helpers --------------------------------------------------------------

    def mark_attached(self, iface: str) -> None:
        for st in self.states.values():
            if st.iface == iface:
                st.attached = True

    def attached_ifaces(self) -> list[str]:
        return [st.iface for st in self.states.values() if st.joined]

    async def scan(self, iface: str | None = None) -> dict:
        """Poor-man's spectrum survey: scan visible networks on the wiphy."""
        target = iface or (self.radios[0].iface if self.radios else None)
        if not target:
            return {"error": "no interface"}
        phy = await netdev.wiphy_of(self.exec, target)
        if not phy:
            return {"error": "no wiphy"}
        out = await self.exec.output(["iw", "phy", phy, "scan"])
        results = []
        current: dict = {}
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("BSS "):
                if current:
                    results.append(current)
                current = {"bssid": stripped.split()[1], "signal": None,
                           "ssid": None, "freq": None}
            elif current:
                if stripped.startswith("signal:"):
                    current["signal"] = stripped.split()[1]
                elif stripped.startswith("SSID:"):
                    current["ssid"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("freq:"):
                    try:
                        current["freq"] = int(stripped.split()[1])
                    except (IndexError, ValueError):
                        pass
        if current:
            results.append(current)
        return {"results": results}
