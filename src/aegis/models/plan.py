"""Plan and agent-reply contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aegis.models.permission import ExecutionResult


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class PlanDraft(BaseModel):
    """Exactly what the planner LLM must return (its JSON schema is sent to Ollama)."""

    model_config = ConfigDict(extra="forbid")

    steps: list[PlanStep] = Field(default_factory=list)
    response: str | None = None


class Plan(BaseModel):
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    response: str | None = None

    @property
    def is_direct_answer(self) -> bool:
        return not self.steps


class PlanResult(BaseModel):
    plan: Plan
    results: list[ExecutionResult] = Field(default_factory=list)
    completed: bool
    stopped_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.completed and all(r.ok for r in self.results)


class AgentReply(BaseModel):
    text: str
    plan: Plan | None = None
    result: PlanResult | None = None
    error: str | None = None
