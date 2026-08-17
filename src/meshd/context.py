"""Daemon runtime context: the object passed to lifecycle steps.

Holds all components owned by the control plane so steps and later the
JSON-RPC API and services can reach them without a global.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from meshd.config import MeshConfigFile
from meshd.logs import get_logger
from meshd.netdev import Executor
from meshd.store import Store

log = get_logger("context")

DEFAULT_ALFRED_SOCK = "/var/run/alfred.sock"


@dataclass
class DaemonContext:
    config: MeshConfigFile
    store: Store
    exec: Executor

    # Components (populated by main and feature phases).
    radios: Any = None
    qos: Any = None
    services: Any = None
    api: Any = None

    # Runtime plumbing.
    loop: Any = None
    running: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def bindings(self) -> dict:
        """Published identity used for alfred registry + dashboard discovery."""
        node = self.config.node
        return {
            "node_id": node.id,
            "role": node.role,
            "ip": node.ip,
            "netmask": node.netmask,
            "mesh_id": self.config.mesh.id,
        }
