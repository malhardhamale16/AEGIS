"""Skill contract shared across layers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RiskLevel(StrEnum):
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {RiskLevel.SAFE: 0, RiskLevel.CONFIRM: 1, RiskLevel.BLOCKED: 2}


class SkillError(Exception):
    """An expected, user-facing skill failure (bad path, unknown app, ...)."""


class SkillIO(BaseModel):
    """Base for skill input/output models. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class Skill(ABC):
    """A small, single-purpose, testable unit of action.

    Subclasses declare the class attributes below and implement ``run``. Skills with risk
    ``confirm`` change system state and must honor ``dry_run`` (simulate, change nothing).
    """

    name: ClassVar[str]
    description: ClassVar[str]
    risk: ClassVar[RiskLevel]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def run(self, data: Any, *, dry_run: bool) -> BaseModel:
        """Execute with an already-validated ``input_model`` instance."""


class SkillInfo(BaseModel):
    """Read-only description of a skill, safe to hand to an LLM or a UI."""

    name: str
    description: str
    risk: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
