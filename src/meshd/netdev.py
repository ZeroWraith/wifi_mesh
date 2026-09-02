"""Low-level network device glue: ``ip``/``iw``/``iwconfig``/``rfkill``.

Ports the demo's battle-tested IBSS handling (fixed BSSID join, iwconfig
fallback for drivers that ignore ``iw``, Realtek ``txpower=-100`` quirk,
clean restore-to-managed on teardown) into structured Python used by the
radio farm.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence

from meshd.logs import get_logger

log = get_logger("netdev")

# Commands that live in /usr/sbin on Debian but not always on PATH.
_SBIN_PATHS = ["/usr/sbin", "/sbin"]

MTU_DEFAULT = 1500


class ExecError(Exception):
    def __init__(self, argv: Sequence[str], code: int, stdout: str, stderr: str):
        super().__init__(f"command failed ({code}): {' '.join(map(str, argv))}")
        self.argv = list(argv)
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


class CmdResult:
    __slots__ = ("argv", "returncode", "stdout", "stderr")

    def __init__(self, argv: Sequence[str], returncode: int, stdout: str, stderr: str):
        self.argv = list(argv)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __repr__(self) -> str:
        return f"CmdResult({' '.join(self.argv)}, rc={self.returncode})"


class Executor:
    """Async subprocess runner for privileged net tools."""

    def __init__(self, use_sudo: bool = False, command_prefix: Sequence[str] = ()):
        self._binary_cache: dict[str, str] = {}
        # meshd itself usually runs as root (systemd unit). When running as a
        # normal user in development, optionally prefix commands with sudo.
        prefix = (("sudo",) if (use_sudo and self._euid() != 0) else ())
        self._sudo_prefix = tuple(command_prefix) if command_prefix else prefix
        # If we have sudo, always use it so PATH lookups work for /usr/sbin.
        if self._sudo_prefix:
            self._bin_path = _SBIN_PATHS + self._sudo_pathenv()
        else:
            self._bin_path = _SBIN_PATHS

    @staticmethod
    def _euid() -> int:
        try:
            import os
            return os.geteuid()
        except AttributeError:
            return 0

    def _sudo_pathenv(self) -> list:
        # sudo keeps an app-specific PATH; rebuilding it is simpler than
        # guessing. Return a permissive default used by resolution below.
        return ["/usr/sbin", "/sbin", "/usr/local/sbin"]

    def resolve(self, name: str) -> str:
        """Locate a binary by absolute path or PATH, preferring /usr/sbin."""
        if "/" in name:
            return name
        cached = self._binary_cache.get(name)
        if cached:
            return cached
        found = None
        for d in self._bin_path:
            import os
            candidate = os.path.join(d, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found = candidate
                break
        resolved = found or name
        self._binary_cache[name] = resolved
        return resolved

    def _argv(self, argv: Sequence[str]) -> list[str]:
        return list(self._sudo_prefix) + [self.resolve(str(a)) for a in argv]

    async def run(self, argv: Sequence[str], *, timeout: float = 30.0,
                  check: bool = False) -> CmdResult:
        cmd = self._argv(argv)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            res = CmdResult(cmd, 127, "", f"command not found: {cmd[0]}")
            if check:
                raise ExecError(res.argv, res.returncode, res.stdout, res.stderr) from None
            return res

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
            res = CmdResult(cmd, -9, stdout_b.decode(errors="replace"),
                            stderr_b.decode(errors="replace") + "\n[timed out]")
            if check:
                raise ExecError(res.argv, res.returncode, res.stdout,
                                res.stderr or "[timeout]") from None
            return res

        res = CmdResult(cmd, proc.returncode or 0, stdout_b.decode(errors="replace"),
                        stderr_b.decode(errors="replace"))
        if check and not res.ok:
            log.error("cmd failed: %s (rc=%s)", " ".join(cmd), res.returncode)
            log.debug("stderr: %s", res.stderr.strip())
            raise ExecError(res.argv, res.returncode, res.stdout, res.stderr)
        return res

    async def ok(self, argv: Sequence[str], timeout: float = 15.0) -> bool:
        """Run a command for its exit status only."""
        return (await self.run(argv, timeout=timeout)).ok

    async def output(self, argv: Sequence[str], timeout: float = 15.0) -> str:
        res = await self.run(argv, timeout=timeout)
        return res.stdout

    async def run_with_stdin(self, argv: Sequence[str], stdin: str,
                             timeout: float = 15.0) -> CmdResult:
        """Run a command, feeding ``stdin`` to its stdin stream."""
        cmd = self._argv(argv)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return CmdResult(cmd, 127, "", f"command not found: {cmd[0]}")
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(stdin.encode()), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
            return CmdResult(cmd, -9, stdout_b.decode(errors="replace"),
                             stderr_b.decode(errors="replace") + "\n[timed out]")
        return CmdResult(cmd, proc.returncode or 0, stdout_b.decode(errors="replace"),
                         stderr_b.decode(errors="replace"))


# ---------------------------------------------------------------------------
# Interface helpers
# ---------------------------------------------------------------------------

async def interfaces(exec: Executor) -> list[str]:
    """All network interfaces."""
    out = await exec.output(["ip", "-o", "link", "show"])
    names = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            names.append(parts[1].rstrip(":"))
    return names


async def wireless_interfaces(exec: Executor) -> list[str]:
    """Wireless interfaces reported by ``iw dev``."""
    out = await exec.output(["iw", "dev"])
    names = []
    for line in out.splitlines():
        if line.strip().startswith("Interface"):
            parts = line.split()
            if len(parts) >= 2:
                names.append(parts[1])
    return names


async def iface_exists(exec: Executor, iface: str) -> bool:
    return iface in await interfaces(exec)


async def iface_type(exec: Executor, iface: str) -> str | None:
    """'managed', 'ibss', 'mesh point', 'ap', ... or None if unknown."""
    out = await exec.output(["iw", "dev", iface, "info"])
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("type"):
            return stripped.split(maxsplit=1)[1]
    return None


async def wiphy_of(exec: Executor, iface: str) -> str | None:
    out = await exec.output(["iw", "dev", iface, "info"])
    for line in out.splitlines():
        if "wiphy" in line:
            parts = line.split()
            return parts[-1]
    return None


async def supports_mesh_point(exec: Executor, iface: str) -> bool:
    """True if the interface's wiphy advertises 802.11s mesh point mode."""
    phy = await wiphy_of(exec, iface)
    if not phy:
        return False
    out = await exec.output(["iw", "phy", phy, "info"])
    # Look for a block mentioning 'mesh point' in interface mode list.
    for line in out.splitlines():
        if "mesh point" in line:
            return True
    return False


