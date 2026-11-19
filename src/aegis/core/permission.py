"""Permission gate: every skill execution goes through here.

Policy:
- ``blocked``: always denied.
- ``safe``: allowed, runs for real (safe skills must not change system state).
- ``confirm``: in dry-run mode it is allowed as a simulation without asking. Otherwise
  the user must approve through the ``confirm`` callback; no callback means denied.
  ``safety.require_confirmation: false`` skips the prompt.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from aegis.core.events import EventBus
from aegis.core.logging import get_logger
from aegis.core.registry import RegistryError, SkillRegistry
from aegis.models.config import SafetyConfig
from aegis.models.permission import (
    ConfirmFn,
    ConfirmRequest,
    ExecutionResult,
    PermissionDecision,
    Verdict,
)
from aegis.models.skill import RiskLevel

log = get_logger("permission")

TOPIC_DECIDED = "permission.decided"
TOPIC_FINISHED = "skill.finished"


class PermissionGate:
    def __init__(
        self,
        registry: SkillRegistry,
        safety: SafetyConfig | None = None,
        *,
        confirm: ConfirmFn | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._registry = registry
        self._safety = safety or SafetyConfig()
        self._confirm = confirm
        self._bus = bus

    def authorize(
        self, name: str, args: dict[str, Any], *, dry_run: bool | None = None
    ) -> PermissionDecision:
        """Decide whether ``name`` may run. May prompt the user via the callback."""
        dry = self._safety.dry_run if dry_run is None else dry_run
        self._registry.get(name)  # raises for unknown or disabled skills
        risk = self._registry.effective_risk(name)
        decision = self._decide(name, args, risk, dry)
        log.info("permission %s: %s (%s)", name, decision.verdict, decision.reason)
        if self._bus:
            self._bus.publish(TOPIC_DECIDED, {"skill": name, **decision.model_dump()})
        return decision

    def _decide(
        self, name: str, args: dict[str, Any], risk: RiskLevel, dry: bool
    ) -> PermissionDecision:
        def make(verdict: Verdict, reason: str, *, dry_run: bool, confirmed: bool = False):
            return PermissionDecision(
                verdict=verdict, risk=risk, dry_run=dry_run, reason=reason, confirmed=confirmed
            )

        if risk is RiskLevel.BLOCKED:
            return make(Verdict.DENIED, "skill is blocked", dry_run=dry)
        if risk is RiskLevel.SAFE:
            return make(Verdict.ALLOWED, "safe skill", dry_run=False)
        # confirm-level
        if dry:
            return make(Verdict.ALLOWED, "dry-run simulation", dry_run=True)
        if not self._safety.require_confirmation:
            return make(Verdict.ALLOWED, "confirmation disabled in config", dry_run=False)
        if self._confirm is None:
            return make(
                Verdict.DENIED, "confirmation required but no prompt available", dry_run=False
            )
        request = ConfirmRequest(
            skill=name,
            description=self._registry.get(name).description,
            risk=risk,
            args=args,
        )
        try:
            approved = bool(self._confirm(request))
        except Exception:
            log.exception("confirm callback failed for %s", name)
            approved = False
        if approved:
            return make(Verdict.ALLOWED, "user confirmed", dry_run=False, confirmed=True)
        return make(Verdict.DENIED, "user declined", dry_run=False)

    def execute(
        self, name: str, args: dict[str, Any] | None = None, *, dry_run: bool | None = None
    ) -> ExecutionResult:
        """Validate, authorize, and run a skill. Never raises for expected failures."""
        args = dict(args or {})
        result = self._execute(name, args, dry_run)
        if self._bus:
            self._bus.publish(
                TOPIC_FINISHED,
                {
                    "skill": name,
                    "ok": result.ok,
                    "error": result.error,
                    "dry_run": result.decision.dry_run if result.decision else None,
                },
            )
        return result

    def _execute(self, name: str, args: dict[str, Any], dry_run: bool | None) -> ExecutionResult:
        try:
            self._registry.validate_input(name, args)
        except RegistryError as exc:
            return ExecutionResult(skill=name, args=args, error=str(exc))
        except ValidationError as exc:
            return ExecutionResult(skill=name, args=args, error=f"invalid input: {exc}")

        decision = self.authorize(name, args, dry_run=dry_run)
        if not decision.allowed:
            return ExecutionResult(
                skill=name, args=args, decision=decision, error=f"denied: {decision.reason}"
            )
        try:
            output = self._registry.execute(name, args, dry_run=decision.dry_run)
        except Exception as exc:
            log.exception("skill %s failed", name)
            return ExecutionResult(
                skill=name, args=args, decision=decision, error=f"{type(exc).__name__}: {exc}"
            )
        return ExecutionResult(
            skill=name, args=args, decision=decision, output=output.model_dump(mode="json")
        )
