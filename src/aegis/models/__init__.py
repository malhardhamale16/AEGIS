"""Shared data contracts. The lowest layer: imports nothing from the rest of aegis."""

from aegis.models.config import (
    AegisConfig,
    ModelsConfig,
    SafetyConfig,
    Settings,
    SkillsConfig,
    VoiceConfig,
)
from aegis.models.llm import ChatMessage, ChatResponse, HealthStatus
from aegis.models.permission import (
    ConfirmFn,
    ConfirmRequest,
    ExecutionResult,
    PermissionDecision,
    Verdict,
)
from aegis.models.plan import AgentReply, Plan, PlanDraft, PlanResult, PlanStep
from aegis.models.skill import RiskLevel, Skill, SkillError, SkillInfo, SkillIO

__all__ = [
    "AegisConfig",
    "AgentReply",
    "ChatMessage",
    "ChatResponse",
    "ConfirmFn",
    "ConfirmRequest",
    "ExecutionResult",
    "HealthStatus",
    "ModelsConfig",
    "PermissionDecision",
    "Plan",
    "PlanDraft",
    "PlanResult",
    "PlanStep",
    "RiskLevel",
    "SafetyConfig",
    "Settings",
    "Skill",
    "SkillError",
    "SkillIO",
    "SkillInfo",
    "SkillsConfig",
    "Verdict",
    "VoiceConfig",
]
