"""Tests for the lifecycle state machine (steps faked with no-ops)."""


import pytest

from meshd.lifecycle import (
    START_ORDER,
    Lifecycle,
    LifecycleState,
    Step,
)


def _noop_start(ctx):
    async def inner():
        return None
    return inner()


def _noop_stop(ctx):
    async def inner():
        return None
    return inner()


class _Ctx:
    pass


@pytest.mark.asyncio
async def test_full_start_reaches_ready():
    lc = Lifecycle(_Ctx(), store=None)
    for state in START_ORDER:
        lc.register(state, Step(f"step-{state.value}",
                                start=_noop_start, stop=_noop_stop))
    results = await lc.start()
    assert all(r.ok for r in results)
    assert lc.state == LifecycleState.READY
    assert lc.status()["state"] == "ready"


@pytest.mark.asyncio
async def test_required_step_failure_aborts_and_marks_failed():
    lc = Lifecycle(_Ctx(), store=None)

    async def bad(ctx):
        raise RuntimeError("boom")

    lc.register(LifecycleState.RADIOS_UP, Step("bad", start=bad, stop=_noop_stop))
    for state in START_ORDER:
        if state == LifecycleState.RADIOS_UP:
            continue
        lc.register(state, Step(f"step-{state.value}",
                                start=_noop_start, stop=_noop_stop))

    results = await lc.start()
    failed = [r for r in results if not r.ok]
    assert failed and failed[0].name == "bad"
    assert lc.state == LifecycleState.FAILED


@pytest.mark.asyncio
async def test_optional_step_failure_degrades_but_reaches_ready():
    lc = Lifecycle(_Ctx(), store=None)

    async def bad(ctx):
        raise RuntimeError("optional boom")

    for state in START_ORDER:
        if state == LifecycleState.QOS_APPLIED:
            lc.register(state, Step("qos", start=bad, stop=_noop_stop, required=False))
        else:
            lc.register(state, Step(f"step-{state.value}",
                                    start=_noop_start, stop=_noop_stop))

    results = await lc.start()
    assert all(r.ok or r.degraded for r in results)
    assert lc.effective_state() == LifecycleState.DEGRADED
    assert lc.status()["state"] == "degraded"


@pytest.mark.asyncio
async def test_unregistered_states_are_skipped():
    lc = Lifecycle(_Ctx(), store=None)
    # Only register PROVISIONING and READY; the middle states must be skipped.
    lc.register(LifecycleState.PROVISIONING,
                Step("prov", start=_noop_start, stop=_noop_stop))
    results = await lc.start()
    assert lc.state == LifecycleState.READY
    assert len(results) == 1


@pytest.mark.asyncio
async def test_stop_runs_reverse_order():
    calls = []
    lc = Lifecycle(_Ctx(), store=None)

    def make(state, name):
        async def start(ctx):
            calls.append(f"start:{name}")

        async def stop(ctx):
            calls.append(f"stop:{name}")

        return Step(name, start=start, stop=stop)

    for state in START_ORDER:
        lc.register(state, make(state, state.value))

    await lc.start()
    calls.clear()
    await lc.stop()
    assert calls == [
        f"stop:{state.value}" for state in reversed(START_ORDER)
    ]
    assert lc.state == LifecycleState.DOWN
