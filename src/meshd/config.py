"""Declarative node configuration for the mesh system.

Loads ``mesh.yaml`` into validated dataclasses. Single source of truth for
node identity, radio farm, mesh / batman-adv parameters, QoS classes,
telemetry and video settings. Replaces the demo's ``config.sh``.
"""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when a configuration is invalid or cannot be loaded."""


DEFAULT_NETMASK = "/24"

ROLES = ("drone", "ground-station", "relay")
GATEWAY_MODES = ("off", "server", "client")
RADIO_MODES = ("auto", "mesh", "ibss")
BANDS = ("2.4g", "5g", "6g")
ROUTING_ALGOS = ("BATMAN_IV", "BATMAN_V")

# channel -> frequency (MHz) for band base calculations
BAND_BASE_FREQ = {"2.4g": 2407, "5g": 5000, "6g": 5955}

# IPv4 private block used for the mesh
MESH_NETWORK = "10.0.0.0/24"
MESH_DNS = "8.8.8.8"


def _validate_re(v: str, pattern: str, field_name: str) -> None:
    if not re.match(pattern, v):
        raise ConfigError(f"{field_name} '{v}' does not match {pattern}")


def _validate_ip(ip: str, field_name: str) -> None:
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        raise ConfigError(f"{field_name} '{ip}' is not a valid IPv4 address")


def _validate_id(node_id: str) -> None:
    _validate_re(node_id, r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$", "node.id")


def _validate_mac(mac: str, field_name: str) -> None:
    _validate_re(
        mac, r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", field_name
    )


def _as_int(value: Any, field_name: str, lo: int, hi: int, default: int) -> int:
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{field_name} must be an integer, got {value!r}") from None
    if not lo <= v <= hi:
        raise ConfigError(f"{field_name} must be in [{lo}, {hi}], got {v}")
    return v


@dataclass
class NodeConfig:
    id: str = "drone-01"
    role: str = "drone"
    ip: str = "10.0.0.3"
    netmask: str = DEFAULT_NETMASK
    hostname: str | None = None

    def validate(self) -> None:
        _validate_id(self.id)
        if self.role not in ROLES:
            raise ConfigError(f"node.role must be one of {ROLES}, got '{self.role}'")
        _validate_ip(self.ip, "node.ip")
        m = re.match(r"^/\d{1,2}$", self.netmask)
        if not m:
            raise ConfigError(
                f"node.netmask must be a CIDR suffix like '/24', got "
                f"'{self.netmask}'"
            )

    @property
    def ip_cidr(self) -> str:
        return f"{self.ip}{self.netmask}"


@dataclass
class MeshConfig:
    id: str = "drone-mesh"
    essid: str = "drone-mesh"
    ibss_bssid: str = "02:12:34:56:78:9a"
    routing_algo: str = "BATMAN_V"
    orig_interval_ms: int = 1000
    hop_penalty: int = 15
    fragmentation: bool = True
    interface_routing: bool = True
    network_coding: bool = False
    gateway: str = "off"
    gateway_download_mbit: int = 100
    gateway_upload_mbit: int = 100
    external_iface: str | None = None
    dns_server: str = MESH_DNS

    def validate(self) -> None:
        _validate_id(self.id)
        if self.essid:
            _validate_re(self.essid, r"^[\x20-\x7e]{1,32}$", "mesh.essid")
        _validate_mac(self.ibss_bssid, "mesh.ibss_bssid")
        if self.routing_algo not in ROUTING_ALGOS:
            raise ConfigError(
                f"mesh.routing_algo must be one of {ROUTING_ALGOS}, got '{self.routing_algo}'"
            )
        self.orig_interval_ms = _as_int(
            self.orig_interval_ms, "mesh.orig_interval_ms", 100, 60000, 1000
        )
        self.hop_penalty = _as_int(self.hop_penalty, "mesh.hop_penalty", 0, 255, 15)
        if self.gateway not in GATEWAY_MODES:
            raise ConfigError(
                f"mesh.gateway must be one of {GATEWAY_MODES}, got '{self.gateway}'"
            )
        self.gateway_download_mbit = _as_int(
            self.gateway_download_mbit, "mesh.gateway_download_mbit", 1, 10000, 100
        )
        self.gateway_upload_mbit = _as_int(
            self.gateway_upload_mbit, "mesh.gateway_upload_mbit", 1, 10000, 100
        )


@dataclass
class RadioConfig:
    name: str = "radioA"
    iface: str = "auto"
    mode: str = "auto"
    band: str = "2.4g"
    channel: int = 6
    txpower_dbm: int | None = None
    mac: str | None = None
    driver_options: str = ""

    def validate(self) -> None:
        if self.mode not in RADIO_MODES:
            raise ConfigError(
                f"radios[].mode must be one of {RADIO_MODES}, got '{self.mode}'"
            )
        if self.band not in BANDS:
            raise ConfigError(
                f"radios[].band must be one of {BANDS}, got '{self.band}'"
            )
        if self.band == "2.4g":
            lo, hi = 1, 14
        elif self.band == "6g":
            lo, hi = 1, 233
        else:
            lo, hi = 34, 177
        self.channel = _as_int(self.channel, "radios[].channel", lo, hi, 6)
        if self.txpower_dbm is not None:
            self.txpower_dbm = _as_int(
                self.txpower_dbm, "radios[].txpower_dbm", 1, 30, 20
            )
        if self.mac:
            _validate_mac(self.mac, f"radios[].mac ({self.name})")

    @property
    def frequency_mhz(self) -> int:
        """802.11 channel -> center frequency in MHz."""
        if self.band == "2.4g":
            return 2412 + (self.channel - 1) * 5
        if self.band == "5g":
            return 5000 + self.channel * 5
        if self.band == "6g":
            return BAND_BASE_FREQ["6g"] + (self.channel - 1) * 5
        raise ConfigError(f"unsupported band {self.band}")


@dataclass
class QosMatch:
    protocol: str = "udp"
    dport: str | None = None
    sport: str | None = None
    dscp: int | None = None

    def to_iptables_args(self) -> list[str]:
        args: list[str] = ["-p", self.protocol]
        if self.dport:
            args += ["--dport", self.dport]
        if self.sport:
            args += ["--sport", self.sport]
        return args

    def to_tc_args(self) -> list[str]:
        args: list[str] = ["protocol", "ip", "prio", "2"]
        if self.dscp is not None:
            args += ["match", "ip", "tos", hex(self.dscp << 2), "0xfc"]
        else:
            args += ["match", "ip", "tos", "0x00", "0xfc"]
        return args


@dataclass
class QosClassConfig:
    name: str = "best_effort"
    dscp: list[str] = field(default_factory=list)
    matches: list[QosMatch] = field(default_factory=list)
    rate: str = "10mbit"
    ceil: str | None = None
    prio: int = 2
    is_default: bool = False

    def validate(self) -> None:
        self.prio = _as_int(self.prio, f"qos.classes[].prio ({self.name})", 0, 7, 2)


@dataclass
class QosConfig:
    enabled: bool = True
    classes: list[QosClassConfig] = field(default_factory=list)

    def validate(self) -> None:
        names = [c.name for c in self.classes]
        if len(names) != len(set(names)):
            raise ConfigError("qos.classes must have unique names")
        for c in self.classes:
            c.validate()
        if not any(c.is_default for c in self.classes):
            self.classes.append(QosClassConfig(is_default=True))


@dataclass
class GpsConfig:
    enabled: bool = True
    device: str | None = None  # None = auto-detect
    fixed_location: str | None = None  # "lat,lon,alt" for ground station


@dataclass
class MavlinkConfig:
    enabled: bool = True
    fc_serial: str = "/dev/ttyACM0"
    fc_baud: int = 921600
    gcs_ip: str = "10.0.0.100"
    gcs_port: int = 14550
    local_port: int = 14551
    stream_rate_hz: int = 10


@dataclass
class TelemetryConfig:
    gps: GpsConfig = field(default_factory=GpsConfig)
    mavlink: MavlinkConfig = field(default_factory=MavlinkConfig)

    def validate(self) -> None:
        self.mavlink.fc_baud = _as_int(
            self.mavlink.fc_baud, "telemetry.mavlink.fc_baud", 1200, 3000000, 921600
        )
        if self.mavlink.enabled:
            _validate_ip(self.mavlink.gcs_ip, "telemetry.mavlink.gcs_ip")


@dataclass
class VideoConfig:
    mode: str = "off"  # off | sender | receiver
    source_device: str | None = None  # /dev/video0, libcamera, nvidia
    caps: str = "video/x-raw,width=1280,height=720,framerate=30/1"
    bitrate_kbps: int = 4000
    transport: str = "unicast"  # unicast | multicast
    fec: bool = True
    adaptive: bool = True
    dest_ip: str = "10.0.0.100"
    dest_port: int = 5000
    multicast_group: str = "239.255.77.77"

    def validate(self) -> None:
        if self.mode not in ("off", "sender", "receiver"):
            raise ConfigError(f"video.mode must be off|sender|receiver, got '{self.mode}'")
        if self.transport not in ("unicast", "multicast"):
            raise ConfigError(f"video.transport must be unicast|multicast, got '{self.transport}'")
        self.bitrate_kbps = _as_int(self.bitrate_kbps, "video.bitrate_kbps", 100, 50000, 4000)
        self.dest_port = _as_int(self.dest_port, "video.dest_port", 1024, 65535, 5000)
        if self.transport == "multicast":
            _validate_ip(self.multicast_group, "video.multicast_group")
            if not self.multicast_group.startswith("239."):
                raise ConfigError("video.multicast_group must be a 239.0.0.0/8 address")


@dataclass
class DashboardConfig:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    template_dir: str | None = None  # None = bundled dashboard template

    def validate(self) -> None:
        self.port = _as_int(self.port, "dashboard.port", 1024, 65535, 8080)


@dataclass
class ManagementConfig:
    token: str = "change-me"
    udp_port: int = 9000
    bind_interface: str = "bat0"

    def validate(self) -> None:
        self.udp_port = _as_int(self.udp_port, "management.udp_port", 1024, 65535, 9000)
        if not self.token:
            raise ConfigError("management.token must not be empty "
                              "(generate one with: meshctl token)")


@dataclass
class MeshConfigFile:
    node: NodeConfig = field(default_factory=NodeConfig)
    mesh: MeshConfig = field(default_factory=MeshConfig)
    radios: list[RadioConfig] = field(default_factory=list)
    qos: QosConfig = field(default_factory=QosConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    management: ManagementConfig = field(default_factory=ManagementConfig)

    def validate(self) -> None:
        self.node.validate()
        self.mesh.validate()
        if not self.radios:
            raise ConfigError("at least one radio must be configured under 'radios'")
        for r in self.radios:
            r.validate()
        self.qos.validate()
        self.telemetry.validate()
        self.video.validate()
        self.dashboard.validate()
        self.management.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": {
                "id": self.node.id,
                "role": self.node.role,
                "ip": self.node.ip,
                "netmask": self.node.netmask,
                "hostname": self.node.hostname,
            },
            "mesh": {
                "id": self.mesh.id,
                "essid": self.mesh.essid,
                "ibss_bssid": self.mesh.ibss_bssid,
                "routing_algo": self.mesh.routing_algo,
                "orig_interval_ms": self.mesh.orig_interval_ms,
                "hop_penalty": self.mesh.hop_penalty,
                "fragmentation": self.mesh.fragmentation,
                "interface_routing": self.mesh.interface_routing,
                "network_coding": self.mesh.network_coding,
                "gateway": self.mesh.gateway,
                "gateway_download_mbit": self.mesh.gateway_download_mbit,
                "gateway_upload_mbit": self.mesh.gateway_upload_mbit,
                "external_iface": self.mesh.external_iface,
                "dns_server": self.mesh.dns_server,
            },
            "radios": [
                {
                    "name": r.name,
                    "iface": r.iface,
                    "mode": r.mode,
                    "band": r.band,
                    "channel": r.channel,
                    "txpower_dbm": r.txpower_dbm,
                    "mac": r.mac,
                    "driver_options": r.driver_options,
                }
                for r in self.radios
            ],
            "qos": {
                "enabled": self.qos.enabled,
                "classes": [
                    {
                        "name": c.name,
                        "dscp": c.dscp,
                        "matches": [
                            {"protocol": m.protocol, "dport": m.dport,
                             "sport": m.sport, "dscp": m.dscp}
                            for m in c.matches
                        ],
                        "rate": c.rate,
                        "ceil": c.ceil,
                        "prio": c.prio,
                        "is_default": c.is_default,
                    }
                    for c in self.qos.classes
                ],
            },
            "telemetry": {
                "gps": {
                    "enabled": self.telemetry.gps.enabled,
                    "device": self.telemetry.gps.device,
                    "fixed_location": self.telemetry.gps.fixed_location,
                },
                "mavlink": {
                    "enabled": self.telemetry.mavlink.enabled,
                    "fc_serial": self.telemetry.mavlink.fc_serial,
                    "fc_baud": self.telemetry.mavlink.fc_baud,
                    "gcs_ip": self.telemetry.mavlink.gcs_ip,
                    "gcs_port": self.telemetry.mavlink.gcs_port,
                    "local_port": self.telemetry.mavlink.local_port,
                    "stream_rate_hz": self.telemetry.mavlink.stream_rate_hz,
                },
            },
            "video": {
                "mode": self.video.mode,
                "source_device": self.video.source_device,
                "caps": self.video.caps,
                "bitrate_kbps": self.video.bitrate_kbps,
                "transport": self.video.transport,
                "fec": self.video.fec,
                "adaptive": self.video.adaptive,
                "dest_ip": self.video.dest_ip,
                "dest_port": self.video.dest_port,
                "multicast_group": self.video.multicast_group,
            },
            "management": {
                "token": self.management.token,
                "udp_port": self.management.udp_port,
                "bind_interface": self.management.bind_interface,
            },
            "dashboard": {
                "enabled": self.dashboard.enabled,
                "host": self.dashboard.host,
                "port": self.dashboard.port,
                "template_dir": self.dashboard.template_dir,
            },
        }


def default_config() -> MeshConfigFile:
    cfg = MeshConfigFile()
    cfg.radios = [RadioConfig(name="radioA", iface="auto", mode="auto",
                              band="2.4g", channel=6, txpower_dbm=20)]
    cfg.qos.classes = [
        QosClassConfig(
            name="command_and_control",
            dscp=["CS6", "EF"],
            matches=[
                QosMatch(protocol="udp", dport="14550:14555"),
                QosMatch(protocol="tcp", dport="14550:14555"),
            ],
            rate="2mbit",
            ceil="8mbit",
            prio=0,
        ),
        QosClassConfig(
            name="video",
            dscp=["AF41", "AF42", "AF43"],
            matches=[
                QosMatch(protocol="udp", dport="5000:5999"),
            ],
            rate="20mbit",
            ceil="40mbit",
            prio=1,
        ),
        QosClassConfig(
            name="best_effort",
            is_default=True,
            prio=2,
        ),
    ]
    return cfg


def load_config(path: Path) -> MeshConfigFile:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    with open(path) as fh:
        raw = yaml.safe_load(fh) or {}

    cfg = default_config()
    _apply(raw, cfg)

    # Management token can be overridden by environment (avoids storing secrets
    # in the deployed config when desired).
    token_env = os.environ.get("MESH_MGMT_TOKEN")
    if token_env:
        cfg.management.token = token_env

    cfg.validate()
    return cfg


def _as_str(value: Any, default: str) -> str:
    """String coercion that undoes the YAML 1.1 'off'/'on' bool gotcha."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if value is None:
        return default
    return str(value)


