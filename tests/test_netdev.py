"""Tests for the Executor and low-level netdev helpers (mocked via subprocess)."""

import pytest

from meshd.netdev import Executor, ibss_joined_bssid, txpower_is_quirk


class FakeExecutor:
    """Stub Executor whose ``output`` returns canned ``iw`` text."""

    def __init__(self, output: str):
        self._output = output

    async def output(self, argv, check=True, timeout=None):
        return self._output


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


@pytest.mark.asyncio
async def test_ibss_joined_bssid_connected_to_format():
    """brcmfmac reports the IBSS cell as 'Connected to <mac> (on wlan0)'."""
    ex = FakeExecutor("Connected to 02:12:34:56:78:9a (on wlan0)\n"
                      "\tSSID: drone-mesh\n\tfreq: 2437")
    assert await ibss_joined_bssid(ex, "wlan0") == "02:12:34:56:78:9a"


@pytest.mark.asyncio
async def test_ibss_joined_bssid_ibss_joined_format():
    ex = FakeExecutor("IBSS: joined 02:12:34:56:78:9a (on wlan0)\n"
                      "\tSSID: drone-mesh")
    assert await ibss_joined_bssid(ex, "wlan0") == "02:12:34:56:78:9a"


@pytest.mark.asyncio
async def test_ibss_joined_bssid_not_connected():
    ex = FakeExecutor("Not connected.\n")
    assert await ibss_joined_bssid(ex, "wlan0") is None
