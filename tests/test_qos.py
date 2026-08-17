"""Tests for the QoS engine command construction."""

import pytest

from meshd.config import default_config
from meshd.qos import (
    DSCP_VALUES,
    QosManager,
    dscp_tos,
    parse_rate,
)


class FakeExec:
    def __init__(self):
        self.calls = []

    async def run(self, argv, timeout=30.0, check=False):
        self.calls.append(list(argv))
        return _Ok()

    async def ok(self, argv, timeout=15.0):
        return True

    async def output(self, argv, timeout=15.0):
        return ""


class _Ok:
    ok = True
    returncode = 0
    stdout = ""
    stderr = ""


@pytest.fixture
def qos_cfg():
    cfg = default_config()
    return cfg.qos


def test_dscp_mapping():
    assert DSCP_VALUES["CS6"] == 48
    assert DSCP_VALUES["EF"] == 46
    assert DSCP_VALUES["AF41"] == 34


def test_dscp_tos_shift():
    # DSCP 48 (CS6) occupies the top 6 bits of the TOS byte.
    assert dscp_tos(48) == 192  # 0xc0
    assert dscp_tos(46) == 184  # 0xb8


def test_parse_rate():
    assert parse_rate("2mbit") == "2000kbit"
    assert parse_rate("40mbit") == "40000kbit"
    assert parse_rate("1gbit") == "1gbit"


def test_class_id_mapping(qos_cfg):
    exec = FakeExec()
    qm = QosManager(exec, qos_cfg)
    qm._assign_numbers()
    ids = {c.name: qm._class_id(c) for c in qos_cfg.classes}
    assert len(set(ids.values())) == len(ids)  # unique classids
    assert ids["command_and_control"].startswith("1:")
    assert ids["best_effort"] != ids["video"]


def test_mangle_rule_generation(qos_cfg):
    exec = FakeExec()
    qm = QosManager(exec, qos_cfg)
    cmds = qm._mangle_cmds()
    # DEFAULT config: C&C has 2 matches (udp + tcp), video 1 match -> 6 rules
    # (each OUTPUT + FORWARD), best_effort has no matching rules.
    assert cmds
    flat = " | ".join(" ".join(c) for c in cmds)
    assert "OUTPUT" in flat and "FORWARD" in flat
    assert "-o bat0" in flat
    assert any("--set-dscp" in c and c[c.index("--set-dscp") + 1] == "48"
               for c in cmds)  # CS6 marking for C&C


@pytest.mark.asyncio
async def test_apply_emits_tc_and_iptables(qos_cfg):
    exec = FakeExec()
    qm = QosManager(exec, qos_cfg)
    await qm.apply()
    joined = " | ".join(" ".join(c) for c in exec.calls)
    assert "htb" in joined
    assert "sfq" in joined
    assert "mangle" in joined
    assert "flowid" in joined


@pytest.mark.asyncio
async def test_teardown_removes_previous(qos_cfg):
    exec = FakeExec()
    qm = QosManager(exec, qos_cfg)
    await qm.apply()
    exec.calls.clear()
    await qm.teardown()
    joined = " | ".join(" ".join(c) for c in exec.calls)
    assert "mangle" in joined and "-D" in joined
    assert "qdisc" in joined and "del" in joined