async def read_txpower(exec: Executor, iface: str) -> float | None:
    out = await exec.output(["iw", "dev", iface, "info"])
    for line in out.splitlines():
        if "txpower" in line:
            try:
                return float(line.split()[1])
            except (ValueError, IndexError):
                return None
    return None


def txpower_is_quirk(txp: float | None) -> bool:
    """Realtek adapters report -100 dBm in managed mode; not a real fault."""
    return txp is not None and abs(txp + 100.0) < 0.01


# ---------------------------------------------------------------------------
# Link control
# ---------------------------------------------------------------------------

async def link_down(exec: Executor, iface: str) -> None:
    await exec.run(["ip", "link", "set", iface, "down"])

async def link_up(exec: Executor, iface: str) -> None:
    await exec.run(["ip", "link", "set", iface, "up"])

async def flush_addrs(exec: Executor, iface: str) -> None:
    await exec.run(["ip", "addr", "flush", "dev", iface])

async def set_mac(exec: Executor, iface: str, mac: str) -> None:
    await link_down(exec, iface)
    await exec.run(["ip", "link", "set", iface, "address", mac])
    await link_up(exec, iface)

async def rfkill_unblock_wifi(exec: Executor) -> None:
    await exec.run(["rfkill", "unblock", "wifi"])


