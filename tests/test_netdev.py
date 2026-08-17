"""Tests for the Executor and low-level netdev helpers (mocked via subprocess)."""

import pytest

from meshd.netdev import Executor, txpower_is_quirk


@pytest.mark.asyncio
async def test_executor_runs_and_captures():
    ex = Executor()
    res = await ex.run(["echo", "hello"], check=False)
    assert res.ok
    assert res.stdout.strip() == "hello"


@pytest.mark.asyncio
async def test_executor_reports_failure():
    ex = Executor()
    res = await ex.run(["false"], check=False)
    assert not res.ok
    assert res.returncode != 0


@pytest.mark.asyncio
async def test_executor_missing_binary():
    ex = Executor()
    res = await ex.run(["definitely-not-a-real-binary-xyz"], check=False)
    assert res.returncode == 127


@pytest.mark.asyncio
async def test_executor_timeout():
    ex = Executor()
    res = await ex.run(["sleep", "5"], timeout=0.2, check=False)
    assert not res.ok


def test_txpower_quirk_detection():
    assert txpower_is_quirk(-100.0)
    assert txpower_is_quirk(-100)
    assert not txpower_is_quirk(20.0)
    assert not txpower_is_quirk(None)
