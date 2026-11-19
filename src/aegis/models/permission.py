"""Contracts for the permission gate."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from aegis.models.skill import RiskLevel


class Verdict(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class ConfirmRequest(BaseModel):
    """What the user is asked to approve."""

    skill: str
    description: str
    risk: RiskLevel
    args: dict[str, Any]


# UIs supply this. Returns True to approve. No callback means "deny".
ConfirmFn = Callable[[ConfirmRequest], bool]


class PermissionDecision(BaseModel):
    verdict: Verdict
    risk: RiskLevel
    dry_run: bool
    reason: str
    confirmed: bool = False

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOWED


class ExecutionResult(BaseModel):
    skill: str
    args: dict[str, Any] = Field(default_factory=dict)
    decision: PermissionDecision | None = None
    output: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.output is not None
