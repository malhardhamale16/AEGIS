"""Agents: planner, executor, conversation. They reach skills only via the registry/gate."""

from aegis.agents.conversation import ConversationAgent, describe_result
from aegis.agents.executor import ExecutorAgent
from aegis.agents.planner import PlannerAgent, PlanningError

__all__ = [
    "ConversationAgent",
    "ExecutorAgent",
    "PlannerAgent",
    "PlanningError",
    "describe_result",
]
