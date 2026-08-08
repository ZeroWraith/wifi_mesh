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

BATCTL = "sudo batctl"


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
        for line in lines[1:]:
            parts = line.split()
            if parts:
                ifaces.append({
                    "name": parts[0],
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
    try:
        out = run_cmd("ip -4 addr show bat0 2>/dev/null")
        if out:
            for line in out.split("\n"):
                if "inet " in line:
                    local_ip = line.strip().split()[1].split("/")[0]
                    break
    except Exception:
        pass

    orig_out = run_cmd(f"{BATCTL} oj 2>/dev/null")
    node_count = 0
    nodes = []
    if orig_out:
        try:
            data = json.loads(orig_out)
            originators = data.get("originators", [])
            node_count = len(originators)
            for orig in originators:
                nodes.append({
                    "mac": orig.get("originator", "unknown"),
                    "ip": orig.get("last_seen", ""),
                    "tq": orig.get("tq", 0),
                    "nexthop": orig.get("next_hop", ""),
                    "outgoing_interface": orig.get("outgoing_iface", ""),
                })
        except json.JSONDecodeError:
            pass

    neigh_out = run_cmd(f"{BATCTL} nj 2>/dev/null")
    neighbor_count = 0
    if neigh_out:
        try:
            ndata = json.loads(neigh_out)
            neighbor_count = len(ndata.get("neighbors", []))
        except json.JSONDecodeError:
            pass

    gw_out = run_cmd(f"{BATCTL} gwj 2>/dev/null")
    gateway_count = 0
    if gw_out:
        try:
            gdata = json.loads(gw_out)
            gateway_count = len(gdata.get("gateways", []))
        except json.JSONDecodeError:
            pass

    return jsonify({
        "local_ip": local_ip,
        "node_count": node_count,
        "neighbor_count": neighbor_count,
        "gateway_count": gateway_count,
        "nodes": nodes,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/mesh/topology")
def get_topology():
    out = run_cmd("sudo batadv-vis -f json 2>/dev/null")
    if out:
        try:
            return jsonify(json.loads(out))
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
