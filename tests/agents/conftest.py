import pytest

from aegis.agents.executor import ExecutorAgent
from aegis.agents.planner import PlannerAgent
from aegis.core.events import EventBus
from aegis.core.permission import PermissionGate
from aegis.core.registry import SkillRegistry
from aegis.models.config import PlannerSettings, SafetyConfig


@pytest.fixture
def registry(echo, fake_write, danger, crash):
    reg = SkillRegistry()
    for s in (echo, fake_write, danger, crash):
        reg.register(s)
    return reg


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def make_planner(registry, fake_llm_factory):
    def _make(responses, **settings):
        llm = fake_llm_factory(responses)
        return PlannerAgent(llm, registry, "planner-model", PlannerSettings(**settings)), llm

    return _make


@pytest.fixture
def make_executor(registry, bus):
    def _make(confirm=None, **safety):
        gate = PermissionGate(registry, SafetyConfig(**safety), confirm=confirm, bus=bus)
        return ExecutorAgent(gate, bus=bus)

    return _make
