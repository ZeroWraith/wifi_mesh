"""Persistent runtime state for the mesh daemon.

Keeps the last-known lifecycle state, discovered radios and a running config
hash in ``/var/lib/mesh/state.json`` so the daemon can recover sensibly after
a crash or reboot (idempotency / state-awareness that the demo lacked).
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from meshd.logs import get_logger

log = get_logger("store")

DEFAULT_STATE_DIR = "/var/lib/mesh"
DEFAULT_RUN_DIR = "/var/run/mesh"
STATE_FILE = "state.json"


class Store:
    def __init__(self, state_dir: str = DEFAULT_STATE_DIR,
                 run_dir: str = DEFAULT_RUN_DIR):
        self.state_dir = state_dir
        self.run_dir = run_dir
        self.path = os.path.join(state_dir, STATE_FILE)
        self._data: dict[str, Any] = {}
        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self) -> None:
        for d in (self.state_dir, self.run_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except PermissionError:
                log.warning("cannot create %s (will use tmp)", d)
                d_tmp = tempfile.mkdtemp(prefix="mesh-")
                if d == self.state_dir:
                    self.state_dir = d_tmp
                    self.path = os.path.join(self.state_dir, STATE_FILE)
                else:
                    self.run_dir = d_tmp
                log.info("using %s as fallback runtime dir", d_tmp)

    def _load(self) -> None:
        try:
            with open(self.path) as fh:
                self._data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = {}

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, mapping: dict[str, Any]) -> None:
        self._data.update(mapping)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def flush(self) -> None:
        self.save()

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def config_hash(self) -> str | None:
        return self.get("config_hash")

    def set_config_hash(self, h: str) -> None:
        self.set("config_hash", h)

    def lifecycle_state(self) -> str:
        return self.get("lifecycle_state", "down")

    def set_lifecycle_state(self, state: str) -> None:
        self.set("lifecycle_state", state)
        self.save()
