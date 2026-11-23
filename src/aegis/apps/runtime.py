"""Wires core, skills and agents together from validated settings."""

from __future__ import annotations

from dataclasses import dataclass

from aegis.agents.conversation import ConversationAgent
from aegis.agents.executor import ExecutorAgent
from aegis.agents.planner import PlannerAgent
from aegis.core.events import EventBus
from aegis.core.llm import LLMClient, OllamaClient
from aegis.core.permission import PermissionGate
from aegis.core.registry import SkillRegistry
from aegis.models.config import Settings
from aegis.models.permission import ConfirmFn
from aegis.skills import machine_context, register_builtin_skills


@dataclass
class Runtime:
    settings: Settings
    bus: EventBus
    registry: SkillRegistry
    gate: PermissionGate
    llm: LLMClient
    planner: PlannerAgent
    executor: ExecutorAgent
    conversation: ConversationAgent

    def close(self) -> None:
        close = getattr(self.llm, "close", None)
        if callable(close):
            close()


def build_registry(settings: Settings) -> SkillRegistry:
    return register_builtin_skills(SkillRegistry(settings.skills), settings.skills)


def build_runtime(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    confirm: ConfirmFn | None = None,
    bus: EventBus | None = None,
) -> Runtime:
    bus = bus or EventBus()
    registry = build_registry(settings)
    gate = PermissionGate(registry, settings.aegis.safety, confirm=confirm, bus=bus)
    llm = llm or OllamaClient(settings.models.ollama, settings.models.generation)
    roles = settings.models.roles
    agents = settings.aegis.agents
    planner = PlannerAgent(
        llm, registry, roles.planner, agents.planner, context=machine_context(settings.skills)
    )
    executor = ExecutorAgent(gate, agents.executor, bus=bus)
    conversation = ConversationAgent(
        llm, planner, executor, roles.conversation, agents.conversation
    )
    return Runtime(settings, bus, registry, gate, llm, planner, executor, conversation)
