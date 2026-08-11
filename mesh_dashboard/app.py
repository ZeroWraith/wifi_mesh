#!/usr/bin/env python3
"""
Batman-Adv Mesh Network Dashboard
Real-time visualization of mesh topology, nodes, and link quality.
"""

import subprocess
import json
import os
import time
from flask import Flask, jsonify, render_template

app = Flask(__name__)

BATCTL = "batctl"


def run_cmd(cmd, timeout=5):
    """Run a shell command and return stdout, or None on error."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/mesh/originators")
def get_originators():
    out = run_cmd(f"{BATCTL} oj 2>/dev/null")
    if out:
        try:
            return jsonify(json.loads(out))
        except json.JSONDecodeError:
            pass
    return jsonify({"originators": []})


@app.route("/api/mesh/neighbors")
def get_neighbors():
    out = run_cmd(f"{BATCTL} nj 2>/dev/null")
    if out:
        try:
            return jsonify(json.loads(out))
        except json.JSONDecodeError:
            pass
    return jsonify({"neighbors": []})


@app.route("/api/mesh/interfaces")
def get_interfaces():
    out = run_cmd(f"{BATCTL} if 2>/dev/null")
    if out:
        lines = out.strip().split("\n")
        ifaces = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and ":" in parts[0]:
                ifaces.append({
                    "name": parts[0].rstrip(":"),
                    "status": parts[1] if len(parts) > 1 else "unknown"
                })
        return jsonify({"interfaces": ifaces})
    return jsonify({"interfaces": []})


@app.route("/api/mesh/gateways")
def get_gateways():
    out = run_cmd(f"{BATCTL} gwj 2>/dev/null")
    if out:
        try:
            return jsonify(json.loads(out))
        except json.JSONDecodeError:
            pass
    return jsonify({"gateways": []})


@app.route("/api/mesh/status")
def get_status():
    local_ip = None
    bat0_up = False

    try:
        out = run_cmd("ip -4 addr show bat0 2>/dev/null")
        if out:
            bat0_up = "UP" in out.split("\n")[0] if out else False
            for line in out.split("\n"):
                if "inet " in line:
                    local_ip = line.strip().split()[1].split("/")[0]
                    break
    except Exception:
        pass

    orig_out = run_cmd(f"{BATCTL} oj 2>/dev/null")
    node_count = 0
    nodes = []
    STALE_THRESHOLD_MS = 30000

    if orig_out:
        try:
            data = json.loads(orig_out)
            if isinstance(data, dict):
                originators = data.get("originators", [])
            else:
                originators = data if isinstance(data, list) else []
            for orig in originators:
                last_seen = orig.get("last_seen_msecs", 0)
                is_stale = last_seen > STALE_THRESHOLD_MS
                node_count += 1 if not is_stale else 0
                nodes.append({
                    "mac": orig.get("orig_address", orig.get("originator", "unknown")),
                    "ip": orig.get("last_seen", ""),
                    "tq": orig.get("tq", 0) if not is_stale else 0,
                    "nexthop": orig.get("next_hop", ""),
                    "outgoing_interface": orig.get("hard_ifname", orig.get("outgoing_iface", "")),
                    "last_seen_ms": last_seen,
                    "stale": is_stale,
                })
        except json.JSONDecodeError:
            pass

    neigh_out = run_cmd(f"{BATCTL} nj 2>/dev/null")
    neighbor_count = 0
    if neigh_out:
        try:
            ndata = json.loads(neigh_out)
            if isinstance(ndata, dict):
                neighbor_count = len(ndata.get("neighbors", []))
            else:
                neighbor_count = len(ndata) if isinstance(ndata, list) else 0
        except json.JSONDecodeError:
            pass

    gw_out = run_cmd(f"{BATCTL} gwj 2>/dev/null")
    gateway_count = 0
    if gw_out:
        try:
            gdata = json.loads(gw_out)
            if isinstance(gdata, dict):
                gateway_count = len(gdata.get("gateways", []))
            else:
                gateway_count = len(gdata) if isinstance(gdata, list) else 0
        except json.JSONDecodeError:
            pass

    mesh_active = bat0_up and node_count > 0

    return jsonify({
        "local_ip": local_ip,
        "bat0_up": bat0_up,
        "mesh_active": mesh_active,
        "node_count": node_count,
        "neighbor_count": neighbor_count,
        "gateway_count": gateway_count,
        "nodes": nodes,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/mesh/topology")
def get_topology():
    out = run_cmd("batadv-vis -f json 2>/dev/null")
    if out:
        try:
            entries = []
            for line in out.strip().split("\n"):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            return jsonify(entries)
        except json.JSONDecodeError:
            pass
    return jsonify([])


@app.route("/api/mesh/gps")
def get_gps():
    out = run_cmd("alfred-gpsd 2>/dev/null", timeout=3)
    if out:
        try:
            return jsonify(json.loads(out))
        except json.JSONDecodeError:
            pass
    return jsonify([])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
