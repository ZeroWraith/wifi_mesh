"""meshctl — operator CLI for the mesh control plane.

Talks to the local daemon over its UNIX control socket for status/stop, and
falls back to interactive systemd control for start. Remote, cross-node
management is added in the management phase (`--device <ip>`).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path

from meshd.config import ConfigError, dump_template, load_config
from meshd.control import rpc
from meshd.logs import setup_logging

DEFAULT_SOCKET = "/var/run/mesh/mesh.sock"
DEFAULT_CONFIG = "/opt/mesh/config/mesh.yaml"

SERVICE = "meshd.service"


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="meshctl",
                                     description="batman-adv mesh operator CLI")
    parser.add_argument("-s", "--socket", default=DEFAULT_SOCKET,
                        help=f"daemon control socket (default: {DEFAULT_SOCKET})")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help=f"path to mesh.yaml (default: {DEFAULT_CONFIG})")
    parser.add_argument("-d", "--device", default=None,
                        help="target remote mesh node IP for management RPC "
                             "(overrides --socket)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("token", help="generate a management token")
    sub.add_parser("init", help="write a template mesh.yaml")
    sub.add_parser("validate", help="validate local config (dry-run)")
    sub.add_parser("ping", help="ping the local daemon")
    sub.add_parser("status", help="show local daemon status")
    sub.add_parser("stop", help="gracefully stop the local mesh")
    sub.add_parser("restart", help="restart the local mesh")
    sub.add_parser("start", help="start meshd via systemd")
    sub.add_parser("nodes", help="list fleet nodes from the alfred registry")
    return parser.parse_args(argv)


def _need_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print("error: operation requires root", file=sys.stderr)
        sys.exit(1)


async def _rpc_or_exit(sock: str, req: dict) -> dict:
    try:
        return await rpc(sock, req)
    except FileNotFoundError:
        print(f"error: daemon not running (no socket at {sock})", file=sys.stderr)
        sys.exit(1)


def _print_status(data: dict) -> None:
    node = data.get("node", {})
    lc = data.get("lifecycle", {})
    print(f"Node            : {node.get('node_id','?')} ({node.get('role','?')})")
    print(f"IP (bat0)       : {node.get('ip','?')}")
    print(f"State           : {lc.get('state','?')}"
          + ("  [DEGRADED]" if lc.get("degraded") else ""))
    print("Radios          :")
    for radio in data.get("radios", []):
        status = "joined" if radio.get("joined") else ("error: " + radio.get("error", "down"))
        quirk = " (txpower quirk)" if radio.get("txpower_quirk") else ""
        print(f"  - {radio.get('name')}: {radio.get('iface','-')} [{radio.get('mode','-')}] "
              f"{status}{quirk}")
    health = data.get("health") or {}
    if health:
        print(f"Health          : bat0_up={health.get('bat0_up')} "
              f"originators={health.get('originators')}")


def main(argv: list | None = None) -> int:
    args = parse_args(argv)
    setup_logging(verbose=False, foreground=True)

    if args.cmd == "token":
        print(secrets.token_urlsafe(24))
        return 0

    if args.cmd == "init":
        dump_template(Path(args.config))
        print(f"wrote template config to {args.config}")
        return 0

    if args.cmd == "validate":
        try:
            cfg = load_config(Path(args.config))
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"configuration OK for node '{cfg.node.id}' ip={cfg.node.ip_cidr}")
        return 0

    if args.cmd == "start":
        _need_root()
        rc = os.system(f"systemctl start {SERVICE}")
        return 0 if rc == 0 else 1

    # Fleet discovery reads the local alfred registry (no --device needed);
    # remote management targets a --device over JSON-RPC.
    if args.cmd == "nodes" or args.device:
        return asyncio.run(_remote(args))

    async def cli():
        req = {"cmd": args.cmd}
        data = await _rpc_or_exit(args.socket, req)
        if args.cmd in ("stop", "restart"):
            if "error" in data:
                print(f"error: {data['error']}", file=sys.stderr)
                return 1
            print(f"daemon acknowledges: {data}")
            return 0
        if args.cmd == "ping":
            print("daemon is alive:", data)
            return 0
        if args.cmd == "status":
            if "error" in data:
                print(f"error: {data['error']}", file=sys.stderr)
                return 1
            _print_status(data)
            return 0
        return 0

    return asyncio.run(cli())


async def _remote(args: argparse.Namespace) -> int:
    from meshd.management import list_nodes, remote_call

    try:
        cfg = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    token = cfg.management.token
    if token == "change-me" and args.cmd != "nodes":
        print("error: set management.token in mesh.yaml (meshctl token)",
              file=sys.stderr)
        return 2

    if args.cmd == "nodes":
        from meshd.netdev import Executor
        try:
            nodes = await list_nodes(Executor())
        except Exception as exc:  # noqa: BLE001
            print(f"warning: registry read failed: {exc}", file=sys.stderr)
            nodes = []
        _print_nodes(nodes)
        return 0

    if not args.device:
        print("error: a --device <ip> is required for management commands",
              file=sys.stderr)
        return 2

    port = cfg.management.udp_port
    try:
        result = await remote_call(args.device, port, token, args.cmd)
    except asyncio.TimeoutError:
        print(f"error: RPC to {args.device} timed out (is meshd running there?)",
              file=sys.stderr)
        return 1
    except (OSError, Exception) as exc:  # noqa: BLE001
        print(f"error: RPC to {args.device} failed: {exc}", file=sys.stderr)
        return 1

    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    if args.cmd == "ping":
        print(f"{args.device} is alive:", result.get("result"))
        return 0
    if args.cmd == "status":
        _print_status(result.get("result", {}))
        return 0
    print(f"{args.device} acknowledges:", result.get("result"))
    return 0


def _print_nodes(nodes: list) -> None:
    if not nodes:
        print("(no nodes in registry — is alfred running and the mesh up?)")
        return
    print(f"{'NODE':<20} {'ROLE':<15} {'IP':<16} {'UDP_PORT':<10}")
    for node in sorted(nodes, key=lambda n: n.get("node_id", "")):
        print(f"{node.get('node_id','?'):<20} {node.get('role','?'):<15} "
              f"{node.get('ip','?'):<16} {node.get('udp_port','?'):<10}")


if __name__ == "__main__":
    sys.exit(main())

