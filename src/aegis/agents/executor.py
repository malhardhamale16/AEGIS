"""Executor agent: runs a plan step by step, every step through the permission gate.

Deterministic on purpose: no LLM is involved in deciding what runs.
"""

from __future__ import annotations

from aegis.core.events import EventBus
from aegis.core.logging import get_logger
from aegis.core.permission import PermissionGate
from aegis.models.config import ExecutorSettings
from aegis.models.permission import ExecutionResult
from aegis.models.plan import Plan, PlanResult

log = get_logger("agents.executor")

TOPIC_PLAN_STARTED = "plan.started"
TOPIC_PLAN_STEP = "plan.step"
TOPIC_PLAN_FINISHED = "plan.finished"


class ExecutorAgent:
    def __init__(
        self,
        gate: PermissionGate,
        settings: ExecutorSettings | None = None,
        *,
        bus: EventBus | None = None,
    ) -> None:
        self._gate = gate
        self._settings = settings or ExecutorSettings()
        self._bus = bus

    def _emit(self, topic: str, payload: dict) -> None:
        if self._bus:
            self._bus.publish(topic, payload)

    def execute(self, plan: Plan, *, dry_run: bool | None = None) -> PlanResult:
        self._emit(TOPIC_PLAN_STARTED, {"goal": plan.goal, "steps": len(plan.steps)})
        results: list[ExecutionResult] = []
        stopped: str | None = None

        for index, step in enumerate(plan.steps, 1):
            result = self._gate.execute(step.skill, step.args, dry_run=dry_run)
            results.append(result)
            self._emit(
                TOPIC_PLAN_STEP,
                {"index": index, "skill": step.skill, "ok": result.ok, "error": result.error},
            )
            if not result.ok:
                log.info("step %d (%s) failed: %s", index, step.skill, result.error)
                if self._settings.stop_on_failure:
                    stopped = f"step {index} ({step.skill}) failed: {result.error}"
                    break

        completed = stopped is None
        outcome = PlanResult(
            plan=plan, results=results, completed=completed, stopped_reason=stopped
        )
        self._emit(TOPIC_PLAN_FINISHED, {"goal": plan.goal, "ok": outcome.ok, "stopped": stopped})
        return outcome