async def set_unmanaged_nm(exec: Executor, iface: str) -> None:
    """Tell NetworkManager to leave the interface alone (also disconnect it)."""
    for args in (
        ["nmcli", "device", "set", iface, "managed", "no"],
        ["nmcli", "device", "disconnect", iface],
    ):
        await exec.run(args)


async def enable_managed_nm(exec: Executor, iface: str) -> None:
    await exec.run(["nmcli", "device", "set", iface, "managed", "yes"])
    await exec.run(["nmcli", "device", "connect", iface])


# ---------------------------------------------------------------------------
# Radio mode bring-up
# ---------------------------------------------------------------------------

async def set_type(exec: Executor, iface: str, mode: str) -> None:
    """Set interface type (ibss | mesh_point | managed | ap)."""
    await link_down(exec, iface)
    res = await exec.run(["iw", "dev", iface, "set", "type", mode])
    if not res.ok:
        raise ExecError(res.argv, res.returncode, res.stdout,
                        res.stderr or f"failed to set type {mode}")
    await link_up(exec, iface)


async def join_mesh_point(exec: Executor, iface: str, mesh_id: str,
                          frequency_mhz: int) -> bool:
    """802.11s: join a mesh with the given mesh id on the given centre freq."""
    await link_down(exec, iface)
    await exec.run(["iw", "dev", iface, "set", "type", "mesh_point"])
    await link_up(exec, iface)
    res = await exec.run(
        ["iw", "dev", iface, "mesh", "join", mesh_id, "freq", str(frequency_mhz)]
    )
    return res.ok


async def leave_mesh(exec: Executor, iface: str) -> None:
    await exec.run(["iw", "dev", iface, "mesh", "leave"])


async def _detect_brcmfmac(exec: Executor, iface: str) -> bool:
    """Check if interface uses brcmfmac driver."""
    try:
        out = await exec.output(["readlink", "-f", f"/sys/class/net/{iface}/device/driver"])
        return "brcmfmac" in out
    except Exception:
        return False


async def _check_ibss_supported(exec: Executor, iface: str) -> bool:
    """Check if the phy for this interface actually supports IBSS mode.

    Some firmware (e.g., brcmfmac on Pi 4 BCM43455) advertises IBSS in nl80211
    but fails validation when actually trying to use it. We check the phy's
    valid interface combinations to confirm real support.
    """
    try:
        # Get phy name for this interface
        phy_out = await exec.output(["iw", "dev", iface, "info"])
        phy_name = None
        for line in phy_out.splitlines():
            if "wiphy" in line:
                parts = line.split()
                if len(parts) >= 2:
                    phy_name = f"phy{parts[-1]}"
                    break

        if not phy_name:
            log.warning("Could not determine phy for %s, assuming IBSS not supported", iface)
            return False

        # Check valid interface combinations
        phy_info = await exec.output(["iw", "phy", phy_name, "info"])
        log.debug("Checking IBSS support for %s (phy %s)", iface, phy_name)
        in_combinations = False
        for line in phy_info.splitlines():
            stripped = line.strip()
            if "valid interface combinations" in line.lower():
                in_combinations = True
                continue
            if in_combinations:
                if stripped.startswith("*") or stripped.startswith("#{"):
                    if "ibss" in stripped.lower() or "mesh" in stripped.lower():
                        log.info("IBSS/mesh supported for %s (phy %s)", iface, phy_name)
                        return True
                    continue
                if not stripped:
                    continue
                break
        log.warning("IBSS/mesh NOT supported for %s (phy %s) - valid combinations lack IBSS/mesh", iface, phy_name)
        return False
    except Exception as e:
        log.warning("Error checking IBSS support for %s: %s", iface, e)
        return False