def _apply(raw: dict[str, Any], cfg: MeshConfigFile) -> None:
    node = raw.get("node") or {}
    cfg.node.id = node.get("id", cfg.node.id)
    cfg.node.role = node.get("role", cfg.node.role)
    cfg.node.ip = node.get("ip", cfg.node.ip)
    cfg.node.netmask = node.get("netmask", cfg.node.netmask)
    cfg.node.hostname = node.get("hostname")

    mesh = raw.get("mesh") or {}
    cfg.mesh.id = mesh.get("id", cfg.mesh.id)
    cfg.mesh.essid = mesh.get("essid", cfg.mesh.essid)
    cfg.mesh.ibss_bssid = mesh.get("ibss_bssid", cfg.mesh.ibss_bssid)
    cfg.mesh.routing_algo = mesh.get("routing_algo", cfg.mesh.routing_algo)
    cfg.mesh.orig_interval_ms = mesh.get("orig_interval_ms", cfg.mesh.orig_interval_ms)
    cfg.mesh.hop_penalty = mesh.get("hop_penalty", cfg.mesh.hop_penalty)
    cfg.mesh.fragmentation = mesh.get("fragmentation", cfg.mesh.fragmentation)
    cfg.mesh.interface_routing = mesh.get("interface_routing", cfg.mesh.interface_routing)
    cfg.mesh.network_coding = mesh.get("network_coding", cfg.mesh.network_coding)
    cfg.mesh.gateway = _as_str(mesh.get("gateway"), cfg.mesh.gateway)
    cfg.mesh.gateway_download_mbit = mesh.get(
        "gateway_download_mbit", cfg.mesh.gateway_download_mbit
    )
    cfg.mesh.gateway_upload_mbit = mesh.get(
        "gateway_upload_mbit", cfg.mesh.gateway_upload_mbit
    )
    cfg.mesh.external_iface = mesh.get("external_iface")
    cfg.mesh.dns_server = mesh.get("dns_server", cfg.mesh.dns_server)

    radios = raw.get("radios")
    if radios:
        cfg.radios = []
        for r in radios:
            cfg.radios.append(
                RadioConfig(
                    name=r.get("name", "radioA"),
                    iface=r.get("iface", "auto"),
                    mode=r.get("mode", "auto"),
                    band=r.get("band", "2.4g"),
                    channel=r.get("channel", 6),
                    txpower_dbm=r.get("txpower_dbm"),
                    mac=r.get("mac"),
                    driver_options=r.get("driver_options", ""),
                )
            )

    qos = raw.get("qos")
    if qos is not None:
        cfg.qos.enabled = qos.get("enabled", cfg.qos.enabled)
        classes = qos.get("classes")
        if classes:
            cfg.qos.classes = []
            for c in classes:
                matches = []
                for m in c.get("matches", []):
                    matches.append(
                        QosMatch(
                            protocol=m.get("protocol", "udp"),
                            dport=m.get("dport"),
                            sport=m.get("sport"),
                            dscp=m.get("dscp"),
                        )
                    )
                cfg.qos.classes.append(
                    QosClassConfig(
                        name=c.get("name", "best_effort"),
                        dscp=c.get("dscp", []),
                        matches=matches,
                        rate=c.get("rate", "10mbit"),
                        ceil=c.get("ceil"),
                        prio=c.get("prio", 2),
                        is_default=c.get("is_default", False),
                    )
                )

    tele = raw.get("telemetry") or {}
    gps = tele.get("gps") or {}
    cfg.telemetry.gps.enabled = gps.get("enabled", cfg.telemetry.gps.enabled)
    cfg.telemetry.gps.device = gps.get("device")
    cfg.telemetry.gps.fixed_location = gps.get("fixed_location")

    mav = tele.get("mavlink") or {}
    cfg.telemetry.mavlink.enabled = mav.get("enabled", cfg.telemetry.mavlink.enabled)
    cfg.telemetry.mavlink.fc_serial = mav.get("fc_serial", cfg.telemetry.mavlink.fc_serial)
    cfg.telemetry.mavlink.fc_baud = mav.get("fc_baud", cfg.telemetry.mavlink.fc_baud)
    cfg.telemetry.mavlink.gcs_ip = mav.get("gcs_ip", cfg.telemetry.mavlink.gcs_ip)
    cfg.telemetry.mavlink.gcs_port = mav.get("gcs_port", cfg.telemetry.mavlink.gcs_port)
    cfg.telemetry.mavlink.local_port = mav.get("local_port", cfg.telemetry.mavlink.local_port)
    cfg.telemetry.mavlink.stream_rate_hz = mav.get(
        "stream_rate_hz", cfg.telemetry.mavlink.stream_rate_hz
    )

    video = raw.get("video") or {}
    cfg.video.mode = _as_str(video.get("mode"), cfg.video.mode)
    cfg.video.source_device = video.get("source_device")
    cfg.video.caps = video.get("caps", cfg.video.caps)
    cfg.video.bitrate_kbps = video.get("bitrate_kbps", cfg.video.bitrate_kbps)
    cfg.video.transport = video.get("transport", cfg.video.transport)
    cfg.video.fec = video.get("fec", cfg.video.fec)
    cfg.video.adaptive = video.get("adaptive", cfg.video.adaptive)
    cfg.video.dest_ip = video.get("dest_ip", cfg.video.dest_ip)
    cfg.video.dest_port = video.get("dest_port", cfg.video.dest_port)
    cfg.video.multicast_group = video.get("multicast_group", cfg.video.multicast_group)

    mgmt = raw.get("management") or {}
    cfg.management.token = mgmt.get("token", cfg.management.token)
    cfg.management.udp_port = mgmt.get("udp_port", cfg.management.udp_port)
    cfg.management.bind_interface = mgmt.get("bind_interface", cfg.management.bind_interface)

    dash = raw.get("dashboard") or {}
    cfg.dashboard.enabled = dash.get("enabled", cfg.dashboard.enabled)
    cfg.dashboard.host = dash.get("host", cfg.dashboard.host)
    cfg.dashboard.port = dash.get("port", cfg.dashboard.port)
    cfg.dashboard.template_dir = dash.get("template_dir")


