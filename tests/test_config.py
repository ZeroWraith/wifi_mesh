"""Tests for the config loader / validator / patcher."""

import os

import pytest

from meshd.config import (
    ConfigError,
    dump_template,
    load_config,
    patch_config,
    with_changes,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(REPO_ROOT, "config", "mesh.yaml")


def test_load_example_config():
    cfg = load_config(EXAMPLE)
    assert cfg.node.id == "drone-01"
    assert cfg.node.role == "drone"
    assert cfg.node.ip_cidr == "10.0.0.3/24"
    assert cfg.radios[0].band == "2.4g"
    assert cfg.mesh.routing_algo == "BATMAN_V"
    assert [c.name for c in cfg.qos.classes] == [
        "command_and_control", "video", "best_effort",
    ]
    # YAML 1.1 bool gotchas are coerced back to strings.
    assert cfg.mesh.gateway == "off"
    assert cfg.video.mode == "off"


def test_template_roundtrip(tmp_path):
    path = tmp_path / "mesh.yaml"
    dump_template(path)
    cfg = load_config(path)
    assert cfg.node.id == "drone-01"
    assert cfg.radios
    assert cfg.qos.classes
    assert cfg.management.udp_port == 9000


@pytest.mark.parametrize(
    "field,value,expect",
    [
        ("node.role", "captain", "role"),
        ("node.ip", "999.0.0.1", "IP"),
        ("node.id", "bad id!", "id"),
        ("mesh.ibss_bssid", "not-a-mac", "ibss_bssid"),
        ("mesh.routing_algo", "BATMAN_III", "routing_algo"),
        ("radios.0.channel", 99, "channel"),
    ],
)
def test_invalid_config_rejected(tmp_path, field, value, expect):
    path = tmp_path / "mesh.yaml"
    dump_template(path)
    cfg = load_config(path)
    # with_changes applies the value and validates, raising ConfigError.
    with pytest.raises(ConfigError) as exc:
        with_changes(cfg, {field: value})
    assert expect in str(exc.value)


def test_with_changes_does_not_mutate(tmp_path):
    path = tmp_path / "mesh.yaml"
    dump_template(path)
    cfg = load_config(path)
    orig = cfg.mesh.orig_interval_ms
    changed = with_changes(cfg, {"mesh.orig_interval_ms": 500})
    assert changed.mesh.orig_interval_ms == 500
    assert cfg.mesh.orig_interval_ms == orig  # original untouched


def test_patch_config_persists(tmp_path):
    path = tmp_path / "mesh.yaml"
    dump_template(path)
    cfg = patch_config(path, {"mesh.orig_interval_ms": 500,
                              "node.ip": "10.0.0.42"})
    assert cfg.mesh.orig_interval_ms == 500
    assert cfg.node.ip == "10.0.0.42"
    reloaded = load_config(path)
    assert reloaded.mesh.orig_interval_ms == 500
    assert reloaded.node.ip == "10.0.0.42"


def test_token_env_override(tmp_path, monkeypatch):
    path = tmp_path / "mesh.yaml"
    dump_template(path)
    monkeypatch.setenv("MESH_MGMT_TOKEN", "env-secret")
    cfg = load_config(path)
    assert cfg.management.token == "env-secret"


def test_no_radios_rejected(tmp_path):
    path = tmp_path / "mesh.yaml"
    dump_template(path)
    cfg = load_config(path)
    cfg.radios = []
    with pytest.raises(ConfigError, match="radio"):
        cfg.validate()
