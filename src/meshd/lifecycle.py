"""Lifecycle state machine for the mesh daemon.

Steps run in a fixed order on start (``down`` -> ``ready``) and in reverse on
stop. Each step is idempotent. A failing *required* step aborts the start;
a failing *optional* step degrades the node but the mesh still comes up
(the ``degraded`` state). State is persisted so a crash can be diagnosed.
"""

from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from meshd.logs import get_logger

log = get_logger("lifecycle")


class LifecycleState(str, enum.Enum):  # noqa: UP042 (str+Enum for py3.10 Jetson compat)
    DOWN = "down"
    PROVISIONING = "provisioning"
    RADIOS_UP = "radios_up"
    MESH_JOINED = "mesh_joined"
    IP_ASSIGNED = "ip_assigned"
    QOS_APPLIED = "qos_applied"
    SERVICES_STARTED = "services_started"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"


# Ordered start sequence (teardown walks this in reverse).
START_ORDER: list[LifecycleState] = [
    LifecycleState.PROVISIONING,
    LifecycleState.RADIOS_UP,
    LifecycleState.MESH_JOINED,
    LifecycleState.IP_ASSIGNED,
    LifecycleState.QOS_APPLIED,
    LifecycleState.SERVICES_STARTED,
    LifecycleState.READY,
]


StepFn = Callable[[object], Awaitable[None]]


@dataclass
class Step:
    name: str
    start: StepFn | None = None
    stop: StepFn | None = None
    required: bool = True


@dataclass
class StepResult:
    name: str
    state: LifecycleState
    ok: bool
    error: str = ""
    degraded: bool = False


class Lifecycle:
    def __init__(self, context: object, store: object | None = None):
        self.context = context
        self.store = store
        self.steps: dict[LifecycleState, Step] = {}
        self.state: LifecycleState = LifecycleState.DOWN
        self.results: list[StepResult] = []
        self._degraded: bool = False

    # -- registration ---------------------------------------------------------

    def register(self, state: LifecycleState, step: Step) -> None:
        self.steps[state] = step

    def register_after(self, after: LifecycleState, state: LifecycleState,
                       step: Step) -> None:
        """Insert ``step`` at ``state`` which must come after ``after`` in START_ORDER."""
        idx = START_ORDER.index(after)
        self.steps[state] = step
        # Keep START_ORDER consistent: insert after the anchor.
        if state not in START_ORDER:
            START_ORDER.insert(idx + 1, state)

    # -- execution ------------------------------------------------------------

    def _set_state(self, state: LifecycleState) -> None:
        self.state = state
        if self.store is not None:
            self.store.set_lifecycle_state(state.value)
        log.info("lifecycle state -> %s", state.value)

    def effective_state(self) -> LifecycleState:
        if self.state == LifecycleState.READY and self._degraded:
            return LifecycleState.DEGRADED
        return self.state

    async def start(self) -> list[StepResult]:
        self.results = []
        self._degraded = False
        for state in START_ORDER:
            step = self.steps.get(state)
            if step is None:
                self._set_state(state)
                continue
            result = await self._run_step(step, state, start=True)
            self.results.append(result)
            if not result.ok and step.required:
                self._set_state(LifecycleState.FAILED)
                return self.results
            if not result.ok:
                self._degraded = True
                log.warning("step '%s' failed but is optional; degrading", step.name)
            self._set_state(self.effective_state())
        return self.results

    async def _run_step(self, step: Step, state: LifecycleState,
                        start: bool) -> StepResult:
        fn = step.start if start else step.stop
        if fn is None:
            return StepResult(name=step.name, state=state, ok=True)
        self._set_state(LifecycleState.STOPPING if not start else state)
        try:
            await fn(self.context)
            return StepResult(name=step.name, state=state, ok=True)
        except Exception as exc:  # noqa: BLE001
            log.error("step '%s' %s failed: %s", step.name,
                      "start" if start else "stop", exc)
            return StepResult(name=step.name, state=state, ok=False,
                              error=str(exc), degraded=not step.required)

    async def stop(self) -> list[StepResult]:
        results = []
        self._set_state(LifecycleState.STOPPING)
        for state in reversed(START_ORDER):
            step = self.steps.get(state)
            if step is None or step.stop is None:
                continue
            result = await self._run_step(step, state, start=False)
            results.append(result)
            if not result.ok:
                log.error("step '%s' failed to stop: %s", step.name, result.error)
        self._degraded = False
        self._set_state(LifecycleState.DOWN)
        return results

    def status(self) -> dict:
        return {
            "state": self.effective_state().value,
            "degraded": self._degraded,
            "steps": [
                {
                    "name": r.name,
                    "state": r.state.value,
                    "ok": r.ok,
                    "error": r.error,
                }
                for r in self.results
            ],
        }