def dump_template(path) -> None:
    """Write a fully-populated example config to ``path``."""
    path = Path(path)
    cfg = default_config()
    template = yaml.safe_dump(cfg.to_dict(), sort_keys=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# batman-adv drone mesh node configuration\n"
        "# Copy to /opt/mesh/config/mesh.yaml and edit per node.\n"
        f"# Unique per node: node.id, node.ip.\n\n{template}"
    )


def patch_config(path: Path, changes: dict[str, Any]) -> MeshConfigFile:
    """Merge ``changes`` (dotted keys like {'mesh.orig_interval_ms': 500})
    into an existing config file and persist it."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text()) or {}
    for dotted, value in changes.items():
        parts = dotted.split(".")
        node = raw
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def with_changes(cfg: MeshConfigFile, changes: dict[str, Any]) -> MeshConfigFile:
    """Return a copy of ``cfg`` with dotted-key changes applied (dry-run helper).

    Supports list indexing for ``radios`` (e.g. ``radios.0.channel``).
    Validates the result and raises :class:`ConfigError` on invalid values.
    """
    out = copy.deepcopy(cfg)
    for dotted, value in changes.items():
        parts = dotted.split(".")
        node = out
        for p in parts[:-1]:
            if isinstance(node, list) and p.isdigit():
                node = node[int(p)]
            else:
                node = getattr(node, p)
        if isinstance(node, list) and parts[-1].isdigit():
            raise ConfigError(f"cannot set whole list element via key '{dotted}'")
        setattr(node, parts[-1], value)
    out.validate()
    return out