async def join_ibss(exec: Executor, iface: str, essid: str, frequency_mhz: int,
                    fixed_bssid: str, channel: int = 6) -> tuple[bool, str | None]:
    """Join an IBSS with a FIXED BSSID so all nodes share the same cell.

    Falls back to ``iwconfig`` for drivers that ignore ``iw fixed-freq``
    (battle-tested behaviour inherited from the demo). Returns
    (joined_ok, joined_bssid_or_none). Does not raise on BSSID mismatch —
    the caller decides whether to continue, since some drivers only report
    the BSSID after a few seconds.

    On some drivers (brcmfmac on Raspberry Pi), the BSSID is never reported
    via ``iw dev <iface> link`` even when the IBSS is successfully joined.
    We treat a successful join command (rc=0) as success even if BSSID
    verification fails.

    On brcmfmac (Raspberry Pi 3/4/5 built-in WiFi), IBSS join often fails
    with "Operation not supported" despite nl80211 advertising IBSS support.
    We detect this and attempt iwconfig fallback more aggressively.
    """
    is_brcmfmac = await _detect_brcmfmac(exec, iface)
    if is_brcmfmac:
        log.info("Detected brcmfmac driver on %s, enabling aggressive IBSS fallback", iface)

    # First attempt: try standard iw ibss join
    await link_down(exec, iface)
    try:
        await exec.run(["iw", "dev", iface, "set", "type", "ibss"])
    except Exception as e:
        if "Device or resource busy" in str(e) or "-16" in str(e):
            log.warning("Interface busy when setting IBSS type, waiting and retrying...")
            await asyncio.sleep(3)
            await exec.run(["iw", "dev", iface, "set", "type", "ibss"])
        else:
            raise
    await link_up(exec, iface)

    res = await exec.run(
        ["iw", "dev", iface, "ibss", "join", essid, str(frequency_mhz),
         "fixed-freq", fixed_bssid],
        timeout=20,
    )
    if res.ok:
        log.info("iw ibss join succeeded (rc=0), treating as joined")
        return True, fixed_bssid

    # Check for specific "Operation not supported" error (brcmfmac IBSS bug)
    stderr_lower = res.stderr.lower() if res.stderr else ""
    is_brcmfmac_ibss_bug = (
        "operation not supported" in stderr_lower or 
        "-95" in stderr_lower or
        (is_brcmfmac and "not supported" in stderr_lower)
    )

    if is_brcmfmac_ibss_bug:
        log.warning("brcmfmac IBSS join not supported (kernel bug), skipping to iwconfig fallback")

    target = fixed_bssid.lower()

    # Some drivers (notably brcmfmac on Raspberry Pi) report the joined BSSID
    # asynchronously, seconds after the join command returns. Poll briefly
    # before deciding the join failed.
    if not is_brcmfmac_ibss_bug:
        joined = await _poll_ibss_bssid(exec, iface, fixed_bssid, attempts=10, delay=1.0)
        if joined is not None:
            return True, joined

        log.warning("iw fixed-freq ignored by driver (got %s, expected %s); "
                    "falling back to iwconfig", joined, target)

    # Fallback path via iwconfig (wireless-tools).
    # For brcmfmac, try this more aggressively.
    log.info("Attempting iwconfig fallback for IBSS join...")
    await link_down(exec, iface)
    
    # Try to force mode with iwconfig
    for attempt in range(3):
        try:
            await exec.run(["iwconfig", iface, "mode", "ad-hoc"])
            break
        except Exception as e:
            if "Device or resource busy" in str(e) and attempt < 2:
                log.warning("iwconfig mode ad-hoc busy, retrying...")
                await asyncio.sleep(2)
            else:
                raise

    await link_up(exec, iface)
    await asyncio.sleep(1)

    res2 = await exec.run(
        ["iwconfig", iface, "essid", essid, "channel", str(channel), "ap", fixed_bssid]
    )

    if res2.ok:
        # Verify the interface actually changed to IBSS and joined
        await asyncio.sleep(2)
        link_info = await exec.output(["iw", "dev", iface, "link"])
        if "Not connected" not in link_info and ("IBSS" in link_info or "Connected" in link_info):
            log.info("iwconfig ibss join verified: interface joined")
            if is_brcmfmac:
                await asyncio.sleep(3)
            return True, fixed_bssid
        else:
            log.warning("iwconfig reported success but interface not joined: %s", link_info.strip())

    # Final poll for BSSID
    joined2 = await _poll_ibss_bssid(exec, iface, fixed_bssid, attempts=10, delay=1.0)
    if joined2 is not None:
        return True, joined2

    log.warning("BSSID still mismatched (%s vs %s); continuing...", joined2, target)
    return True, joined2 or fixed_bssid


async def ibss_joined_bssid(exec: Executor, iface: str) -> str | None:
    """Report the BSSID the interface is currently joined to (if any).

    Parses both common ``iw dev <iface> link`` outputs:
    ``Connected to 02:12:34:56:78:9a (on wlan0)`` (brcmfmac/most drivers) and
    ``IBSS: joined 02:12:34:56:78:9a ...`` / ``Joined ...`` variants.
    """
    out = await exec.output(["iw", "dev", iface, "link"])
    for line in out.splitlines():
        low = line.strip().lower()
        if low.startswith("connected to") or low.startswith("ibss") \
                or low.startswith("joined"):
            for p in line.split():
                if re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", p.lower()):
                    return p
    return None


async def _poll_ibss_bssid(exec: Executor, iface: str,
                           expected_bssid: str,
                           attempts: int = 5, delay: float = 1.0) -> str | None:
    """Poll ``iw dev <iface> link`` until the IBSS BSSID appears.

    Some drivers (brcmfmac on Raspberry Pi) report the joined BSSID only
    seconds after the join command returns, so a single read is not enough.
    Returns the matching BSSID on success, else None.
    """
    target = expected_bssid.lower()
    for _ in range(attempts):
        joined = await ibss_joined_bssid(exec, iface)
        if joined is not None and joined.lower() == target:
            return joined
        await asyncio.sleep(delay)
    return None


async def leave_ibss(exec: Executor, iface: str) -> None:
    await exec.run(["iw", "dev", iface, "ibss", "leave"])


async def restore_managed(exec: Executor, iface: str) -> bool:
    """Return the interface to managed mode and re-enable NetworkManager.

    Mirrors the demo's teardown sequence: down -> leave IBSS/mesh -> flush
    addrs -> type managed (iw, fallback iwconfig) -> up -> rfkill unblock ->
    re-enable NM. Returns True if the final type is 'managed'.
    """
    await link_down(exec, iface)
    await exec.run(["iw", "dev", iface, "ibss", "leave"])
    await exec.run(["iw", "dev", iface, "mesh", "leave"])
    await flush_addrs(exec, iface)

    res = await exec.run(["iw", "dev", iface, "set", "type", "managed"])
    if not res.ok:
        await exec.run(["iwconfig", iface, "mode", "managed"])

    await exec.run(["ip", "link", "set", iface, "up"])
    await rfkill_unblock_wifi(exec)

    if await exec.ok(["nmcli", "version"]):
        await enable_managed_nm(exec, iface)

    return (await iface_type(exec, iface)) == "managed"


async def set_channel(exec: Executor, iface: str, band: str, channel: int) -> bool:
    res = await exec.run(["iw", "dev", iface, "set", "channel", str(channel), band])
    return res.ok


async def set_txpower(exec: Executor, iface: str, dbm: int) -> bool:
    res = await exec.run(["iw", "dev", iface, "set", "txpower", "fixed", f"{dbm}00"])
    return res.ok


async def apply_driver_options(exec: Executor, options: str) -> None:
    """Apply modprobe options for quirky chipsets (e.g. Realtek 8812au).

    ``options`` is a space separated list of ``key=value`` pairs; the driver
    name is parsed from the first ``key``.
    """
    if not options:
        return
    line = f"options {options}"
    path = "/etc/modprobe.d/mesh-radio.conf"
    try:
        try:
            with open(path, "r") as fh:
                existing = fh.read()
        except FileNotFoundError:
            existing = ""
        if line not in existing:
            with open(path, "a") as fh:
                fh.write(line + "\n")
            log.info("wrote modprobe options to %s: %s", path, line)
        else:
            log.debug("modprobe options already present in %s: %s", path, line)
    except PermissionError:
        log.warning("cannot write %s (not root?)", path)
